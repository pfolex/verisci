"""`verisci`: Universal Scientific & Formal Verification Cartridges."""

from verisci.cartridges import (
    CARTRIDGE_REGISTRY,
    LogicCartridge,
    MatterCartridge,
    SiliconCartridge,
    SystemsCartridge,
    get_cartridge,
)
from verisci.protocol import ActionStep, Cartridge, DomainTask, VerificationResult


def verify_submission(task: DomainTask, submission: dict) -> VerificationResult:
    """Dispatch `task` and `submission` to the matching domain verifier cartridge."""
    cartridge = get_cartridge(task.domain)
    return cartridge.verify(task, submission)


__all__ = [
    "ActionStep",
    "Cartridge",
    "DomainTask",
    "VerificationResult",
    "CARTRIDGE_REGISTRY",
    "LogicCartridge",
    "SiliconCartridge",
    "SystemsCartridge",
    "MatterCartridge",
    "get_cartridge",
    "verify_submission",
]
