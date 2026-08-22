"""Normalization helpers for the PoolV3 golden snapshot.

Flow ORDER is intentionally not compared: Slither's IR traversal order is not
guaranteed to be stable across runs (the same nodes may be emitted in a
different order).  Flow CONTENT (the multiset of resolved nodes) is stable and
is the part that encodes "the right implementation for everything".
"""

from typing import Any, Dict, List


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contract": entry["contract"],
        # Lists (not tuples) so in-memory and JSON-loaded snapshots compare equal.
        "inputs": [[item["name"], item["type"]] for item in entry["inputs"]],
        "outputs": [[item["name"], item["type"]] for item in entry["outputs"]],
        "reads_msg_sender": bool(entry["reads_msg_sender"]),
        "msg_sender_constrained": bool(entry["msg_sender_constrained"]),
        "state_variables_read_keys": sorted(entry["state_variables_read_keys"]),
        "state_variables_written_keys": sorted(
            entry["state_variables_written_keys"]
        ),
        "flow": sorted(
            [
                {
                    "name": item["name"],
                    "contract": item["contract"],
                    "kind": item.get("kind"),
                    "selector": item.get("selector"),
                }
                for item in entry["flow"]
            ],
            key=lambda node: (
                node["name"],
                node["contract"],
                node.get("kind") or "",
                node.get("selector") or "",
            ),
        ),
    }


def normalize_entries(
    entries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Normalize a list of entry dicts into a deterministic snapshot dict."""
    return {
        entry["entry_point"]: _normalize_entry(entry)
        for entry in sorted(entries, key=lambda e: e["entry_point"])
    }


def build_snapshot(
    entries: List[Dict[str, Any]], read_only_entries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "entries": normalize_entries(entries),
        "read_only_entries": normalize_entries(read_only_entries),
    }
