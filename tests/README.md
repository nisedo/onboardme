# Backend Test Suite

Regression tests for entry-point discovery and execution-flow resolution.

The suite runs against **immutable deployed contracts** registered in
[`targets.py`](targets.py).  Because deployed bytecode can never change,
there is exactly one correct answer for every assertion: entry-point
discovery must be complete, and every node of every execution flow must
resolve to the C3-most-derived implementation on the deployed type.

## Running the tests

From the repository root:

```bash
# Install the dev-only dependency (one time)
pip install -r requirements-dev.txt

# Run the full suite
python -m pytest tests/ -v
```

### First run fetches + caches the contract source

The first run per target fetches the verified source from Etherscan
(requires `ETHERSCAN_API_KEY` in your `.env`) and **caches it** under
`crytic-export/etherscan-contracts/...`.  The contract is immutable, so the
cache never goes stale: every subsequent run is fully offline and reuses the
cached bundle.  The cached bundle is also shared with the normal tool, so
running the tests first also warms the tool's cache and vice versa.

## Adding a new smart contract

The suite is registry-driven: everything generic runs automatically for any
new entry in the registry.

1. **Register the target** in [`tests/targets.py`](targets.py):

   ```python
   TARGETS = [
       ...
       {
           "id": "my_contract_mainnet",   # stable id (snapshot file name)
           "address": "0x...",
           "chain": "mainnet",
           "contract": "MyContract",      # verified contract name
       },
   ]
   ```

2. **Run the suite.** The generic invariants in
   [`tests/test_discovery.py`](test_discovery.py) now apply to the new
   contract (deployed-contract resolution, flow structure, selector
   consistency, nothing resolved outside the deployed chain, interfaces never
   walked, getters surface their state reads).

3. **Create the golden snapshot** (the full flow of every entry point):

   ```bash
   python -m pytest tests/ --snapshot-update
   ```

   This writes `tests/data/{target_id}_snapshot.json`.  Review it once: the
   snapshot becomes the ground truth that catches future regressions.

4. **(Optional, recommended) add contract-specific ground-truth tests** under
   `tests/contracts/` — see
   [`tests/contracts/test_poolv3_mainnet.py`](contracts/test_poolv3_mainnet.py)
   for the reference implementation.  Gate the module to its target:

   ```python
   @pytest.fixture(autouse=True)
   def _my_contract_only(target):
       skip_unless_target(target, "my_contract_mainnet")
   ```

   Here is where you assert the contract-specific facts a generic suite
   cannot know: the exact list of entry points, hardcoded selectors, and
   which call inside which flow must resolve to which implementation.

### Updating a golden snapshot

If you intentionally change the code and the snapshot diff is *correct*
(i.e. the new behavior is the right interpretation of the immutable
contract), regenerate it with:

```bash
python -m pytest tests/ --snapshot-update
```

**Never update a snapshot to make a test pass without reviewing the diff.**
A snapshot change means the tool now resolves some flow differently than
before - either the change is a regression (fix the code) or the old
behavior was wrong (keep the change and update the snapshot).  There is no
third option because the on-chain contract is immutable.

## What is covered

Generic, for every registered target ([`tests/test_discovery.py`](test_discovery.py)):

* The deployed contract is identified and becomes the analysis root.
* Entry points are non-empty and attributed to the root; the two entry
  classes (state-changing vs read-only) never overlap.
* Every flow starts with its own entry point and never walks the same
  callable twice.
* The entry node's selector matches the keccak selector of its own ABI
  signature.
* No node of any flow resolves to a contract outside the deployed type's own
  C3 chain; interface declarations are never walked.
* Auto-generated public state-variable getters surface their state read.
* Golden snapshot of the full flow of every single entry point.

Contract-specific, for `poolv3_mainnet`
([`tests/contracts/test_poolv3_mainnet.py`](contracts/test_poolv3_mainnet.py)):

* Exact entry-point surface: all 23 state-changing and all 47 view/pure
  functions of the deployed ABI (including getters like `treasury()`).
* Hardcoded selectors of every state-changing entry point.
* Virtual dispatch regression: `depositWithReferral -> PoolV3.deposit`
  (never `ERC4626.deposit`, never a sibling contract), `mintWithReferral ->
  PoolV3.mint`, inherited-base virtual calls (`ERC20.transfer ->
  PoolV3._transfer`), qualified calls pinned to base
  (`PoolV3.decimals -> ERC4626.decimals`), and `super._transfer ->
  ERC20._transfer`.
* Modifiers resolve to the right declaring contract, inputs/outputs match
  the ABI, `msg.sender` reads and state-variable writes match the source.

## Notes

* Flow *order* is intentionally not asserted: Slither's IR traversal order
  is not guaranteed to be stable across runs.  Flow *content* (the resolved
  implementation of every call) is what matters and is asserted everywhere.
* `msg_sender_constrained` is asserted for its current (conservative) value:
  access-control checks that live inside external contracts (e.g. the ACL
  contract behind `pausableAdminsOnly`) are not modeled as sender
  constraints.
