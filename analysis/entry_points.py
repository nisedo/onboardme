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
    # For inherited entry points that are *not* overridden (e.g. PoolV3.depositWithReferral
    # inherited by PoolV3_USDT), the same function object appears under both base and
    # derived contracts. To ensure virtual dispatch is resolved for the *deployed*
    # (most-derived) type, we prefer the most-derived holder.  Example:
    #   root=PoolV3_USDT (contracts/pool/PoolV3_USDT.sol) inherits PoolV3
    #   depositWithReferral declarer is PoolV3, but flow for USDT should be walked
    #   with contract=PoolV3_USDT so that PoolV3.deposit -> _amountMinusFee correctly
    #   resolves to PoolV3_USDT._amountMinusFee.
    #   If root=PoolV3.sol (single-file, USDT not in compilation), USDT is not in
    #   `contracts`, so no effect.  For on-chain (crytic-export) only the deployed
    #   contract + its bases are in `contracts`, so ordering is irrelevant.
    # We sort contracts by inheritance depth descending (most derived first) so the
    # first occurrence kept is the most derived. Depth = len(inheritance) is a
    # good proxy for C3; ties keep original sorted order.
    def _depth(c: Any) -> int:
        try:
            return len(getattr(c, "inheritance", []) or [])
        except Exception:
            return 0

    # Stable sort: most derived first, then name for determinism
    sorted_contracts = sorted(contracts, key=lambda c: (-_depth(c), getattr(c, "name", "")))

    seen: Set[tuple[Any, ...]] = set()
    # Map contract_key -> list to preserve original contract objects for return
    # but we need to return in most-derived-first order for determinism.
    # We will build result keyed by contract object in sorted order.
    result_map: Dict[tuple[str, str], List[Any]] = {}
    contract_obj_map: Dict[tuple[str, str], Any] = {}
    for contract in sorted_contracts:
        contract_key = _contract_key(contract)
        # Ensure we have an entry in result_map for this contract
        if contract_key not in result_map:
            result_map[contract_key] = []
            contract_obj_map[contract_key] = contract
        unique_for_contract = result_map[contract_key]
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

    # Return in most-derived-first order, one entry per contract_key
    added: Set[tuple[str, str]] = set()
    result: List[tuple[Any, List[Any]]] = []
    for contract in sorted_contracts:
        contract_key = _contract_key(contract)
        if contract_key in added:
            continue
        added.add(contract_key)
        result.append((contract_obj_map[contract_key], result_map[contract_key]))
    return result
