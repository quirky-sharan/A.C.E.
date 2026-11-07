"""Prints the skill registry as one JSON Schema document (S07 task 2). From ``core/``:

uv run python -m ace_core.skills.export_schema [--dev] [output.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import JsonValue

from ace_core.db.stores import Actor
from ace_core.skills.catalog import build_registry


class _NoSettings:
    """Building the schema never runs a skill, so no settings store is needed."""

    async def get(self, key: str, default: JsonValue = None) -> JsonValue:
        raise RuntimeError("not available while exporting the schema")

    async def set(self, key: str, value: JsonValue, *, actor: Actor = "system") -> None:
        raise RuntimeError("not available while exporting the schema")


def render(*, dev: bool) -> str:
    registry = build_registry(settings=_NoSettings(), dev=dev)
    return json.dumps(registry.json_schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the ACE skill registry as JSON Schema.")
    parser.add_argument("--dev", action="store_true", help="include the dev-only demo skills")
    parser.add_argument("output", nargs="?", type=Path, help="write here instead of stdout")
    args = parser.parse_args(argv)
    text = render(dev=args.dev)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
