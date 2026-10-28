"""Cartridge Registry (`verisci.cartridges`)."""

from __future__ import annotations

from typing import Dict

from verisci.cartridges.logic import LogicCartridge
from verisci.cartridges.matter import MatterCartridge
from verisci.cartridges.silicon import SiliconCartridge
from verisci.cartridges.systems import SystemsCartridge
from verisci.protocol import Cartridge

CARTRIDGE_REGISTRY: Dict[str, Cartridge] = {
    "logic": LogicCartridge(),
    "silicon": SiliconCartridge(),
    "systems": SystemsCartridge(),
    "matter": MatterCartridge(),
}


def get_cartridge(domain: str) -> Cartridge:
    if domain not in CARTRIDGE_REGISTRY:
        raise KeyError(
            f"Unknown verisci domain '{domain}'. Available: {sorted(CARTRIDGE_REGISTRY)}"
        )
    return CARTRIDGE_REGISTRY[domain]


__all__ = [
    "CARTRIDGE_REGISTRY",
    "LogicCartridge",
    "SiliconCartridge",
    "SystemsCartridge",
    "MatterCartridge",
    "get_cartridge",
]
