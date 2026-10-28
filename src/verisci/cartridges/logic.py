"""Formal Logic & SMT Verification Cartridge (`verisci.cartridges.logic`).

Deterministically verifies:
1. Step-by-step natural deduction / resolution proof derivations over propositional
   clauses (Modus Ponens, Modus Tollens, Disjunctive Syllogism, Resolution,
   Conjunction Elimination/Introduction).
2. Exact SAT/SMT variable truth assignments satisfying all CNF clauses simultaneously.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Set, Tuple

from verisci.protocol import ActionStep, Cartridge, DomainTask, VerificationResult


def _normalize_clause(literals: List[str]) -> Tuple[str, ...]:
    """Canonical sorted tuple of unique literals in a clause."""
    cleaned = sorted({lit.strip() for lit in literals if lit and lit.strip()})
    return tuple(cleaned)


def _negate_literal(lit: str) -> str:
    lit = lit.strip()
    if lit.startswith("~"):
        return lit[1:]
    if lit.startswith("!"):
        return lit[1:]
    return f"~{lit}"


def _is_tautology(clause: Tuple[str, ...]) -> bool:
    lit_set = set(clause)
    for lit in clause:
        if _negate_literal(lit) in lit_set:
            return True
    return False


def _can_resolve(
    c1: Tuple[str, ...], c2: Tuple[str, ...]
) -> Set[Tuple[str, ...]]:
    """Compute all sound single-literal resolvents between two clauses `c1` and `c2`."""
    s1 = set(c1)
    s2 = set(c2)
    resolvents: Set[Tuple[str, ...]] = set()
    for lit in s1:
        neg = _negate_literal(lit)
        if neg in s2:
            merged = (s1 - {lit}) | (s2 - {neg})
            resolvents.add(_normalize_clause(list(merged)))
    return resolvents


def _eval_literal(lit: str, assignment: Dict[str, bool]) -> bool:
    lit = lit.strip()
    if lit.startswith("~") or lit.startswith("!"):
        var = lit[1:]
        return not bool(assignment.get(var, False))
    return bool(assignment.get(lit, False))


def _eval_clause(clause: List[str], assignment: Dict[str, bool]) -> bool:
    return any(_eval_literal(lit, assignment) for lit in clause)


class LogicCartridge(Cartridge):
    """Formal Logic & Propositional Resolution / SAT Verifier."""

    domain = "logic"

    def evaluate_step(
        self, task: DomainTask, state: Dict[str, Any], step: ActionStep
    ) -> Dict[str, Any]:
        known_clauses: List[Tuple[str, ...]] = [
            _normalize_clause(list(c)) for c in state.get("known_clauses", [])
        ]
        known_set = set(known_clauses)
        assignment: Dict[str, bool] = dict(state.get("assignment", {}))
        valid_step = False
        reason = "unrecognized_action"

        if step.action_type == "derive_clause":
            p1_idx = int(step.params.get("p1", -1))
            p2_idx = int(step.params.get("p2", -1))
            conclusion = _normalize_clause(list(step.params.get("conclusion", [])))
            if 0 <= p1_idx < len(known_clauses) and 0 <= p2_idx < len(known_clauses):
                resolvents = _can_resolve(known_clauses[p1_idx], known_clauses[p2_idx])
                if conclusion in resolvents:
                    valid_step = True
                    reason = "valid_resolution"
                    if conclusion not in known_set:
                        known_clauses.append(conclusion)
                else:
                    reason = "invalid_resolution_inference"
            else:
                reason = "premise_index_out_of_bounds"

        elif step.action_type == "assign_var":
            var = str(step.params.get("var", ""))
            val = bool(step.params.get("val", False))
            if var:
                assignment[var] = val
                valid_step = True
                reason = "variable_assigned"

        return {
            "known_clauses": [list(c) for c in known_clauses],
            "assignment": assignment,
            "valid_step": valid_step,
            "reason": reason,
        }

    def verify(self, task: DomainTask, submission: Dict[str, Any]) -> VerificationResult:
        spec = task.spec
        premises: List[Tuple[str, ...]] = [
            _normalize_clause(list(c)) for c in spec.get("premises", [])
        ]
        goal_clause = _normalize_clause(list(spec.get("goal_clause", [])))
        variables: List[str] = list(spec.get("variables", []))

        known_clauses: List[Tuple[str, ...]] = list(premises)
        known_set: Set[Tuple[str, ...]] = set(premises)

        proof_steps: List[Dict[str, Any]] = list(submission.get("proof_steps", []))
        assignment: Dict[str, bool] = dict(submission.get("assignment", {}))

        step_validity: List[bool] = []
        valid_step_count = 0

        for raw_step in proof_steps:
            p1_idx = int(raw_step.get("p1", -1))
            p2_idx = int(raw_step.get("p2", -1))
            conclusion = _normalize_clause(list(raw_step.get("conclusion", [])))
            if 0 <= p1_idx < len(known_clauses) and 0 <= p2_idx < len(known_clauses):
                resolvents = _can_resolve(known_clauses[p1_idx], known_clauses[p2_idx])
                if conclusion in resolvents and not _is_tautology(conclusion):
                    step_validity.append(True)
                    valid_step_count += 1
                    if conclusion not in known_set:
                        known_clauses.append(conclusion)
                        known_set.add(conclusion)
                    else:
                        known_clauses.append(conclusion)
                else:
                    step_validity.append(False)
            else:
                step_validity.append(False)

        passed_invariants: List[str] = []
        failed_invariants: List[str] = []

        all_steps_sound = len(step_validity) > 0 and all(step_validity)
        if all_steps_sound or not goal_clause:
            passed_invariants.append("proof_steps_sound")
        else:
            failed_invariants.append("proof_steps_sound")

        goal_reached = (not goal_clause) or (goal_clause in known_set)
        if goal_reached:
            passed_invariants.append("goal_clause_derived")
        else:
            failed_invariants.append("goal_clause_derived")

        # Verify SAT assignment against all premises
        satisfied_clauses = sum(
            1 for c in premises if _eval_clause(list(c), assignment)
        )
        total_clauses = max(len(premises), 1)
        sat_ratio = satisfied_clauses / total_clauses

        require_sat = bool(spec.get("require_sat", True))
        sat_verified = (satisfied_clauses == len(premises)) if require_sat else True
        if sat_verified:
            passed_invariants.append("cnf_assignment_satisfied")
        else:
            failed_invariants.append("cnf_assignment_satisfied")

        verified = all_steps_sound and goal_reached and sat_verified

        step_soundness_ratio = (
            valid_step_count / len(proof_steps) if proof_steps else (1.0 if not goal_clause else 0.0)
        )
        reward = (
            0.35 * step_soundness_ratio
            + 0.35 * (1.0 if goal_reached else 0.0)
            + 0.30 * sat_ratio
        )
        if verified:
            reward = 1.0

        cert_payload = json.dumps(
            {
                "task_id": task.task_id,
                "verified": verified,
                "derived": [list(c) for c in known_clauses],
                "assignment": assignment,
            },
            sort_keys=True,
        )
        cert_hash = hashlib.sha256(cert_payload.encode("utf-8")).hexdigest()[:16]

        return VerificationResult(
            task_id=task.task_id,
            domain=self.domain,
            verified=verified,
            reward=reward,
            passed_invariants=passed_invariants,
            failed_invariants=failed_invariants,
            step_validity=step_validity,
            diagnostics={
                "valid_steps": valid_step_count,
                "total_steps": len(proof_steps),
                "satisfied_clauses": satisfied_clauses,
                "total_clauses": len(premises),
                "goal_reached": goal_reached,
                "variables_count": len(variables),
            },
            certificate_hash=cert_hash,
        )
