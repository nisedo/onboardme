"""Flow traversal and dependency extraction helpers."""

from __future__ import annotations

import re
from collections import deque
from itertools import chain
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, Set, Union

from slither.analyses.data_dependency.data_dependency import compute_dependency, is_dependent
from slither.core.cfg.node import NodeType
from slither.core.declarations import Contract, FunctionContract
from slither.core.declarations.function import Function
from slither.core.declarations.modifier import Modifier
from slither.core.declarations.solidity_variables import SolidityFunction, SolidityVariableComposed
from slither.core.variables.local_variable import LocalVariable
from slither.core.variables.state_variable import StateVariable
from slither.slithir.operations.condition import Condition
from slither.slithir.operations.high_level_call import HighLevelCall
from slither.slithir.operations.index import Index
from slither.slithir.operations.internal_call import InternalCall
from slither.slithir.operations.library_call import LibraryCall
from slither.slithir.operations.low_level_call import LowLevelCall
from slither.slither import Slither
from slither.utils.code_complexity import compute_cyclomatic_complexity
from slither.utils.tests_pattern import is_test_file

from analysis.entry_points import collect_unique_entry_points
from analysis.slither_extract import (
    _contract_key,
    _display_name,
    _function_selector,
    _source_text,
)
from analysis.state_vars import (
    _collect_local_and_param_vars,
    _collect_state_vars,
    _collect_state_vars_via_storage_params,
    _state_var_record,
)

ProgressCallback = Callable[[str, Dict[str, Any] | None], None]

_MSG_SENDER = SolidityVariableComposed("msg.sender")
_REQUIRE_ASSERT_NAMES = {
    "require(bool)",
    "require(bool,string)",
    "require(bool,error)",
    "assert(bool)",
}

_INDEX_DEPS_CACHE: Dict[int, List[tuple[Any, Any]]] = {}
_SENDER_DEP_CACHE: Dict[tuple[int, int], bool] = {}
_INTERNAL_CALL_DEPS_CACHE: Dict[int, List[tuple[Any, Union[Function, Modifier]]]] = {}
_CALLABLE_RETURN_SENDER_DEP_CACHE: Dict[int, bool] = {}
_GUARDED_PARAM_KINDS_CACHE: Dict[int, Dict[int, tuple[str, ...]]] = {}


def _report_progress(callback: ProgressCallback | None, message: str, **meta: Any) -> None:
    """Best-effort progress reporting."""
    if not callback:
        return
    try:
        callback(message, meta or None)
    except Exception:
        pass


def _collect_entry_point_inputs(entry_point: Function) -> List[Dict[str, str]]:
    """Extract parameter names/types for UI rendering (read-only call form)."""
    inputs: List[Dict[str, str]] = []
    for param in (getattr(entry_point, "parameters", None) or []):
        name = (getattr(param, "name", "") or "").strip()
        typ = str(getattr(param, "type", "") or "").strip()
        inputs.append({"name": name, "type": typ})
    return inputs


def _collect_entry_point_outputs(entry_point: Function) -> List[Dict[str, str]]:
    """Extract return names/types for UI decoding (read-only call results)."""
    outputs: List[Dict[str, str]] = []

    # Slither typically exposes `returns` (list of variables) for function return values.
    returns = getattr(entry_point, "returns", None)
    if isinstance(returns, list):
        for ret in returns:
            name = (getattr(ret, "name", "") or "").strip()
            typ = str(getattr(ret, "type", "") or "").strip()
            if typ:
                outputs.append({"name": name, "type": typ})
        return outputs

    # Fallbacks: different Slither versions may use `return_type`.
    return_type = getattr(entry_point, "return_type", None)
    if return_type is None:
        return outputs
    if isinstance(return_type, list):
        for idx, typ in enumerate(return_type):
            t = str(typ or "").strip()
            if t:
                outputs.append({"name": f"ret{idx}", "type": t})
        return outputs

    t = str(return_type or "").strip()
    if t:
        outputs.append({"name": "ret0", "type": t})
    return outputs


def _var_display(var: Any) -> str:
    """Readable label for variables in dependency output."""
    if isinstance(var, SolidityVariableComposed):
        return str(var)
    contract = getattr(var, "contract", None) or getattr(var, "contract_declarer", None)
    prefix = f"{contract.name}." if contract and getattr(var, "name", None) else ""
    return f"{prefix}{getattr(var, 'name', str(var))}"


def _collect_data_dependencies(callable_item: Union[Function, Modifier]) -> List[Dict[str, str]]:
    """
    Return dependency edges (dependent -> depends_on) for variables reachable from the entry point.
    Includes state variables and locals as dependents; parameters/state/locals/Solidity vars as sources.
    """
    contract = getattr(callable_item, "contract", None)
    state_vars = list(getattr(contract, "state_variables", [])) if contract else []
    params = list(getattr(callable_item, "parameters", []))
    locals_vars = list(getattr(callable_item, "local_variables", []))
    solidity_sources = [
        SolidityVariableComposed("msg.sender"),
        SolidityVariableComposed("msg.value"),
        SolidityVariableComposed("tx.origin"),
    ]

    param_set = set(params)

    def _var_scope(var: Any) -> str:
        """Classify variable storage scope."""
        if isinstance(var, SolidityVariableComposed):
            return "solidity_builtin"
        if isinstance(var, StateVariable):
            return "state"
        if isinstance(var, LocalVariable):
            return "parameter" if var in param_set else "local"
        # Fallback using best-effort attributes
        if getattr(var, "is_state_variable", False):
            return "state"
        return "unknown"

    dependents = state_vars + locals_vars
    sources = state_vars + params + locals_vars + solidity_sources

    edges: List[Dict[str, str]] = []
    seen: Set[tuple] = set()

    for dest in dependents:
        for src in sources:
            if dest is src:
                continue
            try:
                if is_dependent(dest, src, callable_item):
                    key = (_var_display(dest), _var_display(src))
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "dependent": _var_display(dest),
                            "dependent_type": str(getattr(dest, "type", "")),
                            "dependent_scope": _var_scope(dest),
                            "depends_on": _var_display(src),
                            "depends_on_type": str(getattr(src, "type", "")),
                            "depends_on_scope": _var_scope(src),
                        }
                    )
            except Exception:
                # Best-effort: skip problematic dependency checks without aborting whole analysis.
                continue

    return sorted(
        edges,
        key=lambda edge: (
            edge.get("dependent", ""),
            edge.get("depends_on", ""),
            edge.get("dependent_type", ""),
            edge.get("depends_on_type", ""),
            edge.get("dependent_scope", ""),
            edge.get("depends_on_scope", ""),
        ),
    )


def _source_location(item: Any) -> Dict[str, Any]:
    """Best-effort source location record for a Slither element (node, function, etc.)."""
    sm = getattr(item, "source_mapping", None)
    filename = ""
    lines: List[int] = []
    if sm is not None:
        try:
            filename_obj = getattr(sm, "filename", None)
            filename = (
                getattr(filename_obj, "relative", "")
                or getattr(filename_obj, "short", "")
                or getattr(filename_obj, "absolute", "")
                or str(filename_obj or "")
            )
        except Exception:
            filename = ""
        try:
            raw_lines = getattr(sm, "lines", None) or []
            lines = [int(x) for x in raw_lines if isinstance(x, int) or str(x).isdigit()]
        except Exception:
            lines = []
    start_line = min(lines) if lines else None
    end_line = max(lines) if lines else None
    return {
        "filename": filename,
        "lines": lines,
        "start_line": start_line,
        "end_line": end_line,
    }


def _fmt_location(loc: Dict[str, Any] | None) -> str:
    if not isinstance(loc, dict):
        return "<unknown>"
    filename = (loc.get("filename") or "").strip() or "<unknown>"
    start = loc.get("start_line")
    end = loc.get("end_line")
    if isinstance(start, int) and isinstance(end, int) and start != end:
        return f"{filename}:L{start}-L{end}"
    if isinstance(start, int):
        return f"{filename}:L{start}"
    return filename


def _node_reverts(node: Any) -> bool:
    """Return True if the node contains an unconditional revert/throw."""
    try:
        if getattr(node, "type", None) == NodeType.THROW:
            return True
    except Exception:
        pass

    for call in getattr(node, "solidity_calls", []) or []:
        fn = getattr(call, "function", None)
        if fn is None:
            continue
        name = str(getattr(fn, "name", fn) or "")
        if name.startswith("revert"):
            return True

    return False


def _depends_on_msg_sender(var: Any, ctx: Contract | Function | None) -> bool:
    """
    Return True if `var` depends (transitively) on msg.sender in the given analysis context.

    Important: prefer passing a callable (Function/Modifier) as `ctx`.
    Using a whole-contract context can massively over-approximate dependencies (especially
    for temporary IR variables) and create false positives like marking `require(success)`
    as sender-dependent even when the function never reads msg.sender.

    Note: Slither's data-dependency intentionally ignores some "addressing dependencies"
    (e.g. mapping/array indices in Index operations). We explicitly model those here so
    common patterns like `allowed[msg.sender]` are treated as sender-dependent.

    Note: Slither also does not always propagate dependencies through internal call
    return values in caller context. We model those manually so wrappers like
    `_msgSender()` are treated as sender-dependent when their return values derive
    from `msg.sender`.
    """
    if ctx is None or var is None:
        return False

    def _index_deps_for_ctx(context: Contract | Function) -> List[tuple[Any, Any]]:
        cache_key = id(context)
        cached = _INDEX_DEPS_CACHE.get(cache_key)
        if cached is not None:
            return cached
        deps: List[tuple[Any, Any]] = []
        if isinstance(context, Contract):
            callables: List[Any] = []
            callables.extend(getattr(context, "functions", []) or [])
            callables.extend(getattr(context, "modifiers", []) or [])
            nodes_iter = chain.from_iterable(getattr(item, "nodes", []) or [] for item in callables)
        else:
            nodes_iter = getattr(context, "nodes", []) or []

        for node in nodes_iter:
            for ir in getattr(node, "irs", []) or []:
                if not isinstance(ir, Index):
                    continue
                lvalue = getattr(ir, "lvalue", None)
                idx = getattr(ir, "variable_right", None)
                if lvalue is None or idx is None:
                    continue
                deps.append((lvalue, idx))
        _INDEX_DEPS_CACHE[cache_key] = deps
        return deps

    def _internal_call_deps_for_ctx(
        context: Contract | Function,
    ) -> List[tuple[Any, Union[Function, Modifier]]]:
        cache_key = id(context)
        cached = _INTERNAL_CALL_DEPS_CACHE.get(cache_key)
        if cached is not None:
            return cached

        deps: List[tuple[Any, Union[Function, Modifier]]] = []
        if isinstance(context, Contract):
            callables: List[Any] = []
            callables.extend(getattr(context, "functions", []) or [])
            callables.extend(getattr(context, "modifiers", []) or [])
            nodes_iter = chain.from_iterable(getattr(item, "nodes", []) or [] for item in callables)
        else:
            nodes_iter = getattr(context, "nodes", []) or []

        for node in nodes_iter:
            for ir in getattr(node, "irs", []) or []:
                if not isinstance(ir, InternalCall):
                    continue
                lvalue = getattr(ir, "lvalue", None)
                target = getattr(ir, "function", None)
                if lvalue is None or not isinstance(target, (Function, Modifier)):
                    continue
                deps.append((lvalue, target))

        _INTERNAL_CALL_DEPS_CACHE[cache_key] = deps
        return deps

    def _callable_returns_sender_dependent(
        callable_item: Union[Function, Modifier, None],
        visiting_returns: Set[int],
    ) -> bool:
        if not isinstance(callable_item, Function):
            return False

        cache_key = id(callable_item)
        cached = _CALLABLE_RETURN_SENDER_DEP_CACHE.get(cache_key)
        if cached is not None:
            return cached
        if cache_key in visiting_returns:
            # Recursive internal-call cycle.
            return False
        visiting_returns.add(cache_key)

        try:
            return_values: List[Any] = list(getattr(callable_item, "return_values", None) or [])
            if not return_values:
                return_values = list(getattr(callable_item, "returns", None) or [])

            for ret in return_values:
                if ret is None:
                    continue
                try:
                    if is_dependent(ret, _MSG_SENDER, callable_item):
                        _CALLABLE_RETURN_SENDER_DEP_CACHE[cache_key] = True
                        return True
                except Exception:
                    continue

            for ret in return_values:
                if ret is None:
                    continue
                for ref, callee in _internal_call_deps_for_ctx(callable_item):
                    if ref is None:
                        continue
                    try:
                        if not is_dependent(ret, ref, callable_item):
                            continue
                    except Exception:
                        continue
                    if _callable_returns_sender_dependent(callee, visiting_returns):
                        _CALLABLE_RETURN_SENDER_DEP_CACHE[cache_key] = True
                        return True

            _CALLABLE_RETURN_SENDER_DEP_CACHE[cache_key] = False
            return False
        finally:
            visiting_returns.remove(cache_key)

    visiting: Set[tuple[int, int]] = set()

    def _inner(v: Any) -> bool:
        if v is None:
            return False
        cache_key = (id(ctx), id(v))
        cached = _SENDER_DEP_CACHE.get(cache_key)
        if cached is not None:
            return cached
        if cache_key in visiting:
            # Cycle through indexing relationships; treat as not-provable.
            return False
        visiting.add(cache_key)

        try:
            if is_dependent(v, _MSG_SENDER, ctx):
                _SENDER_DEP_CACHE[cache_key] = True
                visiting.remove(cache_key)
                return True
        except Exception:
            pass

        # Model Index lvalue := base[index]; the result depends on `index` too.
        for ref, idx in _index_deps_for_ctx(ctx):
            try:
                if is_dependent(v, ref, ctx) and _inner(idx):
                    _SENDER_DEP_CACHE[cache_key] = True
                    visiting.remove(cache_key)
                    return True
            except Exception:
                continue

        # Model InternalCall lvalue := callee(...); if the callee returns a
        # sender-dependent value, the lvalue is sender-dependent too.
        for ref, callee in _internal_call_deps_for_ctx(ctx):
            try:
                if not is_dependent(v, ref, ctx):
                    continue
            except Exception:
                continue
            if _callable_returns_sender_dependent(callee, set()):
                _SENDER_DEP_CACHE[cache_key] = True
                visiting.remove(cache_key)
                return True

        _SENDER_DEP_CACHE[cache_key] = False
        visiting.remove(cache_key)
        return False

    return _inner(var)


def _must_revert_from(node: Any, memo: Dict[int, bool], visiting: Set[int]) -> bool:
    """
    Conservative 'must-revert' predicate for CFG nodes:
    True only if all paths from the node lead to an unconditional revert/throw.
    Cycles are treated as not-must-revert to avoid false certainty.
    """
    if node is None:
        return False
    key = id(node)
    if key in memo:
        return memo[key]
    if key in visiting:
        # Loop/cycle: can't prove must-revert.
        return False
    visiting.add(key)

    node_type = None
    try:
        node_type = getattr(node, "type", None)
    except Exception:
        node_type = None

    if _node_reverts(node):
        memo[key] = True
        visiting.remove(key)
        return True
    if node_type == NodeType.RETURN:
        memo[key] = False
        visiting.remove(key)
        return False

    sons = getattr(node, "sons", None) or []
    if not sons:
        memo[key] = False
        visiting.remove(key)
        return False

    result = all(_must_revert_from(son, memo, visiting) for son in sons)
    memo[key] = result
    visiting.remove(key)
    return result


def _find_revert_nodes(start: Any, limit: int = 50) -> List[Any]:
    """Collect a few revert/throw nodes reachable from `start` (best-effort)."""
    if start is None:
        return []
    seen: Set[int] = set()
    out: List[Any] = []
    queue: deque[Any] = deque([start])
    while queue and len(out) < limit:
        node = queue.popleft()
        key = id(node)
        if key in seen:
            continue
        seen.add(key)
        if _node_reverts(node):
            out.append(node)
            continue
        for son in getattr(node, "sons", None) or []:
            queue.append(son)
    return out


def _guarded_parameter_kinds(callable_item: Union[Function, Modifier]) -> Dict[int, Set[str]]:
    """
    Return parameter indexes that influence revert-style guards in `callable_item`.

    Kinds include: `require`, `assert`, `if_revert`.
    """
    if callable_item is None:
        return {}

    cache_key = id(callable_item)
    cached = _GUARDED_PARAM_KINDS_CACHE.get(cache_key)
    if cached is not None:
        return {idx: set(kinds) for idx, kinds in cached.items()}

    params: List[Any] = list(getattr(callable_item, "parameters", None) or [])
    if not params:
        _GUARDED_PARAM_KINDS_CACHE[cache_key] = {}
        return {}

    guarded: Dict[int, Set[str]] = {}
    must_memo: Dict[int, bool] = {}

    def _mark_kind(cond_var: Any, kind: str) -> None:
        if cond_var is None:
            return
        for idx, param in enumerate(params):
            try:
                if is_dependent(cond_var, param, callable_item):
                    guarded.setdefault(idx, set()).add(kind)
            except Exception:
                continue

    for node in getattr(callable_item, "nodes", []) or []:
        for call in chain(
            getattr(node, "internal_calls", []) or [],
            getattr(node, "solidity_calls", []) or [],
        ):
            fn = getattr(call, "function", None)
            fn_name = str(getattr(fn, "name", "") or "")
            if fn_name not in _REQUIRE_ASSERT_NAMES:
                continue
            args = getattr(call, "arguments", None) or []
            cond = args[0] if args else None
            kind = "assert" if fn_name.startswith("assert") else "require"
            _mark_kind(cond, kind)

        if getattr(node, "type", None) in (NodeType.IF, NodeType.IFLOOP):
            cond_ir = None
            for ir in getattr(node, "irs", []) or []:
                if isinstance(ir, Condition):
                    cond_ir = ir
                    break
            cond_val = getattr(cond_ir, "value", None) if cond_ir is not None else None
            if cond_val is None:
                continue
            visiting: Set[int] = set()
            son_true = getattr(node, "son_true", None)
            son_false = getattr(node, "son_false", None)
            true_must_revert = _must_revert_from(son_true, must_memo, visiting)
            false_must_revert = _must_revert_from(son_false, must_memo, visiting)
            if true_must_revert or false_must_revert:
                _mark_kind(cond_val, "if_revert")
                for ir in getattr(node, "irs", []) or []:
                    if not isinstance(ir, InternalCall):
                        continue
                    ref = getattr(ir, "lvalue", None)
                    if ref is None:
                        continue
                    try:
                        if not is_dependent(cond_val, ref, callable_item):
                            continue
                    except Exception:
                        continue
                    for arg in getattr(ir, "arguments", None) or []:
                        if arg is None:
                            continue
                        _mark_kind(arg, "if_revert")

    frozen = {idx: tuple(sorted(kinds)) for idx, kinds in guarded.items()}
    _GUARDED_PARAM_KINDS_CACHE[cache_key] = frozen
    return {idx: set(kinds) for idx, kinds in frozen.items()}


def _collect_msg_sender_checks(callable_item: Union[Function, Modifier]) -> List[Dict[str, Any]]:
    """
    Extract sender-dependent revert guards inside a callable.

    Captures:
    - require/assert where the condition depends (transitively) on msg.sender
    - if branches that must-revert where the if-condition depends on msg.sender
    - in modifiers only: external calls that pass msg.sender-derived values as args
    """
    if callable_item is None:
        return []

    # Dependency checks should be evaluated in the callable's own context to avoid
    # whole-contract over-approximation (Slither can otherwise taint unrelated
    # temporary vars and create false positives).
    dep_ctx: Contract | Function = callable_item

    callable_name = _display_name(callable_item)
    callable_kind = "modifier" if isinstance(callable_item, Modifier) else "function"

    checks: List[Dict[str, Any]] = []
    must_memo: Dict[int, bool] = {}

    for node in getattr(callable_item, "nodes", []) or []:
        node_loc = _source_location(node)
        node_src = (_source_text(node) or "").strip()

        # 1) require/assert guards: require(cond) / assert(cond)
        for call in chain(
            getattr(node, "internal_calls", []) or [],
            getattr(node, "solidity_calls", []) or [],
        ):
            fn = getattr(call, "function", None)
            fn_name = str(getattr(fn, "name", "") or "")
            if fn_name not in _REQUIRE_ASSERT_NAMES:
                continue
            args = getattr(call, "arguments", None) or []
            cond = args[0] if args else None
            if not _depends_on_msg_sender(cond, dep_ctx):
                continue
            kind = "assert" if fn_name.startswith("assert") else "require"
            checks.append(
                {
                    "kind": kind,
                    "callable": callable_name,
                    "callable_kind": callable_kind,
                    "location": node_loc,
                    "source": node_src,
                    "detail": {"signature": fn_name},
                }
            )

        # 2) if (...) { revert } style guards
        if getattr(node, "type", None) in (NodeType.IF, NodeType.IFLOOP):
            cond_ir = None
            for ir in getattr(node, "irs", []) or []:
                if isinstance(ir, Condition):
                    cond_ir = ir
                    break
            cond_val = getattr(cond_ir, "value", None) if cond_ir is not None else None
            if cond_val is not None and _depends_on_msg_sender(cond_val, dep_ctx):
                visiting: Set[int] = set()
                son_true = getattr(node, "son_true", None)
                son_false = getattr(node, "son_false", None)
                true_must_revert = _must_revert_from(son_true, must_memo, visiting)
                false_must_revert = _must_revert_from(son_false, must_memo, visiting)

                if true_must_revert or false_must_revert:
                    branch = "true" if true_must_revert else "false"
                    start = son_true if true_must_revert else son_false
                    revert_nodes = _find_revert_nodes(start)
                    revert_loc = _source_location(revert_nodes[0]) if revert_nodes else None
                    revert_src = (_source_text(revert_nodes[0]) or "").strip() if revert_nodes else ""
                    checks.append(
                        {
                            "kind": "if_revert",
                            "callable": callable_name,
                            "callable_kind": callable_kind,
                            "location": node_loc,
                            "source": node_src,
                            "detail": {
                                "revert_on": branch,
                                "revert_location": revert_loc,
                                "revert_source": revert_src,
                            },
                        }
                    )

        # 3) Internal calls that pass msg.sender-derived values into callee
        # parameters that influence a revert-style guard.
        operations = getattr(node, "irs", None) or []
        for ir in operations:
            if not isinstance(ir, InternalCall):
                continue
            callee = getattr(ir, "function", None)
            if not isinstance(callee, (Function, Modifier)):
                continue
            guarded_param_kinds = _guarded_parameter_kinds(callee)
            if not guarded_param_kinds:
                continue
            args = list(getattr(ir, "arguments", None) or [])
            if not args:
                continue

            matched_indexes: List[int] = []
            matched_kinds: Set[str] = set()
            for param_idx, kinds in guarded_param_kinds.items():
                if param_idx < 0 or param_idx >= len(args):
                    continue
                arg = args[param_idx]
                if arg is None:
                    continue
                if not _depends_on_msg_sender(arg, dep_ctx):
                    continue
                matched_indexes.append(param_idx)
                matched_kinds.update(kinds)

            if not matched_indexes:
                continue

            propagated_kind = (
                "if_revert"
                if "if_revert" in matched_kinds
                else "require"
                if "require" in matched_kinds
                else "assert"
            )
            checks.append(
                {
                    "kind": propagated_kind,
                    "callable": callable_name,
                    "callable_kind": callable_kind,
                    "location": node_loc,
                    "source": node_src,
                    "detail": {
                        "via_internal_call": _display_name(callee),
                        "guard_kinds": sorted(matched_kinds),
                        "guarded_parameter_indexes": sorted(set(matched_indexes)),
                    },
                }
            )

        # 4) Modifier-only: external calls that pass msg.sender-derived values.
        if callable_kind == "modifier":
            for ir in operations:
                if isinstance(ir, (HighLevelCall, LowLevelCall)) and not isinstance(ir, LibraryCall):
                    args = getattr(ir, "arguments", None) or []
                    destination = getattr(ir, "destination", None)
                    reads = list(args)
                    if destination is not None:
                        reads.append(destination)
                    if not any(
                        _depends_on_msg_sender(v, dep_ctx) for v in reads if v is not None
                    ):
                        continue
                    checks.append(
                        {
                            "kind": "external_call_sender_arg",
                            "callable": callable_name,
                            "callable_kind": callable_kind,
                            "location": node_loc,
                            "source": node_src,
                            "detail": {
                                "type": ir.__class__.__name__,
                                "function": str(getattr(ir, "function_name", "") or ""),
                            },
                        }
                    )

    return checks


def _format_msg_sender_checks(checks: List[Dict[str, Any]]) -> List[str]:
    """Human-friendly one-liners for UI/markdown panels."""
    out: List[str] = []
    for chk in checks or []:
        kind = chk.get("kind") or "check"
        callable_name = chk.get("callable") or "<unknown>"
        loc = chk.get("location") or {}
        line = f"[{kind}] {callable_name} @ {_fmt_location(loc)}"
        detail = chk.get("detail") or {}
        if kind == "if_revert":
            branch = detail.get("revert_on") or "?"
            rloc = detail.get("revert_location") or {}
            line += f" (revert on {branch}; reverts @ {_fmt_location(rloc)})"
        out.append(line)
    return out


def _resolve_unimplemented_call(
    caller: Union[Function, Modifier],
    target: Union[Function, Modifier, None],
    root_contract: Contract | None,
    all_contracts: Sequence[Contract] | None = None,
) -> Union[Function, Modifier, None]:
    """Resolve unimplemented interface/abstract calls to the first implemented override."""
    if target is None:
        return target
    if not hasattr(target, "is_implemented") or target.is_implemented:
        return target

    target_name = getattr(target, "name", None)
    target_signature = getattr(target, "solidity_signature", None)
    target_full_name = getattr(target, "full_name", None)
    signature = target_signature or target_full_name or target_name
    if not signature and not target_name:
        return target
    caller_contract = getattr(caller, "contract_declarer", None) or getattr(caller, "contract", None)
    target_contract = getattr(target, "contract_declarer", None) or getattr(target, "contract", None)

    def _param_types(fn: Any) -> List[str]:
        params = getattr(fn, "parameters", None) or []
        return [str(getattr(p, "type", "")) for p in params]

    target_param_types = _param_types(target)

    def _matches_signature(fn: Function) -> bool:
        fn_sig = getattr(fn, "solidity_signature", None)
        if target_signature and fn_sig:
            return fn_sig == target_signature
        fn_full_name = getattr(fn, "full_name", None)
        if target_full_name and fn_full_name:
            return fn_full_name == target_full_name
        fn_name = getattr(fn, "name", None)
        if target_name and fn_name and fn_name != target_name:
            return False
        if target_param_types:
            return _param_types(fn) == target_param_types
        return True

    def _find_implemented(contract: Contract | None) -> Function | None:
        if contract is None:
            return None
        candidates = list(getattr(contract, "functions_declared", []) or [])
        for fn in getattr(contract, "functions", []) or []:
            if fn not in candidates:
                candidates.append(fn)
        for fn in candidates:
            if not _matches_signature(fn):
                continue
            if getattr(fn, "is_implemented", True):
                return fn
        return None

    def _find_descendant_override() -> Function | None:
        if all_contracts is None or target_contract is None:
            return None
        for contract in all_contracts:
            if contract is target_contract:
                continue
            inheritance = getattr(contract, "inheritance", []) or []
            if target_contract not in inheritance:
                continue
            resolved = _find_implemented(contract)
            if resolved is not None:
                return resolved
        return None

    # First, resolve using the main (root) contract, then walk its parents.
    if root_contract is not None:
        search_contracts: List[Contract] = [root_contract]
        search_contracts.extend(getattr(root_contract, "inheritance", []))
        for base in search_contracts:
            resolved = _find_implemented(base)
            if resolved is not None:
                return resolved

    # If no root contract is provided, fall back to the caller's contract then parents.
    if root_contract is None and caller_contract is not None:
        resolved = _find_implemented(caller_contract)
        if resolved is not None:
            return resolved
        for base in getattr(caller_contract, "inheritance", []):
            resolved = _find_implemented(base)
            if resolved is not None:
                return resolved

    # Finally, try any derived contracts in the compilation unit.
    resolved = _find_descendant_override()
    if resolved is not None:
        return resolved

    return target


def _resolve_override_call(
    caller: Union[Function, Modifier],
    call_obj: Any,
    target: Union[Function, Modifier, None],
    root_contract: Contract | None,
    all_contracts: Sequence[Contract] | None = None,
) -> Union[Function, Modifier, None]:
    """Resolve virtual calls to the most-derived override on the root contract.

    Robust virtual-dispatch resolver:
    - Honors explicit non-virtual calls (`super.foo()` or `ContractName.foo()`) per call site.
    - For virtual internal calls, returns the most-derived implementation in the
      *deployed* `root_contract` linearization only (root + its inheritance).
      Siblings beyond root (e.g. `PoolV3_USDT is PoolV3`) are NOT considered,
      because if PoolV3 is the deployed root, PoolV3_USDT does not exist.
      This matches Solidity C3 linearization semantics and satisfies:
        * PoolV3 (root=PoolV3.sol) -> PoolV3.deposit, not ERC4626, not PoolV3_USDT
        * PoolV3_USDT (root=PoolV3_USDT.sol) -> PoolV3_USDT/PooolV3 chain correctly.
      Works for both local (`Slither(path)`) and on-chain (`Slither(crytic-export)`)
      analyses because it only uses `root_contract` and its bases, never arbitrary
      `all_contracts` descendants for implemented virtual calls. Unimplemented
      interface resolution is handled separately by `_resolve_unimplemented_call`.
    """
    if target is None or root_contract is None:
        return target
    if not isinstance(target, Function):
        return target

    # 1) Non-virtual detection: super or qualified ContractName.foo()
    # Check Slither type_call flag first
    call_type = str(getattr(call_obj, "type_call", "") or "").lower()
    if "super" in call_type:
        return target

    target_name = getattr(target, "name", None) or ""
    # Prefer per-call-site source (IR node) over whole caller source to avoid
    # false positives when caller contains both super/qualified and virtual calls.
    call_src = ""
    node = getattr(call_obj, "node", None)
    if node is not None:
        try:
            call_src = _source_text(node) or ""
        except Exception:
            call_src = ""
    caller_src = ""
    try:
        caller_src = _source_text(caller) or ""
    except Exception:
        caller_src = ""

    # Helper to test a source snippet for super/qualified pattern
    def _is_qualified_in_src(src: str) -> bool:
        if not src or not target_name:
            return False
        # super.foo(
        if re.search(r"\bsuper\s*\.\s*" + re.escape(target_name) + r"\s*\(", src):
            return True
        # ContractName.foo( where ContractName is target's declarer
        contract_name = ""
        try:
            decl = getattr(target, "contract_declarer", None) or getattr(target, "contract", None)
            contract_name = getattr(decl, "name", "") or ""
        except Exception:
            contract_name = ""
        if contract_name and re.search(
            r"\b" + re.escape(contract_name) + r"\s*\.\s*" + re.escape(target_name) + r"\s*\(", src
        ):
            return True
        return False

    # If we have a concrete call-site source, only honor qualified/super there.
    # Fall back to caller source only when call-site source is empty (e.g., fallback
    # Function objects from regex scanning that have no node).
    if call_src:
        if _is_qualified_in_src(call_src):
            return target
    elif caller_src and _is_qualified_in_src(caller_src):
        # This path is for synthetic Function call objects without a node;
        # whole-caller heuristic is the best we can do, but we keep it to not
        # break existing qualified-call handling for those fallbacks.
        return target

    # 2) Virtual dispatch: find most-derived override in root's linearization.
    #    Use Slither's C3-aware resolver first, then fallback to manual chain scan.
    target_signature = getattr(target, "solidity_signature", None)

    # Build chain set for validation that target is actually in root's hierarchy.
    # If target's declarer is outside root's hierarchy (unrelated library), don't
    # try to override it.
    try:
        target_contract = getattr(target, "contract_declarer", None) or getattr(target, "contract", None)
        chain_contracts = {root_contract}
        chain_contracts.update(getattr(root_contract, "inheritance", []) or [])
        if target_contract is not None and target_contract not in chain_contracts:
            # Check via linearized base contracts if available (more complete)
            linearized = getattr(root_contract, "_linearizedBaseContracts", None) or []
            if target_contract not in linearized and target_contract is not root_contract:
                # Unrelated contract (e.g., external library) – keep original
                # But still allow if target is interface that root implements indirectly
                # Interfaces are often not in inheritance list? They are, PoolV3 inherits IERC4626.
                # So only early-return if truly unrelated and not interface-like.
                # For safety, continue to resolver but it will likely return target.
                pass
    except Exception:
        pass

    # Primary: Slither's own C3 resolver (handles diamond correctly)
    if target_signature:
        try:
            most_derived = root_contract.get_function_from_signature(target_signature)  # type: ignore[attr-defined]
            if (
                most_derived is not None
                and getattr(most_derived, "is_implemented", True)
                and getattr(most_derived, "solidity_signature", None) == target_signature
            ):
                # Ensure declarer is in root chain (avoid picking unrelated overload)
                decl = getattr(most_derived, "contract_declarer", None) or getattr(most_derived, "contract", None)
                chain_set = {root_contract}
                chain_set.update(getattr(root_contract, "inheritance", []) or [])
                # Also consider linearized set
                linearized = getattr(root_contract, "_linearizedBaseContracts", None) or []
                chain_set.update(linearized)
                if decl is None or decl in chain_set or getattr(most_derived, "contract", None) in chain_set:
                    return most_derived
                # If decl not in chain_set but most_derived is still the root's view of that signature,
                # it *is* the correct virtual dispatch for this root, so return it.
                return most_derived
        except Exception:
            pass
        # Also try full_name fallback
        try:
            target_full = getattr(target, "full_name", None)
            if target_full:
                most_derived2 = root_contract.get_function_from_canonical_name(target_full)  # type: ignore[attr-defined]
                if most_derived2 and getattr(most_derived2, "is_implemented", True):
                    return most_derived2
        except Exception:
            pass

    # Fallback: manual scan of [root] + inheritance in order that respects C3.
    # Slither's inheritance is already in linearized order from most base to most derived
    # or vice versa depending on version; we handle both by checking distance from root
    # via BFS on immediate_inheritance graph and picking minimal distance.
    target_full_name = getattr(target, "full_name", None)
    target_name_only = getattr(target, "name", None)
    target_param_types = [str(getattr(p, "type", "")) for p in (getattr(target, "parameters", None) or [])]

    def _matches_signature(fn: Function) -> bool:
        fn_sig = getattr(fn, "solidity_signature", None)
        if target_signature and fn_sig:
            return fn_sig == target_signature
        fn_full_name = getattr(fn, "full_name", None)
        if target_full_name and fn_full_name:
            return fn_full_name == target_full_name
        fn_name = getattr(fn, "name", None)
        if target_name_only and fn_name and fn_name != target_name_only:
            return False
        if target_param_types:
            params = getattr(fn, "parameters", None) or []
            return [str(getattr(p, "type", "")) for p in params] == target_param_types
        return True

    def _find_override(contract: Contract | None) -> Function | None:
        if contract is None:
            return None
        candidates = list(getattr(contract, "functions_declared", []) or [])
        for fn in getattr(contract, "functions", []) or []:
            if fn not in candidates:
                candidates.append(fn)
        for fn in candidates:
            if not _matches_signature(fn):
                continue
            if getattr(fn, "is_implemented", True):
                return fn
        return None

    # Chain: root first (distance 0), then BFS by immediate inheritance distance
    # This guarantees most-derived (closest to root) wins, handling diamond tie
    # correctly via linearized order.
    chain_ordered: list[Contract] = []
    seen: set[int] = set()
    # BFS from root outward to compute distance; queue holds (contract, distance)
    from collections import deque

    queue: deque[tuple[Contract, int]] = deque()
    queue.append((root_contract, 0))
    seen.add(id(root_contract))
    # Map contract -> distance
    dist: dict[int, int] = {id(root_contract): 0}
    # Use inheritance graph: for each contract, its immediate parents are immediate_inheritance
    # If not available, fall back to inheritance list.
    while queue:
        cur, d = queue.popleft()
        chain_ordered.append(cur)
        immediates = getattr(cur, "immediate_inheritance", None)
        if immediates is None:
            # Fallback: use inheritance but we need to avoid large explosion; just use direct inheritance of root for first level
            if cur is root_contract:
                immediates = getattr(root_contract, "inheritance", []) or []
                # For deeper levels, we can't reliably expand, so stop BFS after first level
                # Instead, fill chain_ordered with root + linearized inheritance in original order
                # To preserve C3, we append remaining inheritance not yet seen in order
                for base in immediates:
                    if id(base) not in seen:
                        seen.add(id(base))
                        dist[id(base)] = d + 1
                        chain_ordered.append(base)
                break
            else:
                immediates = []
        for base in immediates or []:
            if id(base) not in seen:
                seen.add(id(base))
                dist[id(base)] = d + 1
                queue.append((base, d + 1))

    # If BFS didn't cover all inheritance (single-file case where linearized is empty),
    # ensure every base in inheritance is in chain_ordered in linearization order
    for base in getattr(root_contract, "inheritance", []) or []:
        if id(base) not in seen:
            chain_ordered.append(base)

    # Now scan chain_ordered from most-derived outward (chain_ordered is BFS order, root first)
    for contract in chain_ordered:
        ov = _find_override(contract)
        if ov is not None:
            return ov

    return target


def _call_target(call_obj: Any) -> Union[Function, Modifier, None]:
    candidate = None
    if isinstance(call_obj, tuple) and len(call_obj) >= 2:
        candidate = call_obj[1]
    elif isinstance(call_obj, (InternalCall, HighLevelCall, LibraryCall)):
        candidate = getattr(call_obj, "function", None)
    elif isinstance(call_obj, (Function, Modifier)):
        candidate = call_obj
    else:
        candidate = getattr(call_obj, "function", None)
    if isinstance(candidate, (InternalCall, HighLevelCall, LibraryCall)):
        candidate = getattr(candidate, "function", None)
    if isinstance(candidate, (Function, Modifier)):
        return candidate
    return None


def _call_sort_key(call_obj: Any) -> tuple[str, str]:
    target = _call_target(call_obj)
    if target is not None:
        return ("target", _display_name(target))
    return ("raw", f"{call_obj.__class__.__name__}:{call_obj}")


def _walk_callable(
    item: Union[Function, Modifier],
    visited: Set[str],
    collected: List[Dict[str, Any]],
    callable_index: Dict[str, Union[Function, Modifier]],
    root_contract: Contract,
    all_contracts: Sequence[Contract] | None = None,
) -> None:
    """
    Record this callable and recursively visit everything it can execute:
    - Modifiers on the callable
    - Internal calls
    - External high-level calls
    Solidity native functions (e.g., mload, revert) are skipped.
    """
    if item is None:
        return

    name = _display_name(item)
    if name in visited:
        return
    visited.add(name)

    if isinstance(item, SolidityFunction):
        return

    collected.append(
        {
            "name": name,
            "kind": item.__class__.__name__.lower(),
            "source": _source_text(item),
            "selector": _function_selector(item),
            "cyclomatic_complexity": compute_cyclomatic_complexity(item)
            if hasattr(item, "nodes")
            else 1,
            "contract": getattr(getattr(item, "contract_declarer", None), "name", None)
            or getattr(getattr(item, "contract", None), "name", None)
            or "Unknown",
        }
    )
    callable_index[name] = item

    # Visit modifiers first (they execute before the function body).
    for modifier in getattr(item, "modifiers", []):
        if isinstance(modifier, Modifier):
            _walk_callable(
                modifier,
                visited,
                collected,
                callable_index,
                root_contract,
                all_contracts,
            )

    CALL_ATTRS = (
        "internal_calls",
        "high_level_calls",
        "library_calls",
        "solidity_calls",
    )

    ordered_calls: List[Any] = []
    seen_call_keys: Set[tuple[str, int]] = set()

    def _call_identity(call_obj: Any) -> tuple[str, int]:
        target = _call_target(call_obj)
        if target is not None:
            return ("target", id(target))
        return ("raw", id(call_obj))

    def _add_call(call_obj: Any) -> None:
        if call_obj is None:
            return
        key = _call_identity(call_obj)
        if key in seen_call_keys:
            return
        seen_call_keys.add(key)
        ordered_calls.append(call_obj)

    operations = getattr(item, "all_slithir_operations", None)
    if callable(operations):
        for ir in operations():
            if isinstance(ir, (InternalCall, HighLevelCall, LibraryCall)):
                _add_call(ir)

    for attr in CALL_ATTRS:
        for call in getattr(item, attr, []):
            _add_call(call)

    # Fallback: scan source for internal/private calls Slither may miss.
    caller_contract = getattr(item, "contract_declarer", None) or getattr(item, "contract", None)
    if caller_contract is not None:
        candidates = [caller_contract]
        candidates.extend(getattr(caller_contract, "inheritance", []) or [])
        fn_by_name: Dict[str, Function] = {}
        for contract in candidates:
            for fn in getattr(contract, "functions_declared", []) or []:
                name = getattr(fn, "name", None)
                if name and name.startswith("_"):
                    fn_by_name.setdefault(name, fn)
        source_text = _source_text(item)
        if source_text:
            for match in re.finditer(r"\b(_[A-Za-z0-9_]*)\s*\(", source_text):
                fallback_fn = fn_by_name.get(match.group(1))
                if fallback_fn is not None:
                    _add_call(fallback_fn)

    def _is_interface_target(target_item: Union[Function, Modifier, None]) -> bool:
        if target_item is None:
            return False
        contract = getattr(target_item, "contract_declarer", None) or getattr(
            target_item, "contract", None
        )
        return bool(contract is not None and getattr(contract, "is_interface", False))

    for call in ordered_calls:
        target = _call_target(call)
        target = _resolve_unimplemented_call(item, target, root_contract, all_contracts)
        target = _resolve_override_call(item, call, target, root_contract, all_contracts)
        if _is_interface_target(target):
            continue
        _walk_callable(
            target,
            visited,
            collected,
            callable_index,
            root_contract,
            all_contracts,
        )


def _entry_points_for(contract: Contract) -> List[Function]:
    """Return state-modifying public/external entry points for a contract."""
    return _entry_points_by_predicate(
        contract,
        lambda fn: (not fn.view) and (not fn.pure),
    )


def _read_only_entry_points_for(contract: Contract) -> List[Function]:
    """Return view/pure public/external entry points for a contract."""
    return _entry_points_by_predicate(
        contract,
        lambda fn: bool(fn.view or fn.pure),
    )


def _entry_points_by_predicate(
    contract: Contract,
    is_selected: Callable[[FunctionContract], bool],
) -> List[Function]:
    """Return public/external FunctionContract callables matching is_selected."""
    candidates: List[Function] = []
    for function in contract.functions:
        if function.visibility not in ["public", "external"]:
            continue
        if not isinstance(function, FunctionContract):
            continue
        if function.is_constructor:
            continue
        if function.is_shadowed:
            continue
        if hasattr(function, "is_implemented") and not function.is_implemented:
            continue
        if not is_selected(function):
            continue
        candidates.append(function)
    return sorted(candidates, key=_display_name)


def _iter_audited_contracts(
    slither: Slither,
    root_contracts: Sequence[Contract] | None = None,
) -> Sequence[Contract]:
    """Yield concrete, non-test contracts to inspect."""
    allowed_keys: Set[tuple[str, str]] | None = None
    if root_contracts:
        allowed_keys = set()
        for root in root_contracts:
            allowed_keys.add(_contract_key(root))
            for base in getattr(root, "inheritance", []):
                allowed_keys.add(_contract_key(base))

    candidates = slither.contracts if allowed_keys is not None else slither.contracts_derived

    return sorted(
        (
            contract
            for contract in candidates
            if not contract.is_test
            and not contract.is_from_dependency()
            and not is_test_file(Path(contract.source_mapping.filename.absolute))
            and not contract.is_interface
            and not contract.is_library
            and not contract.is_abstract
            and (allowed_keys is None or _contract_key(contract) in allowed_keys)
        ),
        key=lambda contract: contract.name,
    )


def build_entry_point_flows(
    slither: Slither,
    root_contracts: Sequence[Contract] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> List[Dict[str, Any]]:
    """Assemble structured data for every entry point and its execution flow."""
    return _build_entry_point_flows(
        slither,
        root_contracts=root_contracts,
        entry_points_fn=_entry_points_for,
        label="entry point",
        progress_cb=progress_cb,
    )


def build_read_only_entry_point_flows(
    slither: Slither,
    root_contracts: Sequence[Contract] | None = None,
    progress_cb: ProgressCallback | None = None,
) -> List[Dict[str, Any]]:
    """Assemble structured data for view/pure entry points and their execution flows."""
    return _build_entry_point_flows(
        slither,
        root_contracts=root_contracts,
        entry_points_fn=_read_only_entry_points_for,
        label="read-only entry point",
        progress_cb=progress_cb,
    )


def _build_entry_point_flows(
    slither: Slither,
    root_contracts: Sequence[Contract] | None,
    entry_points_fn: Callable[[Contract], List[Function]],
    label: str,
    progress_cb: ProgressCallback | None,
) -> List[Dict[str, Any]]:
    # These caches key off `id(...)` of Slither objects. Clear them per run to avoid
    # stale entries (and potential id-reuse collisions) across multiple analyses in
    # the same long-lived process (e.g. the local web server).
    _INDEX_DEPS_CACHE.clear()
    _SENDER_DEP_CACHE.clear()
    _INTERNAL_CALL_DEPS_CACHE.clear()
    _CALLABLE_RETURN_SENDER_DEP_CACHE.clear()
    _GUARDED_PARAM_KINDS_CACHE.clear()

    entries: List[Dict[str, Any]] = []
    reported_unimplemented: Set[str] = set()
    all_contracts = list(getattr(slither, "contracts", []) or [])
    compilation_units = getattr(slither, "compilation_units", None) or []
    if not compilation_units:
        cc = getattr(slither, "crytic_compile", None) or getattr(slither, "_crytic_compile", None)
        compilation_units = getattr(cc, "compilation_units", None) or []
    if compilation_units:
        _report_progress(progress_cb, "Computing data dependencies")
        for unit in compilation_units:
            try:
                compute_dependency(unit)
            except Exception:
                # Best-effort; dependency analysis can fail on edge-case builds.
                continue

    audited_contracts = list(_iter_audited_contracts(slither, root_contracts))
    _report_progress(
        progress_cb,
        "Collecting audited contracts",
        count=len(audited_contracts),
    )
    contract_entry_points = collect_unique_entry_points(audited_contracts, entry_points_fn)
    total_entries = sum(len(entry_points) for _, entry_points in contract_entry_points)
    entry_index = 0

    for contract_index, (contract, entry_points) in enumerate(contract_entry_points, start=1):
        _report_progress(
            progress_cb,
            "Scanning contract",
            contract=contract.name,
            index=contract_index,
            total=len(audited_contracts),
        )
        for entry_point in entry_points:
            entry_index += 1
            _report_progress(
                progress_cb,
                f"Analyzing {label}",
                entry_point=_display_name(entry_point),
                contract=contract.name,
                index=entry_index,
                total=total_entries,
            )
            visited: Set[str] = set()
            flow: List[Dict[str, Any]] = []
            callable_index: Dict[str, Union[Function, Modifier]] = {}

            reads_msg_sender = any(
                v.name == "msg.sender" for v in entry_point.all_solidity_variables_read()
            )

            state_vars_read = _collect_state_vars(entry_point, "read")
            state_vars_written = _collect_state_vars(entry_point, "written")
            extra_written = _collect_state_vars_via_storage_params(entry_point)
            if extra_written:
                existing = {
                    v.get("qualified_name") or v.get("name", "")
                    for v in state_vars_written
                }
                for var in sorted(extra_written, key=lambda v: v.name or ""):
                    record = _state_var_record(var)
                    key = record.get("qualified_name") or record.get("name", "")
                    if key and key not in existing:
                        state_vars_written.append(record)
                        existing.add(key)
            state_vars_read_keys = [
                v.get("qualified_name") or v.get("name", "")
                for v in state_vars_read
            ]
            state_vars_written_keys = [
                v.get("qualified_name") or v.get("name", "")
                for v in state_vars_written
            ]

            _walk_callable(
                entry_point,
                visited,
                flow,
                callable_index,
                contract,
                all_contracts,
            )

            for item in flow:
                target_fn = callable_index.get(item.get("name"))
                if (
                    isinstance(target_fn, Function)
                    and hasattr(target_fn, "is_implemented")
                    and not target_fn.is_implemented
                ):
                    target_contract = getattr(target_fn, "contract_declarer", None) or getattr(
                        target_fn, "contract", None
                    )
                    if target_contract is not None and getattr(target_contract, "is_library", False):
                        continue
                    if item["name"] not in reported_unimplemented:
                        print(f"Function not implemented: {item['name']}")
                        reported_unimplemented.add(item["name"])
                # Capture data dependencies for every function in the flow.
                item["data_dependencies"] = _collect_data_dependencies(target_fn)
                item["variable_records"] = (
                    _collect_local_and_param_vars(target_fn) if target_fn else []
                )
                sender_checks = _collect_msg_sender_checks(target_fn) if target_fn else []
                item["msg_sender_checks"] = sender_checks
                item["msg_sender_constrained"] = bool(sender_checks)
                item["restrictions"] = _format_msg_sender_checks(sender_checks)

            aggregated_sender_checks: List[Dict[str, Any]] = []
            for item in flow:
                aggregated_sender_checks.extend(item.get("msg_sender_checks") or [])

            _report_progress(
                progress_cb,
                f"{label.capitalize()} complete",
                entry_point=_display_name(entry_point),
                contract=contract.name,
                index=entry_index,
                total=total_entries,
            )

            entries.append(
                {
                    "contract": contract.name,
                    "entry_point": _display_name(entry_point),
                    "inputs": _collect_entry_point_inputs(entry_point),
                    "outputs": _collect_entry_point_outputs(entry_point),
                    "reads_msg_sender": reads_msg_sender,
                    "msg_sender_constrained": bool(aggregated_sender_checks),
                    "msg_sender_checks": aggregated_sender_checks,
                    "msg_sender_restrictions": _format_msg_sender_checks(
                        aggregated_sender_checks
                    ),
                    "state_variables_read": state_vars_read,
                    "state_variables_written": state_vars_written,
                    "state_variables_read_keys": state_vars_read_keys,
                    "state_variables_written_keys": state_vars_written_keys,
                    "flow": flow,
                }
            )

    return entries
