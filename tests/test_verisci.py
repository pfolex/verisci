"""Comprehensive unit test suite for `verisci` across all 4 domains."""

from __future__ import annotations

import unittest

from verisci import (
    ActionStep,
    CARTRIDGE_REGISTRY,
    DomainTask,
    get_cartridge,
    verify_submission,
)


class TestVeriSciCartridges(unittest.TestCase):
    def test_registry_contains_four_domains(self) -> None:
        self.assertEqual(
            sorted(CARTRIDGE_REGISTRY.keys()),
            ["logic", "matter", "silicon", "systems"],
        )

    def test_logic_cartridge_valid_and_invalid_proofs(self) -> None:
        task = DomainTask(
            task_id="logic-mp-chain",
            domain="logic",
            difficulty=3,
            prompt="Derive C from A, ~A v B, ~B v C and provide a satisfying assignment.",
            spec={
                "variables": ["A", "B", "C"],
                "premises": [["A"], ["~A", "B"], ["~B", "C"]],
                "goal_clause": ["C"],
                "require_sat": True,
            },
        )
        valid_sub = {
            "proof_steps": [
                {"p1": 0, "p2": 1, "conclusion": ["B"]},
                {"p1": 3, "p2": 2, "conclusion": ["C"]},
            ],
            "assignment": {"A": True, "B": True, "C": True},
        }
        res = verify_submission(task, valid_sub)
        self.assertTrue(res.verified)
        self.assertAlmostEqual(res.reward, 1.0)
        self.assertEqual(res.step_validity, [True, True])

        # Invalid inference step and wrong assignment
        invalid_sub = {
            "proof_steps": [
                {"p1": 0, "p2": 2, "conclusion": ["C"]},
            ],
            "assignment": {"A": False, "B": False, "C": False},
        }
        bad_res = verify_submission(task, invalid_sub)
        self.assertFalse(bad_res.verified)
        self.assertLess(bad_res.reward, 0.5)
        self.assertIn("goal_clause_derived", bad_res.failed_invariants)

    def test_silicon_cartridge_full_adder_equivalence(self) -> None:
        # Full adder: sum = a ^ b ^ cin, cout = (a & b) | (cin & (a ^ b))
        truth_table = []
        for a in (0, 1):
            for b in (0, 1):
                for cin in (0, 1):
                    s = a ^ b ^ cin
                    cout = (a & b) | (cin & (a ^ b))
                    truth_table.append(
                        {
                            "inputs": {"a": a, "b": b, "cin": cin},
                            "outputs": {"sum": s, "cout": cout},
                        }
                    )

        task = DomainTask(
            task_id="silicon-full-adder",
            domain="silicon",
            difficulty=4,
            prompt="Synthesize a 1-bit Full Adder netlist.",
            spec={
                "inputs": ["a", "b", "cin"],
                "outputs": ["sum", "cout"],
                "truth_table": truth_table,
                "max_gates": 6,
                "max_depth": 4,
            },
        )
        valid_netlist = {
            "gates": [
                {"op": "XOR", "ins": ["a", "b"], "out": "w_ab_xor"},
                {"op": "XOR", "ins": ["w_ab_xor", "cin"], "out": "sum"},
                {"op": "AND", "ins": ["a", "b"], "out": "w_ab_and"},
                {"op": "AND", "ins": ["w_ab_xor", "cin"], "out": "w_cin_and"},
                {"op": "OR", "ins": ["w_ab_and", "w_cin_and"], "out": "cout"},
            ]
        }
        res = verify_submission(task, valid_netlist)
        self.assertTrue(res.verified)
        self.assertEqual(res.diagnostics["matched_rows"], 8)
        self.assertEqual(res.diagnostics["critical_path_depth"], 3)

        # Buggy netlist (OR instead of XOR for sum)
        buggy_netlist = {
            "gates": [
                {"op": "OR", "ins": ["a", "b"], "out": "sum"},
                {"op": "AND", "ins": ["a", "b"], "out": "cout"},
            ]
        }
        bad_res = verify_submission(task, buggy_netlist)
        self.assertFalse(bad_res.verified)
        self.assertIn("truth_table_equivalence", bad_res.failed_invariants)

    def test_systems_cartridge_mutex_and_lamport_verification(self) -> None:
        task = DomainTask(
            task_id="systems-mutex-2w",
            domain="systems",
            difficulty=4,
            prompt="Verify 2-worker mutual exclusion with Lamport clocks.",
            spec={
                "num_workers": 2,
                "required_commits": 2,
                "resources": ["lock_A"],
                "max_buffer": 2,
            },
        )
        valid_schedule = {
            "events": [
                {"op": "acquire", "worker": 0, "resource": "lock_A", "clock": 1},
                {"op": "critical_commit", "worker": 0, "clock": 2},
                {"op": "release", "worker": 0, "resource": "lock_A", "clock": 3},
                {"op": "send", "worker": 0, "msg_id": "m1", "clock": 4},
                {"op": "recv", "worker": 1, "msg_id": "m1", "clock": 5},
                {"op": "acquire", "worker": 1, "resource": "lock_A", "clock": 6},
                {"op": "critical_commit", "worker": 1, "clock": 7},
                {"op": "release", "worker": 1, "resource": "lock_A", "clock": 8},
            ]
        }
        res = verify_submission(task, valid_schedule)
        self.assertTrue(res.verified)
        self.assertAlmostEqual(res.reward, 1.0)

        # Violate mutual exclusion: worker 1 acquires before worker 0 releases
        race_schedule = {
            "events": [
                {"op": "acquire", "worker": 0, "resource": "lock_A", "clock": 1},
                {"op": "acquire", "worker": 1, "resource": "lock_A", "clock": 1},
                {"op": "critical_commit", "worker": 0, "clock": 2},
            ]
        }
        bad_res = verify_submission(task, race_schedule)
        self.assertFalse(bad_res.verified)
        self.assertIn("mutual_exclusion", bad_res.failed_invariants)

    def test_matter_cartridge_ethanol_and_invalid_valence(self) -> None:
        # Acetaldehyde (C2H4O): CH3-CH=O (contains C=O motif, 0 rings)
        task = DomainTask(
            task_id="matter-acetaldehyde",
            domain="matter",
            difficulty=4,
            prompt="Construct molecular graph for C2H4O with a carbonyl C=O double bond.",
            spec={
                "formula": {"C": 2, "H": 4, "O": 1},
                "required_motifs": ["C=O", "C-C"],
                "expected_rings": 0,
            },
        )
        # Atoms: 0:C, 1:C, 2:O, 3:H, 4:H, 5:H, 6:H
        valid_molecule = {
            "atoms": ["C", "C", "O", "H", "H", "H", "H"],
            "bonds": [
                {"u": 0, "v": 1, "order": 1},  # C-C
                {"u": 1, "v": 2, "order": 2},  # C=O
                {"u": 0, "v": 3, "order": 1},  # C-H
                {"u": 0, "v": 4, "order": 1},  # C-H
                {"u": 0, "v": 5, "order": 1},  # C-H
                {"u": 1, "v": 6, "order": 1},  # C-H
            ],
        }
        res = verify_submission(task, valid_molecule)
        self.assertTrue(res.verified)
        self.assertAlmostEqual(res.reward, 1.0)

        # Invalid Texas Carbon (5 bonds on C0)
        texas_carbon = {
            "atoms": ["C", "C", "O", "H", "H", "H", "H"],
            "bonds": [
                {"u": 0, "v": 1, "order": 2},
                {"u": 1, "v": 2, "order": 2},
                {"u": 0, "v": 3, "order": 1},
                {"u": 0, "v": 4, "order": 1},
                {"u": 0, "v": 5, "order": 1},
                {"u": 1, "v": 6, "order": 1},
            ],
        }
        bad_res = verify_submission(task, texas_carbon)
        self.assertFalse(bad_res.verified)
        self.assertIn("covalent_valence_exact", bad_res.failed_invariants)

    def test_incremental_evaluate_step_protocol(self) -> None:
        cart = get_cartridge("silicon")
        task = DomainTask(
            task_id="step-test",
            domain="silicon",
            difficulty=1,
            prompt="AND gate",
            spec={"inputs": ["a", "b"], "outputs": ["y"], "truth_table": []},
        )
        state = cart.evaluate_step(
            task,
            {"gates": []},
            ActionStep("add_gate", {"op": "AND", "ins": ["a", "b"], "out": "y"}),
        )
        self.assertTrue(state["valid_step"])
        self.assertEqual(len(state["gates"]), 1)


if __name__ == "__main__":
    unittest.main()
