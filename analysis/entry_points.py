"""Helpers for enumerating entry points without duplicate inherited callables."""

from __future__ import annotations

from collections import defaultdict
from functools import cmp_to_key
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
    overridden_sigs: DefaultDict[tuple, Set[str]] = defaultdict(set)
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

        # C3-based override detection fallback: in flattened verification
        # bundles the is_shadowed flag can be unreliable, so also mark a base
        # signature as overridden when a derived contract declares a public/
        # external function with the same signature while inheriting that base
        # (Solidity forces an override relationship in this situation, so this
        # can never misfire on unrelated same-name private functions).
        for fn in getattr(contract, "functions_declared", []) or []:
            if getattr(fn, "visibility", "") not in ("public", "external"):
                continue
            if getattr(fn, "is_constructor", False):
                continue
            sig = _entry_point_signature(fn)
            if not sig or sig == "<unknown>":
                continue
            for base in getattr(contract, "inheritance", []) or []:
                base_key = _contract_key(base)
                if base_key == derived_key:
                    continue
                if any(
                    _entry_point_signature(b) == sig
                    for b in getattr(base, "functions", []) or []
                ):
                    overridden_sigs[base_key].add(sig)

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
    #
    # Ordering is STRICT C3 linearization, never alphabetical:
    #   - When the audited set forms one chain (a single most-derived contract
    #     whose inheritance contains every other member - the production case,
    #     since the tool always analyzes one root at a time), contracts are
    #     ordered by their exact position in solc's C3 linearization
    #     ([root] + root.inheritance, as materialized by Slither).
    #   - Otherwise derived-before-base is enforced by ancestor relation.
    #   - Incomparable contracts (unrelated roots) are ordered by declaration
    #     position in source (file + byte offset) - deterministic and never
    #     alphabetical, so it can never depend on contract names.
    def _ancestor_of(a: Any, b: Any) -> bool:
        """True if `a` is an ancestor (base) of `b` in b's C3 linearization."""
        try:
            return a in (getattr(b, "inheritance", None) or [])
        except Exception:
            return False

    def _structural_key(c: Any) -> tuple:
        """Deterministic declaration-position key, independent of names."""
        try:
            sm = getattr(c, "source_mapping", None)
            filename = getattr(getattr(sm, "filename", None), "absolute", "") or ""
            start = getattr(sm, "start", None)
            return (filename, start if isinstance(start, int) else -1)
        except Exception:
            return ("", -1)

    # Strict C3 linearization index when the audited set forms a single chain.
    chain_index: Dict[int, int] | None = None
    for candidate in contracts:
        others = [o for o in contracts if o is not candidate]
        if others and all(o in (getattr(candidate, "inheritance", None) or []) for o in others):
            chain = [candidate] + list(getattr(candidate, "inheritance", None) or [])
            chain_index = {id(c): i for i, c in enumerate(chain)}
            break

    def _c3_compare(a: Any, b: Any) -> int:
        if chain_index is not None:
            ia = chain_index.get(id(a), 10 ** 9)
            ib = chain_index.get(id(b), 10 ** 9)
            if ia != ib:
                return -1 if ia < ib else 1
            return 0
        if _ancestor_of(a, b):
            return 1  # b more derived => b first
        if _ancestor_of(b, a):
            return -1  # a more derived => a first
        # Incomparable: strict deterministic declaration order, never names.
        ka, kb = _structural_key(a), _structural_key(b)
        if ka != kb:
            return -1 if ka < kb else 1
        return 0

    sorted_contracts = sorted(contracts, key=cmp_to_key(_c3_compare))

    seen: Set[tuple[Any, ...]] = set()
    # Map contract_key -> list to preserve original contract objects for return
    result_map: Dict[tuple, List[Any]] = {}
    contract_obj_map: Dict[tuple, Any] = {}
    for contract in sorted_contracts:
        contract_key = _contract_key(contract)
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
    added: Set[tuple] = set()
    result: List[tuple[Any, List[Any]]] = []
    for contract in sorted_contracts:
        contract_key = _contract_key(contract)
        if contract_key in added:
            continue
        added.add(contract_key)
        result.append((contract_obj_map[contract_key], result_map[contract_key]))
    return result
