"""Universal invariants run automatically for EVERY registered target.

These tests do not know the contract in advance: they encode the rules that
must hold for any immutable deployed contract analyzed by the tool.

Adding a new contract to ``tests/targets.py`` immediately brings it under
these invariants plus the full-flow golden snapshot.
"""

from slither.utils.function import get_function_id

from tests.helpers import (
    compare_or_update_snapshot,
    getter_state_var_key,
    is_getter_entry,
)
from tests.normalize import build_snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Deployment & discovery
# ─────────────────────────────────────────────────────────────────────────────


def test_deployed_contract_is_the_analysis_root(
    deployed_contracts, root_contract, target
):
    resolved, roots = deployed_contracts
    assert resolved, f"could not resolve deployed contract {target['address']}"
    assert resolved[0].name == target["contract"]
    assert roots and roots[0].name == target["contract"]


def test_every_target_has_entry_points(entries, read_only_entries, target):
    assert entries, f"no state-changing entry points detected for {target['id']}"
    assert read_only_entries, f"no read-only entry points detected for {target['id']}"


def test_entry_point_sets_do_not_overlap(entries, read_only_entries):
    assert set(entries).isdisjoint(set(read_only_entries))


def test_entry_points_are_attributed_to_the_root(
    entries, read_only_entries, root_contract
):
    for entry in list(entries.values()) + list(read_only_entries.values()):
        assert entry["contract"] == root_contract.name, entry["entry_point"]


def test_no_duplicate_entry_point_names(entries, read_only_entries):
    for name in entries:
        assert name not in read_only_entries
    assert len(set(entries)) == len(entries)
    assert len(set(read_only_entries)) == len(read_only_entries)


# ─────────────────────────────────────────────────────────────────────────────
# Flow structure
# ─────────────────────────────────────────────────────────────────────────────


def test_every_flow_starts_with_its_entry_point(entries, read_only_entries):
    for entry in list(entries.values()) + list(read_only_entries.values()):
        assert entry["flow"], f"empty flow for {entry['entry_point']}"
        assert entry["flow"][0]["name"] == entry["entry_point"]


def test_flow_nodes_are_deduplicated_within_an_entry(entries, read_only_entries):
    for entry in list(entries.values()) + list(read_only_entries.values()):
        names = [node["name"] for node in entry["flow"]]
        assert len(names) == len(set(names)), (
            f"{entry['entry_point']} walks the same callable twice"
        )


def test_entry_point_selectors_match_the_abi_signature(entries, read_only_entries):
    """The selector of the entry node must be the keccak selector of its own
    ABI signature - a wrong function binding changes the selector."""
    for entry in list(entries.values()) + list(read_only_entries.values()):
        node = entry["flow"][0]
        if not node.get("selector"):
            continue
        signature = node["name"].split(".", 1)[1]
        expected = f"{get_function_id(signature):#0{10}x}"
        assert node["selector"] == expected, (
            f"{entry['entry_point']} selector {node['selector']} does not "
            f"match its ABI signature {signature}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Resolution scope: everything must stay inside the deployed type's own chain
# ─────────────────────────────────────────────────────────────────────────────


def test_no_flow_node_resolves_outside_root_chain(
    slither, root_contract, entries, read_only_entries
):
    """Every node of every flow must belong to the deployed type's own chain
    (root + its C3 inheritance) or to a library.  Anything else is a sibling
    leak or a wrong external binding."""
    allowed = {root_contract.name}
    allowed.update(c.name for c in root_contract.inheritance)
    allowed.update(
        c.name for c in slither.contracts if getattr(c, "is_library", False)
    )
    for entry in list(entries.values()) + list(read_only_entries.values()):
        for node in entry["flow"]:
            assert node["contract"] in allowed, (
                f"{entry['entry_point']} resolves {node['name']} to "
                f"{node['contract']}, which is outside the deployed "
                f"{root_contract.name} chain"
            )


def test_interface_declarations_are_never_walked(
    slither, root_contract, entries, read_only_entries
):
    """Interface functions are declarations, not implementations: they must
    never appear as flow nodes.  Sole exception: auto-generated public
    state-variable getters, which Slither models as bodyless interface
    functions - their own entry node carries the interface declarer."""
    interface_names = {
        c.name for c in slither.contracts if getattr(c, "is_interface", False)
    }
    for entry in list(entries.values()) + list(read_only_entries.values()):
        for node in entry["flow"]:
            declarer = node["name"].split(".")[0]
            if declarer in interface_names:
                assert (
                    node["name"] == entry["entry_point"]
                    and is_getter_entry(entry, root_contract)
                ), (
                    f"{entry['entry_point']} walks interface declaration "
                    f"{node['name']}"
                )


def test_getters_surface_their_state_variable_read(
    root_contract, entries, read_only_entries
):
    """A getter entry point must report reading the underlying state
    variable in the storage panel."""
    for entry in list(entries.values()) + list(read_only_entries.values()):
        if not is_getter_entry(entry, root_contract):
            continue
        key = getter_state_var_key(entry["entry_point"], root_contract)
        assert key is not None
        assert key in entry["state_variables_read_keys"], (
            f"{entry['entry_point']} does not report reading {key}: "
            f"{entry['state_variables_read_keys']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Golden snapshot: full-flow coverage for every entry point
# ─────────────────────────────────────────────────────────────────────────────
#
# Flow ORDER is not compared (Slither IR traversal order is unstable across
# runs); flow CONTENT is.  Regenerate with: pytest tests/ --snapshot-update
# ─────────────────────────────────────────────────────────────────────────────


def test_full_flow_snapshot(target, flows, request):
    entries, read_only = flows
    snapshot = build_snapshot(entries, read_only)
    compare_or_update_snapshot(target, snapshot, request)
