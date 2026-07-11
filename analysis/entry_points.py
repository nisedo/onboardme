"""Helpers for enumerating entry points without duplicate inherited callables."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List, Sequence, Set

from analysis.slither_extract import _contract_key


def _entry_point_signature(entry_point: Any) -> str:
    """Return a stable function-level signature for comparing across contracts."""
    return (
        getattr(entry_point, "solidity_signature", None)
        or getattr(entry_point, "full_name", None)
        or getattr(entry_point, "name", None)
        or "<unknown>"
    )


def entry_point_identity(entry_point: Any) -> tuple[Any, ...]:
    """
    Build a stable per-run identity for an entry point.

    The same inherited callable can surface while iterating both a root contract and one of its
    concrete bases. Prefer a semantic key based on declarer + source mapping so we can drop the
    duplicate without losing distinct overloads or overrides.
    """
    source_mapping = getattr(entry_point, "source_mapping", None)
    filename = ""
    start = None
    length = None
    if source_mapping is not None:
        filename_obj = getattr(source_mapping, "filename", None)
        filename = (
            getattr(filename_obj, "absolute", "")
            or getattr(filename_obj, "relative", "")
            or getattr(filename_obj, "short", "")
            or str(filename_obj or "")
        )
        raw_start = getattr(source_mapping, "start", None)
        raw_length = getattr(source_mapping, "length", None)
        start = raw_start if isinstance(raw_start, int) else None
        length = raw_length if isinstance(raw_length, int) else None

    declarer = getattr(entry_point, "contract_declarer", None) or getattr(entry_point, "contract", None)
    declarer_name = getattr(declarer, "name", "") or ""
    signature = _entry_point_signature(entry_point)

    if filename or start is not None or length is not None:
        return (
            declarer_name,
            signature,
            filename,
            start,
            length,
        )

    return (
        declarer_name,
        signature,
        id(entry_point),
    )


def collect_unique_entry_points(
    contracts: Sequence[Any],
    entry_points_fn: Callable[[Any], List[Any]],
) -> List[tuple[Any, List[Any]]]:
    """Collect entry points once even if inherited functions surface on multiple contracts.

    Also filters out functions from base contracts that are overridden by a more derived
    contract in the same audited set, so that only the most-derived (i.e. the actual
    implementation) version of each entry point is kept.

    Override detection uses Slither's ``is_shadowed`` flag on the *raw* functions of each
    derived contract (not the filtered entry-point list, which already drops shadowed
    functions).  Only public/external shadowed functions whose ``contract_declarer`` is a
    different (base) contract in the audited set are treated as overrides.
    """
    # ── Detect overrides via shadowed functions in derived contracts  ─────────
    # Keyed by (base_contract_key) → set of overridden signatures.
    # We iterate every contract's raw functions: a function marked is_shadowed=True
    # means something further down the inheritance chain replaced it.
    overridden_sigs: DefaultDict[tuple[str, str], Set[str]] = defaultdict(set)
    for contract in contracts:
        derived_key = _contract_key(contract)
        for fn in getattr(contract, "functions", []) or []:
            if not getattr(fn, "is_shadowed", False):
                continue
            if getattr(fn, "visibility", "") not in ("public", "external"):
                continue
            if getattr(fn, "is_constructor", False):
                continue
            declarer = getattr(fn, "contract_declarer", None) or getattr(fn, "contract", None)
            if declarer is None:
                continue
            declarer_key = _contract_key(declarer)
            if declarer_key == derived_key:
                continue  # shouldn't happen for a truly shadowed function
            sig = _entry_point_signature(fn)
            overridden_sigs[declarer_key].add(sig)

    # ── Collect unique entry points, skipping those overridden by a child  ───
    seen: Set[tuple[Any, ...]] = set()
    result: List[tuple[Any, List[Any]]] = []
    for contract in contracts:
        contract_key = _contract_key(contract)
        unique_for_contract: List[Any] = []
        for entry_point in entry_points_fn(contract):
            key = entry_point_identity(entry_point)
            if key in seen:
                continue
            sig = _entry_point_signature(entry_point)
            if sig in overridden_sigs.get(contract_key, ()):
                seen.add(key)
                continue
            seen.add(key)
            unique_for_contract.append(entry_point)
        result.append((contract, unique_for_contract))
    return result
