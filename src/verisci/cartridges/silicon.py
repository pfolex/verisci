"""Hardware & Digital Logic Cartridge (`verisci.cartridges.silicon`).

Deterministically simulates combinational gate netlists (`AND`, `OR`, `XOR`,
`NAND`, `NOR`, `NOT`, `MUX`), verifies acyclic topological structure, checks
exact truth-table equivalence across all $2^N$ input combinations, and evaluates
gate-count and critical-path depth constraints.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Set, Tuple

from verisci.protocol import ActionStep, Cartridge, DomainTask, VerificationResult

VALID_GATES = {"AND", "OR", "XOR", "NAND", "NOR", "NOT", "MUX", "BUF"}


def _eval_gate(op: str, vals: List[int]) -> int:
    op = op.upper()
    if op == "AND":
        return 1 if all(v == 1 for v in vals) else 0
    if op == "OR":
        return 1 if any(v == 1 for v in vals) else 0
    if op == "XOR":
        acc = 0
        for v in vals:
            acc ^= (v & 1)
        return acc
    if op == "NAND":
        return 0 if all(v == 1 for v in vals) else 1
    if op == "NOR":
        return 0 if any(v == 1 for v in vals) else 1
    if op == "NOT":
        return 0 if (vals and vals[0] == 1) else 1
    if op == "BUF":
        return 1 if (vals and vals[0] == 1) else 0
    if op == "MUX":
        # inputs: [sel, in0, in1] -> in1 if sel == 1 else in0
        sel = vals[0] if len(vals) > 0 else 0
        in0 = vals[1] if len(vals) > 1 else 0
        in1 = vals[2] if len(vals) > 2 else 0
        return in1 if sel == 1 else in0
    raise ValueError(f"Unsupported gate op: {op}")


def simulate_netlist(
    inputs: List[str],
    outputs: List[str],
    gates: List[Dict[str, Any]],
    input_vector: Dict[str, int],
) -> Tuple[bool, Dict[str, int], int, str]:
    """Simulate a combinational gate netlist on one input vector.

    Returns `(ok, wire_values, max_depth, error_reason)`.
    """
    wires: Dict[str, int] = {k: int(v) & 1 for k, v in input_vector.items()}
    depths: Dict[str, int] = {k: 0 for k in input_vector}

    remaining = list(gates)
    progressed = True
    while remaining and progressed:
        progressed = False
        next_remaining: List[Dict[str, Any]] = []
        for g in remaining:
            op = str(g.get("op", "")).upper()
            out_wire = str(g.get("out", ""))
            in_wires = [str(w) for w in g.get("ins", [])]
            if op not in VALID_GATES or not out_wire or not in_wires:
                return False, wires, 0, f"malformed_gate:{out_wire}"
            if all(w in wires for w in in_wires):
                if out_wire in wires:
                    return False, wires, 0, f"multiple_drivers:{out_wire}"
                in_vals = [wires[w] for w in in_wires]
                wires[out_wire] = _eval_gate(op, in_vals)
                depths[out_wire] = 1 + max(depths[w] for w in in_wires)
                progressed = True
            else:
                next_remaining.append(g)
        remaining = next_remaining

    if remaining:
        return False, wires, 0, "combinational_cycle_or_unconnected_wire"

    if any(out not in wires for out in outputs):
        return False, wires, 0, "missing_primary_output_driver"

    max_depth = max((depths.get(out, 0) for out in outputs), default=0)
    return True, {out: wires[out] for out in outputs}, max_depth, "ok"


class SiliconCartridge(Cartridge):
    """Hardware & Digital Logic Netlist Synthesis Verifier."""

    domain = "silicon"

    def evaluate_step(
        self, task: DomainTask, state: Dict[str, Any], step: ActionStep
    ) -> Dict[str, Any]:
        gates = list(state.get("gates", []))
        known_wires: Set[str] = set(task.spec.get("inputs", [])) | {
            str(g.get("out")) for g in gates
        }
        valid_step = False
        reason = "invalid_step"

        if step.action_type == "add_gate":
            op = str(step.params.get("op", "")).upper()
            out_wire = str(step.params.get("out", ""))
            in_wires = [str(w) for w in step.params.get("ins", [])]
            if (
                op in VALID_GATES
                and out_wire
                and out_wire not in known_wires
                and in_wires
                and all(w in known_wires for w in in_wires)
            ):
                gates.append({"op": op, "ins": in_wires, "out": out_wire})
                valid_step = True
                reason = "gate_added"
            else:
                reason = "invalid_gate_or_wire"

        return {
            "gates": gates,
            "valid_step": valid_step,
            "reason": reason,
        }

    def verify(self, task: DomainTask, submission: Dict[str, Any]) -> VerificationResult:
        spec = task.spec
        inputs: List[str] = list(spec.get("inputs", []))
        outputs: List[str] = list(spec.get("outputs", []))
        truth_table: List[Dict[str, Any]] = list(spec.get("truth_table", []))
        max_gates = int(spec.get("max_gates", 64))
        max_depth_limit = int(spec.get("max_depth", 32))

        gates: List[Dict[str, Any]] = list(submission.get("gates", []))
        step_validity: List[bool] = []
        known_wires: Set[str] = set(inputs)

        for g in gates:
            op = str(g.get("op", "")).upper()
            out_w = str(g.get("out", ""))
            in_ws = [str(w) for w in g.get("ins", [])]
            if (
                op in VALID_GATES
                and out_w
                and out_w not in known_wires
                and in_ws
                and all(w in known_wires for w in in_ws)
            ):
                step_validity.append(True)
                known_wires.add(out_w)
            else:
                step_validity.append(False)

        passed_invariants: List[str] = []
        failed_invariants: List[str] = []

        matches = 0
        total_rows = max(len(truth_table), 1)
        observed_depth = 0
        sim_ok_all = len(gates) > 0

        for row in truth_table:
            in_vec = {k: int(row["inputs"][k]) for k in inputs}
            expected_out = {k: int(row["outputs"][k]) for k in outputs}
            ok, actual_out, depth, _ = simulate_netlist(inputs, outputs, gates, in_vec)
            if not ok:
                sim_ok_all = False
                break
            observed_depth = max(observed_depth, depth)
            if actual_out == expected_out:
                matches += 1

        if sim_ok_all:
            passed_invariants.append("acyclic_well_formed_netlist")
        else:
            failed_invariants.append("acyclic_well_formed_netlist")

        exact_equivalence = sim_ok_all and (matches == len(truth_table))
        if exact_equivalence:
            passed_invariants.append("truth_table_equivalence")
        else:
            failed_invariants.append("truth_table_equivalence")

        within_gate_budget = 0 < len(gates) <= max_gates
        if within_gate_budget:
            passed_invariants.append("gate_budget_satisfied")
        else:
            failed_invariants.append("gate_budget_satisfied")

        within_depth_budget = sim_ok_all and (observed_depth <= max_depth_limit)
        if within_depth_budget:
            passed_invariants.append("timing_depth_satisfied")
        else:
            failed_invariants.append("timing_depth_satisfied")

        verified = (
            sim_ok_all
            and exact_equivalence
            and within_gate_budget
            and within_depth_budget
        )

        accuracy = matches / total_rows if sim_ok_all else 0.0
        efficiency_bonus = (
            max(0.0, 1.0 - (len(gates) / max(max_gates * 2, 1))) if sim_ok_all else 0.0
        )
        reward = 0.85 * accuracy + 0.15 * efficiency_bonus if not verified else 1.0

        cert_payload = json.dumps(
            {
                "task_id": task.task_id,
                "verified": verified,
                "gates": gates,
                "matches": matches,
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
                "matched_rows": matches,
                "total_rows": len(truth_table),
                "gate_count": len(gates),
                "max_gates": max_gates,
                "critical_path_depth": observed_depth,
                "max_depth": max_depth_limit,
            },
            certificate_hash=cert_hash,
        )
