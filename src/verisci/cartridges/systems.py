"""Systems & Concurrency Cartridge (`verisci.cartridges.systems`).

Deterministically model-checks concurrent protocol schedules and distributed
state-machine traces (locks, compare-and-swap, Lamport logical clocks, and
bounded message buffers) against safety and liveness invariants:
1. Mutual Exclusion (never >1 worker in critical section simultaneously)
2. Lock Ownership Discipline (only holder may release; no double-acquire without release)
3. Lamport Monotonicity (causal logical clocks strictly advance on send/recv/local step)
4. Deadlock-Free / Clean Termination (all locks released & all target work units committed)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Set

from verisci.protocol import ActionStep, Cartridge, DomainTask, VerificationResult


class SystemsCartridge(Cartridge):
    """Concurrent & Distributed State Machine Protocol Verifier."""

    domain = "systems"

    def evaluate_step(
        self, task: DomainTask, state: Dict[str, Any], step: ActionStep
    ) -> Dict[str, Any]:
        events = list(state.get("events", []))
        ev = dict(step.params)
        ev["op"] = step.action_type
        events.append(ev)
        return {
            "events": events,
            "valid_step": True,
            "reason": "event_appended",
        }

    def verify(self, task: DomainTask, submission: Dict[str, Any]) -> VerificationResult:
        spec = task.spec
        num_workers = int(spec.get("num_workers", 2))
        required_commits = int(spec.get("required_commits", 2))
        resources: List[str] = list(spec.get("resources", ["lock_A"]))
        max_buffer = int(spec.get("max_buffer", 4))

        events: List[Dict[str, Any]] = list(submission.get("events", []))

        lock_holder: Dict[str, int | None] = {r: None for r in resources}
        in_cs: Set[int] = set()
        worker_clock: Dict[int, int] = {w: 0 for w in range(num_workers)}
        msg_clocks: Dict[str, int] = {}
        buffer_occupancy = 0

        mutex_ok = True
        lock_discipline_ok = True
        lamport_ok = True
        buffer_bounds_ok = True
        commits = 0
        worker_commits: Dict[int, int] = {w: 0 for w in range(num_workers)}
        step_validity: List[bool] = []

        for ev in events:
            op = str(ev.get("op", ""))
            worker = int(ev.get("worker", -1))
            clock = int(ev.get("clock", 0))
            res = str(ev.get("resource", resources[0] if resources else "lock_A"))
            step_ok = True

            if worker < 0 or worker >= num_workers:
                step_ok = False
                lock_discipline_ok = False
            else:
                if clock <= worker_clock[worker]:
                    lamport_ok = False
                    step_ok = False
                worker_clock[worker] = max(worker_clock[worker], clock)

            if op == "acquire":
                if res not in lock_holder or lock_holder[res] is not None:
                    lock_discipline_ok = False
                    mutex_ok = False
                    step_ok = False
                else:
                    lock_holder[res] = worker
                    in_cs.add(worker)
                    if len(in_cs) > 1 and len(resources) == 1:
                        mutex_ok = False
                        step_ok = False

            elif op == "critical_commit":
                # Worker must hold all required locks for this task
                if any(lock_holder.get(r) != worker for r in resources):
                    mutex_ok = False
                    lock_discipline_ok = False
                    step_ok = False
                else:
                    commits += 1
                    if 0 <= worker < num_workers:
                        worker_commits[worker] += 1

            elif op == "release":
                if res not in lock_holder or lock_holder[res] != worker:
                    lock_discipline_ok = False
                    step_ok = False
                else:
                    lock_holder[res] = None
                    if all(lock_holder.get(r) != worker for r in resources):
                        in_cs.discard(worker)

            elif op == "send":
                msg_id = str(ev.get("msg_id", ""))
                msg_clocks[msg_id] = clock
                buffer_occupancy += 1
                if buffer_occupancy > max_buffer:
                    buffer_bounds_ok = False
                    step_ok = False

            elif op == "recv":
                msg_id = str(ev.get("msg_id", ""))
                if msg_id not in msg_clocks or clock <= msg_clocks[msg_id]:
                    lamport_ok = False
                    step_ok = False
                else:
                    buffer_occupancy = max(0, buffer_occupancy - 1)

            else:
                step_ok = False

            step_validity.append(step_ok)

        all_locks_released = all(v is None for v in lock_holder.values())
        liveness_met = (commits >= required_commits) and all(
            worker_commits[w] >= 1 for w in range(num_workers)
        )
        clean_termination = all_locks_released and (buffer_occupancy == 0)

        passed_invariants: List[str] = []
        failed_invariants: List[str] = []

        for name, cond in [
            ("mutual_exclusion", mutex_ok and len(events) > 0),
            ("lock_ownership_discipline", lock_discipline_ok and len(events) > 0),
            ("lamport_causal_monotonicity", lamport_ok and len(events) > 0),
            ("bounded_buffer_safety", buffer_bounds_ok),
            ("liveness_quorum_commits", liveness_met),
            ("deadlock_free_clean_termination", clean_termination and len(events) > 0),
        ]:
            if cond:
                passed_invariants.append(name)
            else:
                failed_invariants.append(name)

        verified = len(failed_invariants) == 0
        reward = len(passed_invariants) / 6.0 if not verified else 1.0

        cert_payload = json.dumps(
            {
                "task_id": task.task_id,
                "verified": verified,
                "commits": commits,
                "passed": passed_invariants,
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
                "total_events": len(events),
                "commits_completed": commits,
                "required_commits": required_commits,
                "all_locks_released": all_locks_released,
                "residual_buffer": buffer_occupancy,
            },
            certificate_hash=cert_hash,
        )
