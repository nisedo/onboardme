"""Shared helpers for the backend test suite."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

DATA_DIR = Path(__file__).parent / "data"


def snapshot_path_for(target: Dict[str, Any]) -> Path:
    """Golden snapshot file for a registered target."""
    return DATA_DIR / f"{target['id']}_snapshot.json"


def compare_or_update_snapshot(
    target: Dict[str, Any], snapshot: Dict[str, Any], request: Any
) -> None:
    """Compare against the golden snapshot, or regenerate it with
    ``--snapshot-update``."""
    path = snapshot_path_for(target)
    if request.config.getoption("--snapshot-update"):
        path.write_text(
            json.dumps(snapshot, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"snapshot regenerated: {path}")

    expected = json.loads(path.read_text(encoding="utf-8"))
    assert snapshot == expected, (
        f"Full-flow snapshot mismatch for {target['id']}. If the code change "
        "was intentional, review the diff, verify the new behavior is the "
        "correct interpretation of the immutable on-chain contract, and "
        f"update the snapshot with: pytest tests/ --snapshot-update"
    )


def skip_unless_target(target: Dict[str, Any], target_id: str) -> None:
    """Skip contract-specific assertions when the suite runs other targets."""
    if target["id"] != target_id:
        pytest.skip(
            f"contract-specific assertions apply to {target_id} only"
        )


def entry_function_name(entry_point: str) -> tuple[str, str]:
    """"Contract.foo(uint256)" -> ("Contract", "foo")."""
    declarer, rest = entry_point.split(".", 1)
    return declarer, rest.split("(")[0]


def is_getter_entry(entry: Dict[str, Any], root_contract: Any) -> bool:
    """True when the entry point is an auto-generated public state-variable
    getter modeled by Slither as a bodyless interface function."""
    flow = entry["flow"]
    if len(flow) != 1 or flow[0]["name"] != entry["entry_point"]:
        return False
    _, name = entry_function_name(entry["entry_point"])
    return any(
        getattr(var, "name", None) == name
        and getattr(var, "visibility", "") == "public"
        for var in getattr(root_contract, "state_variables", []) or []
    )


def getter_state_var_key(entry_point: str, root_contract: Any) -> str | None:
    """Expected qualified state-variable key for a getter entry point."""
    _, name = entry_function_name(entry_point)
    for var in getattr(root_contract, "state_variables", []) or []:
        if (
            getattr(var, "name", None) == name
            and getattr(var, "visibility", "") == "public"
        ):
            contract = getattr(var, "contract", None) or getattr(
                var, "contract_declarer", None
            )
            contract_name = getattr(contract, "name", "") if contract else ""
            return f"{contract_name}.{name}" if contract_name else name
    return None
