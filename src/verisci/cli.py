"""CLI entrypoint for `verisci` formal verification cartridges."""

from __future__ import annotations

import argparse
import json
import sys

from verisci import CARTRIDGE_REGISTRY, DomainTask, verify_submission


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verisci",
        description="Universal Scientific & Formal Verification Cartridges",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("domains", help="List available formal verification cartridges")

    verify_p = sub.add_parser("verify", help="Verify a JSON task + submission payload")
    verify_p.add_argument("payload", help="Path to JSON file with 'task' and 'submission'")

    args = parser.parse_args(argv)
    if args.cmd == "domains":
        print(json.dumps({"domains": sorted(CARTRIDGE_REGISTRY.keys())}, indent=2))
        return 0
    if args.cmd == "verify":
        with open(args.payload, "r", encoding="utf-8") as f:
            data = json.load(f)
        task_dict = data["task"]
        task = DomainTask(
            task_id=task_dict["task_id"],
            domain=task_dict["domain"],
            difficulty=int(task_dict.get("difficulty", 1)),
            prompt=task_dict.get("prompt", ""),
            spec=task_dict["spec"],
        )
        res = verify_submission(task, data["submission"])
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.verified else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
