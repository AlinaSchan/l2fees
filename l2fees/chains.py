"""the chains and how each one prices the layer-1 part of a transaction.

kinds:
- `l1`: ethereum itself; execution gas only
- `opstack`: op mainnet, base and the other op stack chains; the GasPriceOracle predeploy at
  0x42..0F answers `getL1Fee(bytes)` for the unsigned transaction
- `arbitrum`: the NodeInterface at 0xc8 answers `gasEstimateL1Component(to, contractCreation, data)`
  with the layer-1 part in units of layer-2 gas
- `scroll`: the L1GasPriceOracle predeploy at 0x53..02 answers `getL1Fee(bytes)`
- `linea`: `linea_estimateGas` prices the bytes through the priority fee it returns
- `zkevm`: polygon zkevm; the gas price it quotes already carries the layer-1 cost, execution gas only

the public endpoints are tried in order; `--rpc chain=url` puts yours first."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    name: str
    chain_id: int
    kind: str
    rpcs: tuple[str, ...]


CHAINS: tuple[Chain, ...] = (
    Chain("ethereum", 1, "l1", ("https://ethereum-rpc.publicnode.com", "https://eth.drpc.org", "https://rpc.mevblocker.io")),
    Chain("arbitrum one", 42161, "arbitrum", ("https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com", "https://arbitrum.drpc.org")),
    Chain("op mainnet", 10, "opstack", ("https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com", "https://optimism.drpc.org")),
    Chain("base", 8453, "opstack", ("https://mainnet.base.org", "https://base-rpc.publicnode.com", "https://base.drpc.org")),
    Chain("unichain", 130, "opstack", ("https://mainnet.unichain.org", "https://unichain-rpc.publicnode.com", "https://unichain.drpc.org")),
    Chain("ink", 57073, "opstack", ("https://rpc-gel.inkonchain.com", "https://ink.drpc.org")),
    Chain("soneium", 1868, "opstack", ("https://rpc.soneium.org", "https://soneium.drpc.org")),
    Chain("world chain", 480, "opstack", ("https://worldchain-mainnet.g.alchemy.com/public", "https://worldchain.drpc.org")),
    Chain("mode", 34443, "opstack", ("https://mainnet.mode.network", "https://mode.drpc.org")),
    Chain("zora", 7777777, "opstack", ("https://rpc.zora.energy", "https://zora.drpc.org")),
    Chain("blast", 81457, "opstack", ("https://rpc.blast.io", "https://blast.drpc.org")),
    Chain("linea", 59144, "linea", ("https://rpc.linea.build", "https://linea.drpc.org", "https://linea-rpc.publicnode.com")),
    Chain("scroll", 534352, "scroll", ("https://rpc.scroll.io", "https://scroll-rpc.publicnode.com", "https://scroll.drpc.org")),
    Chain("polygon zkevm", 1101, "zkevm", ("https://zkevm-rpc.com", "https://polygon-zkevm.drpc.org")),
)

OP_GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"
SCROLL_GAS_PRICE_ORACLE = "0x5300000000000000000000000000000000000002"
ARBITRUM_NODE_INTERFACE = "0x00000000000000000000000000000000000000C8"

# selectors: the first four bytes of keccak256 of the signature, written out so nothing is hashed at runtime
GET_L1_FEE = "49948e0e"  # getL1Fee(bytes)
GAS_ESTIMATE_L1_COMPONENT = "77d488a2"  # gasEstimateL1Component(address,bool,bytes)

# the sender of the simulated calls: an address every chain has seen. nothing is sent, the node only prices.
SENDER = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


ALIASES = {"eth": "ethereum", "mainnet": "ethereum", "arbitrum": "arbitrum one", "arb": "arbitrum one", "optimism": "op mainnet",
           "op": "op mainnet", "worldchain": "world chain", "world": "world chain", "zkevm": "polygon zkevm"}


def by_name(text: str) -> Chain | None:
    key = text.strip().lower().replace("-", " ").replace("_", " ")
    key = ALIASES.get(key, key)
    for c in CHAINS:
        if c.name == key or c.name.replace(" ", "") == key.replace(" ", "") or str(c.chain_id) == key:
            return c
    return None
