"""Universal Verifiable Cartridge Protocol (`verisci.protocol`).

Defines deterministic, zero-dependency data contracts shared across all
scientific and engineering verification cartridges and RLVR environments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ActionStep:
    """A single discrete reasoning, synthesis, or transformation step."""

    action_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "params": dict(self.params),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionStep":
        return cls(
            action_type=str(data["action_type"]),
            params=dict(data.get("params", {})),
            rationale=str(data.get("rationale", "")),
        )


@dataclass
class DomainTask:
    """A verifiable scientific/formal task specification."""

    task_id: str
    domain: str
    difficulty: int
    prompt: str
    spec: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "prompt": self.prompt,
            "spec": self.spec,
            "metadata": self.metadata,
        }


@dataclass
class VerificationResult:
    """Exact formal verification outcome with dense diagnostics and binary proof check."""

    task_id: str
    domain: str
    verified: bool
    reward: float
    passed_invariants: List[str] = field(default_factory=list)
    failed_invariants: List[str] = field(default_factory=list)
    step_validity: List[bool] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    certificate_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "domain": self.domain,
            "verified": self.verified,
            "reward": round(self.reward, 6),
            "passed_invariants": list(self.passed_invariants),
            "failed_invariants": list(self.failed_invariants),
            "step_validity": list(self.step_validity),
            "diagnostics": dict(self.diagnostics),
            "certificate_hash": self.certificate_hash,
        }


class Cartridge(ABC):
    """Abstract base class for pluggable formal & scientific verification cartridges."""

    domain: str = "abstract"

    @abstractmethod
    def verify(self, task: DomainTask, submission: Dict[str, Any]) -> VerificationResult:
        """Deterministically verify a candidate solution against `task.spec`."""

    @abstractmethod
    def evaluate_step(
        self, task: DomainTask, state: Dict[str, Any], step: ActionStep
    ) -> Dict[str, Any]:
        """Apply one incremental step and return updated state + immediate validity."""
