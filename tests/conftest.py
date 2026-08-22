"""Shared fixtures for the OnboardMe backend test suite.

Every test target is registered in ``tests/targets.py``; the fixtures below
are parametrized per target, so adding a new smart contract to the suite is a
one-line change in the registry.  Generic invariants in
``tests/test_discovery.py`` then run automatically for the new contract.

Etherscan responses are cached by crytic-compile under
``crytic-export/etherscan-contracts/``: the first run per target fetches the
verified source (requires ``ETHERSCAN_API_KEY`` in ``.env``); every
subsequent run reuses the cached bundle fully offline.  Deployed bytecode is
immutable, so the cache never goes stale.
"""

import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Keep console output clean, same as main.py.
logging.disable(logging.CRITICAL)

from tests.targets import TARGETS  # noqa: E402


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Regenerate golden snapshots instead of comparing against them.",
    )


@pytest.fixture(scope="session", params=TARGETS, ids=lambda t: t["id"])
def target(request: pytest.FixtureRequest) -> dict:
    """One run of the whole suite per registered contract target."""
    return request.param


@pytest.fixture(scope="session")
def slither(target: dict):
    """Slither instance for the target's verified bundle (cached offline)."""
    from slither.slither import Slither

    return Slither(f"{target['chain']}:{target['address']}", skip_analyze=False)


@pytest.fixture(scope="session")
def deployed_contracts(slither, target: dict):
    """Resolved deployed contract(s) plus merged root contracts."""
    from main import (
        _merge_root_contracts,
        _resolve_root_contracts,
        _select_local_root_contracts,
    )

    resolved = _resolve_root_contracts(
        slither, target["address"], target["chain"]
    )
    roots = _merge_root_contracts(
        resolved, _select_local_root_contracts(slither)
    )
    return resolved, roots


@pytest.fixture(scope="session")
def root_contract(slither, deployed_contracts, target: dict):
    """The target's deployable root contract object."""
    _, roots = deployed_contracts
    return next(
        contract
        for contract in roots
        if contract.name == target["contract"]
    )


@pytest.fixture(scope="session")
def flows(slither, root_contract):
    """State-changing and read-only entry-point flows for the root."""
    from analysis.flow_walk import (
        build_entry_point_flows,
        build_read_only_entry_point_flows,
    )

    entries = build_entry_point_flows(slither, [root_contract])
    read_only = build_read_only_entry_point_flows(slither, [root_contract])
    return entries, read_only


@pytest.fixture(scope="session")
def entries(flows) -> dict:
    entries, _ = flows
    return {entry["entry_point"]: entry for entry in entries}


@pytest.fixture(scope="session")
def read_only_entries(flows) -> dict:
    _, read_only = flows
    return {entry["entry_point"]: entry for entry in read_only}
