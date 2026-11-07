"""The exported IPC schema covers every method and event, resolves, and is committed up to date."""

from pathlib import Path
from typing import Any

from ace_core.ipc.events import EVENT_PAYLOADS
from ace_core.ipc.export_schema import build_schema, main, render
from ace_core.ipc.methods import METHODS

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_SCHEMA = REPO_ROOT / "apps" / "desktop" / "src" / "ipc" / "ipc.schema.json"


def _refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        found = [node["$ref"]] if isinstance(node.get("$ref"), str) else []
        return found + [ref for value in node.values() for ref in _refs(value)]
    if isinstance(node, list):
        return [ref for value in node for ref in _refs(value)]
    return []


def test_schema_has_every_method_and_event_and_all_refs_resolve() -> None:
    schema = build_schema()
    assert set(schema["properties"]["methods"]["properties"]) == set(METHODS)
    assert set(schema["properties"]["events"]["properties"]) == set(EVENT_PAYLOADS)
    definitions = schema["$defs"]
    for ref in _refs(schema):
        assert ref.startswith("#/$defs/")
        assert ref.removeprefix("#/$defs/") in definitions


def test_committed_schema_is_up_to_date() -> None:
    assert COMMITTED_SCHEMA.read_text(encoding="utf-8") == render(), (
        "regenerate: uv run --project core python -m ace_core.ipc.export_schema "
        "apps/desktop/src/ipc/ipc.schema.json && pnpm --filter ace-desktop gen:ipc"
    )


def test_main_writes_the_file_and_check_detects_staleness(tmp_path: Path) -> None:
    target = tmp_path / "ipc.schema.json"
    assert main([str(target), "--check"]) == 1  # missing
    assert main([str(target)]) == 0
    assert main([str(target), "--check"]) == 0
    target.write_text("{}\n", encoding="utf-8")
    assert main([str(target), "--check"]) == 1  # stale
