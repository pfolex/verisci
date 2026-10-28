"""Computational Matter & Chemistry Cartridge (`verisci.cartridges.matter`).

Deterministically verifies molecular graphs against physical/chemical laws:
1. Exact Atomic Stoichiometry (matches target molecular formula e.g. C2H6O)
2. Covalent Valence Rules (C=4, N=3, O=2, H=1, F=1, Cl=1, S=2, P=3)
3. Connected Single-Component Graph Topology (BFS reachability across all atoms)
4. Target Functional Group / Bond Motif Presence (e.g., carbonyl C=O, hydroxyl O-H,
   nitrile C#N, ring closure count)
"""

from __future__ import annotations

from collections import Counter, deque
import hashlib
import json
from typing import Any, Dict, List, Set, Tuple

from verisci.protocol import ActionStep, Cartridge, DomainTask, VerificationResult

VALENCE_TABLE: Dict[str, int] = {
    "H": 1,
    "F": 1,
    "Cl": 1,
    "Br": 1,
    "I": 1,
    "O": 2,
    "S": 2,
    "N": 3,
    "P": 3,
    "C": 4,
    "Si": 4,
}


def _bond_motif_key(elem_a: str, elem_b: str, order: int) -> str:
    pair = sorted([elem_a, elem_b])
    sep = {1: "-", 2: "=", 3: "#"}.get(order, f"~{order}~")
    return f"{pair[0]}{sep}{pair[1]}"


class MatterCartridge(Cartridge):
    """Computational Chemistry & Molecular Graph Verifier."""

    domain = "matter"

    def evaluate_step(
        self, task: DomainTask, state: Dict[str, Any], step: ActionStep
    ) -> Dict[str, Any]:
        atoms = list(state.get("atoms", []))
        bonds = list(state.get("bonds", []))
        valid_step = False
        reason = "invalid_step"

        if step.action_type == "add_atom":
            el = str(step.params.get("element", ""))
            if el in VALENCE_TABLE:
                atoms.append(el)
                valid_step = True
                reason = "atom_added"
        elif step.action_type == "add_bond":
            u = int(step.params.get("u", -1))
            v = int(step.params.get("v", -1))
            order = int(step.params.get("order", 1))
            if 0 <= u < len(atoms) and 0 <= v < len(atoms) and u != v and 1 <= order <= 3:
                bonds.append({"u": u, "v": v, "order": order})
                valid_step = True
                reason = "bond_added"

        return {
            "atoms": atoms,
            "bonds": bonds,
            "valid_step": valid_step,
            "reason": reason,
        }

    def verify(self, task: DomainTask, submission: Dict[str, Any]) -> VerificationResult:
        spec = task.spec
        target_formula: Dict[str, int] = {
            str(k): int(v) for k, v in spec.get("formula", {}).items()
        }
        required_motifs: List[str] = list(spec.get("required_motifs", []))
        expected_rings = spec.get("expected_rings", None)

        atoms: List[str] = [str(a) for a in submission.get("atoms", [])]
        bonds: List[Dict[str, Any]] = list(submission.get("bonds", []))

        n = len(atoms)
        valence_used = [0] * n
        adj: Dict[int, Set[int]] = {i: set() for i in range(n)}
        seen_pairs: Set[Tuple[int, int]] = set()
        step_validity: List[bool] = []
        observed_motifs: Set[str] = set()
        bonds_well_formed = True

        for b in bonds:
            u = int(b.get("u", -1))
            v = int(b.get("v", -1))
            order = int(b.get("order", 1))
            pair = (min(u, v), max(u, v))
            if (
                0 <= u < n
                and 0 <= v < n
                and u != v
                and 1 <= order <= 3
                and pair not in seen_pairs
                and atoms[u] in VALENCE_TABLE
                and atoms[v] in VALENCE_TABLE
            ):
                seen_pairs.add(pair)
                valence_used[u] += order
                valence_used[v] += order
                adj[u].add(v)
                adj[v].add(u)
                observed_motifs.add(_bond_motif_key(atoms[u], atoms[v], order))
                step_validity.append(True)
            else:
                bonds_well_formed = False
                step_validity.append(False)

        # 1. Stoichiometry check
        actual_counts = dict(Counter(atoms))
        stoichiometry_ok = actual_counts == target_formula

        # 2. Valence satisfaction check
        satisfied_atoms = 0
        for i, el in enumerate(atoms):
            if VALENCE_TABLE.get(el, -1) == valence_used[i]:
                satisfied_atoms += 1
        valence_ok = n > 0 and (satisfied_atoms == n) and bonds_well_formed

        # 3. Connected graph check (single molecule)
        connected_ok = False
        if n > 0:
            visited: Set[int] = {0}
            queue: deque[int] = deque([0])
            while queue:
                curr = queue.popleft()
                for nxt in adj[curr]:
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            connected_ok = len(visited) == n

        # 4. Functional motif & ring count check
        normalized_required = set()
        for m in required_motifs:
            if "=" in m:
                p = m.split("=")
                normalized_required.add(_bond_motif_key(p[0], p[1], 2))
            elif "#" in m:
                p = m.split("#")
                normalized_required.add(_bond_motif_key(p[0], p[1], 3))
            elif "-" in m:
                p = m.split("-")
                normalized_required.add(_bond_motif_key(p[0], p[1], 1))

        motifs_ok = normalized_required.issubset(observed_motifs)

        # Cyclomatic number: rings = |E| - |V| + 1 for a connected graph
        cyclomatic_rings = len(seen_pairs) - n + 1 if connected_ok else -1
        rings_ok = (
            True
            if expected_rings is None
            else (connected_ok and cyclomatic_rings == int(expected_rings))
        )

        passed_invariants: List[str] = []
        failed_invariants: List[str] = []

        for name, cond in [
            ("stoichiometry_conservation", stoichiometry_ok),
            ("covalent_valence_exact", valence_ok),
            ("single_connected_molecule", connected_ok),
            ("functional_motifs_present", motifs_ok and rings_ok),
        ]:
            if cond:
                passed_invariants.append(name)
            else:
                failed_invariants.append(name)

        verified = len(failed_invariants) == 0
        valence_ratio = satisfied_atoms / max(n, 1)
        reward = (
            0.30 * (1.0 if stoichiometry_ok else 0.0)
            + 0.35 * valence_ratio
            + 0.20 * (1.0 if connected_ok else 0.0)
            + 0.15 * (1.0 if (motifs_ok and rings_ok) else 0.0)
        )
        if verified:
            reward = 1.0

        cert_payload = json.dumps(
            {
                "task_id": task.task_id,
                "verified": verified,
                "atoms": atoms,
                "bonds": sorted(list(seen_pairs)),
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
                "atom_count": n,
                "bond_count": len(seen_pairs),
                "satisfied_valence_atoms": satisfied_atoms,
                "cyclomatic_rings": max(0, cyclomatic_rings),
                "observed_motifs": sorted(observed_motifs),
            },
            certificate_hash=cert_hash,
        )
