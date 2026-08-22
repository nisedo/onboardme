"""Registry of immutable deployed contracts covered by the backend suite.

To add a new smart contract to the test suite, append one entry here:

    {
        "id": "my_contract_mainnet",          # stable id (used for snapshot file name)
        "address": "0x...",                   # deployed address
        "chain": "mainnet",                   # chain name or id (see README)
        "contract": "MyContract",             # verified contract name
    },

Then run the suite.  The generic tests in ``test_discovery.py`` run
automatically for the new target; the full-flow golden snapshot is created
with ``--snapshot-update``.  Optionally add contract-specific ground-truth
assertions under ``tests/contracts/`` (see ``tests/README.md``).

The first run fetches the verified source from Etherscan (requires
``ETHERSCAN_API_KEY``) and caches it under ``crytic-export/``; deployed
bytecode is immutable, so the cache never goes stale.
"""

TARGETS = [
    {
        "id": "poolv3_mainnet",
        "address": "0x683FAf5BAFd88d4c383cCaf3d61C26AF2E164409",
        "chain": "mainnet",
        "contract": "PoolV3",
    },
]
