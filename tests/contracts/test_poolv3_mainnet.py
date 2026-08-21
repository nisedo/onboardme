"""Contract-specific ground truth for mainnet PoolV3.

Target: 0x683FAf5BAFd88d4c383cCaf3d61C26AF2E164409 (Ethereum mainnet).
Contract name: PoolV3 (Gearbox V3 lending pool, immutable deployed bytecode).

These assertions encode the ONE correct interpretation of this deployed
contract: entry-point discovery must be complete and every node of every
execution flow must resolve to the C3-most-derived implementation on the
deployed type (never a base override that was replaced, never a sibling
beyond the root).

If a future code change makes a test fail, exactly one of two things is true:
  1. the change is a regression -> fix the code;
  2. the test encoded wrong behavior -> update the test.
There is no third option because the on-chain contract is immutable.
"""

import pytest

from tests.helpers import skip_unless_target

TARGET_ID = "poolv3_mainnet"


@pytest.fixture(autouse=True)
def _poolv3_only(target):
    skip_unless_target(target, TARGET_ID)


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth: complete entry-point surface of the deployed PoolV3.
# State-changing functions are public/external non-view, non-pure; the
# read-only list is every view/pure function including the auto-generated
# public state-variable getters (treasury, version, acl, ...).
# ─────────────────────────────────────────────────────────────────────────────

STATE_CHANGING_ENTRY_POINTS = [
    "ERC20.approve(address,uint256)",
    "ERC20.decreaseAllowance(address,uint256)",
    "ERC20.increaseAllowance(address,uint256)",
    "ERC20.transfer(address,uint256)",
    "ERC20.transferFrom(address,address,uint256)",
    "ERC20Permit.permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
    "PoolV3.deposit(uint256,address)",
    "PoolV3.depositWithReferral(uint256,address,uint256)",
    "PoolV3.lendCreditAccount(uint256,address)",
    "PoolV3.mint(uint256,address)",
    "PoolV3.mintWithReferral(uint256,address,uint256)",
    "PoolV3.pause()",
    "PoolV3.redeem(uint256,address,address)",
    "PoolV3.repayCreditAccount(uint256,uint256,uint256)",
    "PoolV3.setCreditManagerDebtLimit(address,uint256)",
    "PoolV3.setInterestRateModel(address)",
    "PoolV3.setPoolQuotaKeeper(address)",
    "PoolV3.setQuotaRevenue(uint256)",
    "PoolV3.setTotalDebtLimit(uint256)",
    "PoolV3.setWithdrawFee(uint256)",
    "PoolV3.unpause()",
    "PoolV3.updateQuotaRevenue(int256)",
    "PoolV3.withdraw(uint256,address,address)",
]

READ_ONLY_ENTRY_POINTS = [
    "EIP712.eip712Domain()",
    "ERC20.allowance(address,address)",
    "ERC20.balanceOf(address)",
    "ERC20.name()",
    "ERC20.symbol()",
    "ERC20.totalSupply()",
    "ERC20Permit.DOMAIN_SEPARATOR()",
    "ERC20Permit.nonces(address)",
    "ERC4626.asset()",
    "ERC4626.convertToAssets(uint256)",
    "ERC4626.convertToShares(uint256)",
    "IACLTrait.acl()",
    "IContractsRegisterTrait.contractsRegister()",
    "IPoolV3.interestRateModel()",
    "IPoolV3.lastBaseInterestUpdate()",
    "IPoolV3.lastQuotaRevenueUpdate()",
    "IPoolV3.poolQuotaKeeper()",
    "IPoolV3.treasury()",
    "IPoolV3.withdrawFee()",
    "IVersion.version()",
    "Pausable.paused()",
    "PoolV3.availableLiquidity()",
    "PoolV3.baseInterestIndex()",
    "PoolV3.baseInterestIndexLU()",
    "PoolV3.baseInterestRate()",
    "PoolV3.contractType()",
    "PoolV3.creditManagerBorrowable(address)",
    "PoolV3.creditManagerBorrowed(address)",
    "PoolV3.creditManagerDebtLimit(address)",
    "PoolV3.creditManagers()",
    "PoolV3.decimals()",
    "PoolV3.expectedLiquidity()",
    "PoolV3.expectedLiquidityLU()",
    "PoolV3.maxDeposit(address)",
    "PoolV3.maxMint(address)",
    "PoolV3.maxRedeem(address)",
    "PoolV3.maxWithdraw(address)",
    "PoolV3.previewDeposit(uint256)",
    "PoolV3.previewMint(uint256)",
    "PoolV3.previewRedeem(uint256)",
    "PoolV3.previewWithdraw(uint256)",
    "PoolV3.quotaRevenue()",
    "PoolV3.supplyRate()",
    "PoolV3.totalAssets()",
    "PoolV3.totalBorrowed()",
    "PoolV3.totalDebtLimit()",
    "PoolV3.underlyingToken()",
]

# 4-byte selectors of every state-changing entry point (keccak-based, fixed
# by the immutable ABI).  A wrong function binding changes the selector.
SELECTORS = {
    "ERC20.approve(address,uint256)": "0x095ea7b3",
    "ERC20.decreaseAllowance(address,uint256)": "0xa457c2d7",
    "ERC20.increaseAllowance(address,uint256)": "0x39509351",
    "ERC20.transfer(address,uint256)": "0xa9059cbb",
    "ERC20.transferFrom(address,address,uint256)": "0x23b872dd",
    "ERC20Permit.permit(address,address,uint256,uint256,uint8,bytes32,bytes32)": "0xd505accf",
    "PoolV3.deposit(uint256,address)": "0x6e553f65",
    "PoolV3.depositWithReferral(uint256,address,uint256)": "0xb3d45433",
    "PoolV3.lendCreditAccount(uint256,address)": "0xbf28068b",
    "PoolV3.mint(uint256,address)": "0x94bf804d",
    "PoolV3.mintWithReferral(uint256,address,uint256)": "0xd7337c2e",
    "PoolV3.pause()": "0x8456cb59",
    "PoolV3.redeem(uint256,address,address)": "0xba087652",
    "PoolV3.repayCreditAccount(uint256,uint256,uint256)": "0xca9505e4",
    "PoolV3.setCreditManagerDebtLimit(address,uint256)": "0x79e4e3a9",
    "PoolV3.setInterestRateModel(address)": "0x8bcd4016",
    "PoolV3.setPoolQuotaKeeper(address)": "0x1ab7c7d7",
    "PoolV3.setQuotaRevenue(uint256)": "0x275df3ad",
    "PoolV3.setTotalDebtLimit(uint256)": "0x871d7268",
    "PoolV3.setWithdrawFee(uint256)": "0xb6ac642a",
    "PoolV3.unpause()": "0x3f4ba83a",
    "PoolV3.updateQuotaRevenue(int256)": "0xd6458eea",
    "PoolV3.withdraw(uint256,address,address)": "0xb460af94",
}

# ERC4626 functions PoolV3 overrides: none of them may appear in any flow
# resolved to the ERC4626 implementation (they must resolve to PoolV3).
# Exception: PoolV3.decimals() deliberately calls ERC4626.decimals() with an
# explicit qualified call (`return ERC4626.decimals();`), so that single
# qualified binding is correct and pinned.
ERC4626_OVERRIDDEN = [
    "deposit",
    "mint",
    "withdraw",
    "redeem",
    "maxDeposit",
    "maxMint",
    "maxWithdraw",
    "maxRedeem",
    "previewDeposit",
    "previewMint",
    "previewWithdraw",
    "previewRedeem",
    "totalAssets",
    "_deposit",
    "_withdraw",
    "_convertToShares",
    "_convertToAssets",
]

# Auto-generated public state-variable getters.  Slither models them as
# bodyless interface functions in flattened bundles; the tool must still list
# them as read-only entry points and surface the underlying state read.
# The state-variable qualified name uses the DECLARING contract.
GETTERS = {
    "IACLTrait.acl()": "ACLTrait.acl",
    "IContractsRegisterTrait.contractsRegister()": "ContractsRegisterTrait.contractsRegister",
    "IPoolV3.interestRateModel()": "PoolV3.interestRateModel",
    "IPoolV3.lastBaseInterestUpdate()": "PoolV3.lastBaseInterestUpdate",
    "IPoolV3.lastQuotaRevenueUpdate()": "PoolV3.lastQuotaRevenueUpdate",
    "IPoolV3.poolQuotaKeeper()": "PoolV3.poolQuotaKeeper",
    "IPoolV3.treasury()": "PoolV3.treasury",
    "IPoolV3.withdrawFee()": "PoolV3.withdrawFee",
    "IVersion.version()": "PoolV3.version",
}


def _flow_names(entry):
    return [node["name"] for node in entry["flow"]]


# ─────────────────────────────────────────────────────────────────────────────
# Discovery completeness
# ─────────────────────────────────────────────────────────────────────────────


def test_state_changing_entry_points_exact(entries):
    assert sorted(entries.keys()) == STATE_CHANGING_ENTRY_POINTS


def test_read_only_entry_points_exact(read_only_entries):
    assert sorted(read_only_entries.keys()) == READ_ONLY_ENTRY_POINTS


def test_selectors_match_immutable_abi(entries):
    for name, expected in SELECTORS.items():
        assert name in entries
        flow = entries[name]["flow"]
        assert flow, f"empty flow for {name}"
        assert flow[0]["selector"] == expected, name


# ─────────────────────────────────────────────────────────────────────────────
# Virtual dispatch: the original bug and everything like it
# ─────────────────────────────────────────────────────────────────────────────


def test_deposit_with_referral_resolves_to_poolv3_deposit(entries):
    """Regression: depositWithReferral must call PoolV3.deposit, NOT the
    base ERC4626.deposit, and must never leak a sibling contract."""
    names = _flow_names(entries["PoolV3.depositWithReferral(uint256,address,uint256)"])
    assert "PoolV3.deposit(uint256,address)" in names
    assert not any(name.startswith("ERC4626.deposit") for name in names)
    assert not any("PoolV3_USDT" in name for name in names)


def test_mint_with_referral_resolves_to_poolv3_mint(entries):
    names = _flow_names(entries["PoolV3.mintWithReferral(uint256,address,uint256)"])
    assert "PoolV3.mint(uint256,address)" in names
    assert not any(name.startswith("ERC4626.mint") for name in names)
    assert not any("PoolV3_USDT" in name for name in names)


def test_no_erc4626_overridden_implementation_ever_resolves_to_erc4626(
    entries, read_only_entries
):
    for entry in list(entries.values()) + list(read_only_entries.values()):
        for node in entry["flow"]:
            name = node["name"]
            if not name.startswith("ERC4626."):
                continue
            short = name.split(".")[1].split("(")[0]
            assert short not in ERC4626_OVERRIDDEN, (
                f"{entry['entry_point']} resolves {name} to the base ERC4626 "
                f"implementation, but PoolV3 overrides {short}"
            )


def test_decimals_qualified_call_is_pinned_to_erc4626_only_where_written(
    entries, read_only_entries
):
    """PoolV3.decimals() body is `return ERC4626.decimals();` - a qualified
    call.  It must resolve to ERC4626.decimals() ONLY inside that flow."""
    for entry in list(entries.values()) + list(read_only_entries.values()):
        for node in entry["flow"]:
            if node["name"] == "ERC4626.decimals()":
                assert entry["entry_point"] == "PoolV3.decimals()", (
                    f"ERC4626.decimals() leaked into {entry['entry_point']}; "
                    f"the only qualified call is inside PoolV3.decimals()"
                )
    decimals_flow = read_only_entries["PoolV3.decimals()"]["flow"]
    assert "ERC4626.decimals()" in [node["name"] for node in decimals_flow]


def test_virtual_dispatch_from_inherited_base_code(entries):
    """ERC20.transfer calls _transfer(...) internally.  The deployed type is
    PoolV3, which overrides _transfer (pause guard), so the flow must contain
    PoolV3._transfer.  PoolV3._transfer in turn calls super._transfer(...),
    which is pinned to ERC20._transfer - both must appear."""
    names = _flow_names(entries["ERC20.transfer(address,uint256)"])
    assert "PoolV3._transfer(address,address,uint256)" in names
    assert "ERC20._transfer(address,address,uint256)" in names

    names = _flow_names(entries["ERC20.transferFrom(address,address,uint256)"])
    assert "PoolV3._transfer(address,address,uint256)" in names


def test_deposit_uses_poolv3_internal_implementations(entries):
    names = _flow_names(entries["PoolV3.deposit(uint256,address)"])
    assert "PoolV3._deposit(address,uint256,uint256,uint256)" in names
    assert "PoolV3._amountMinusFee(uint256)" in names
    assert "PoolV3._convertToShares(uint256,Math.Rounding)" in names
    # _mint is inherited from ERC20 (not overridden) and must stay ERC20's.
    assert "ERC20._mint(address,uint256)" in names
    # asset() is inherited from ERC4626 (not overridden) and must stay ERC4626's.
    assert "ERC4626.asset()" in names


def test_withdraw_redeem_use_poolv3_withdraw_implementation(entries):
    withdraw = _flow_names(entries["PoolV3.withdraw(uint256,address,address)"])
    assert "PoolV3._withdraw(address,address,uint256,uint256,uint256,uint256)" in withdraw
    assert "ERC20._burn(address,uint256)" in withdraw
    assert "PoolV3._amountWithWithdrawalFee(uint256)" in withdraw

    redeem = _flow_names(entries["PoolV3.redeem(uint256,address,address)"])
    assert "PoolV3._withdraw(address,address,uint256,uint256,uint256,uint256)" in redeem
    assert "ERC20._burn(address,uint256)" in redeem
    assert "PoolV3._amountMinusWithdrawalFee(uint256)" in redeem


def test_pause_unpause_use_pausable_and_acl_modifiers(entries):
    pause = entries["PoolV3.pause()"]["flow"]
    pause_names = [node["name"] for node in pause]
    assert "Pausable._pause()" in pause_names
    modifier_nodes = [
        (node["name"], node["contract"])
        for node in pause
        if node.get("kind") == "modifier"
    ]
    assert ("ACLTrait.pausableAdminsOnly()", "ACLTrait") in modifier_nodes

    unpause = entries["PoolV3.unpause()"]["flow"]
    assert "Pausable._unpause()" in [node["name"] for node in unpause]


def test_deposit_modifiers_resolve_to_correct_contracts(entries):
    flow = entries["PoolV3.deposit(uint256,address)"]["flow"]
    modifiers = {
        node["name"]: node["contract"]
        for node in flow
        if node.get("kind") == "modifier"
    }
    assert modifiers["Pausable.whenNotPaused()"] == "Pausable"
    assert modifiers["ReentrancyGuardTrait.nonReentrant()"] == "ReentrancyGuardTrait"
    assert modifiers["SanityCheckTrait.nonZeroAddress(address)"] == "SanityCheckTrait"


def test_permit_resolves_to_eip712_and_ecdsa_implementations(entries):
    names = _flow_names(
        entries[
            "ERC20Permit.permit(address,address,uint256,uint256,uint8,bytes32,bytes32)"
        ]
    )
    assert "EIP712._hashTypedDataV4(bytes32)" in names
    assert "ECDSA.recover(bytes32,uint8,bytes32,bytes32)" in names
    assert "ERC20._approve(address,address,uint256)" in names
    assert "ERC20Permit._useNonce(address)" in names


# ─────────────────────────────────────────────────────────────────────────────
# Getter entry points (flattened-bundle modeling)
# ─────────────────────────────────────────────────────────────────────────────


def test_auto_generated_getters_are_read_only_entry_points(read_only_entries):
    for name, state_var_key in GETTERS.items():
        assert name in read_only_entries, f"missing getter entry point {name}"
        entry = read_only_entries[name]
        # Bodyless getter: flow is exactly the entry point itself.
        assert [node["name"] for node in entry["flow"]] == [name]
        assert state_var_key in entry["state_variables_read_keys"], (
            f"{name} does not report reading {state_var_key}: "
            f"{entry['state_variables_read_keys']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Inputs / outputs / msg.sender / state
# ─────────────────────────────────────────────────────────────────────────────


def test_entry_point_inputs_outputs(entries):
    deposit = entries["PoolV3.deposit(uint256,address)"]
    assert [(item["name"], item["type"]) for item in deposit["inputs"]] == [
        ("assets", "uint256"),
        ("receiver", "address"),
    ]
    assert [(item["name"], item["type"]) for item in deposit["outputs"]] == [
        ("shares", "uint256")
    ]

    referral = entries["PoolV3.depositWithReferral(uint256,address,uint256)"]
    assert [(item["name"], item["type"]) for item in referral["inputs"]] == [
        ("assets", "uint256"),
        ("receiver", "address"),
        ("referralCode", "uint256"),
    ]

    permit = entries[
        "ERC20Permit.permit(address,address,uint256,uint256,uint8,bytes32,bytes32)"
    ]
    assert len(permit["inputs"]) == 7
    assert permit["outputs"] == []

    pause = entries["PoolV3.pause()"]
    assert pause["inputs"] == [] and pause["outputs"] == []


def test_reads_msg_sender(entries):
    # permit is the only state-changing entry point that never touches
    # msg.sender (owner is an explicit parameter).
    for name, entry in entries.items():
        expected = name != (
            "ERC20Permit.permit(address,address,uint256,uint256,uint8,bytes32,bytes32)"
        )
        assert entry["reads_msg_sender"] is expected, name


def test_state_variables_written(entries):
    lend = entries["PoolV3.lendCreditAccount(uint256,address)"]
    written = set(lend["state_variables_written_keys"])
    # Debt accounting + interest accrual via _updateBaseInterest.
    for key in (
        "PoolV3._totalDebt",
        "PoolV3._baseInterestRate",
        "PoolV3._baseInterestIndexLU",
        "PoolV3._expectedLiquidityLU",
        "PoolV3.lastBaseInterestUpdate",
        "PoolV3.lastQuotaRevenueUpdate",
        "ReentrancyGuardTrait._reentrancyStatus",
    ):
        assert key in written, f"lendCreditAccount should write {key}: {written}"

    repay = set(
        entries["PoolV3.repayCreditAccount(uint256,uint256,uint256)"][
            "state_variables_written_keys"
        ]
    )
    for key in (
        "PoolV3._totalDebt",
        "ERC20._balances",  # treasury shares mint/burn
        "ERC20._totalSupply",
    ):
        assert key in repay, f"repayCreditAccount should write {key}: {repay}"

    assert entries["PoolV3.setWithdrawFee(uint256)"][
        "state_variables_written_keys"
    ] == ["PoolV3.withdrawFee"]

    assert set(entries["PoolV3.pause()"]["state_variables_written_keys"]) == {
        "Pausable._paused"
    }
