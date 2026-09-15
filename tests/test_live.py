"""talks to the public endpoints. skipped unless L2FEES_LIVE=1."""
import os

import pytest

from l2fees import chains
from l2fees.cli import read_chain
from l2fees.rpc import Rpc
from l2fees.samples import SAMPLES

pytestmark = pytest.mark.skipif(os.environ.get("L2FEES_LIVE") != "1", reason="set L2FEES_LIVE=1")


@pytest.mark.parametrize("chain", chains.CHAINS, ids=[c.name for c in chains.CHAINS])
def test_every_chain_answers_with_its_own_id_and_prices_both_samples(chain):
    result = read_chain(chain, {})
    assert not result.error, result.error
    assert result.price and result.price.per_gas > 0
    transfer, swap = result.quotes
    assert transfer.exec_wei > 0 and swap.exec_wei > transfer.exec_wei
    if chain.kind in ("opstack", "scroll", "arbitrum"):
        assert transfer.l1_wei is not None and transfer.l1_wei > 0 and swap.l1_wei > transfer.l1_wei
    if chain.kind == "linea":
        assert transfer.l1_wei is not None and transfer.l1_wei > 0


def test_the_samples_are_on_mainnet_as_described():
    rpc = Rpc(chains.CHAINS[0].rpcs)
    for s in SAMPLES:
        tx = rpc.call("eth_getTransactionByHash", [s.hash])
        assert tx and int(tx["blockNumber"], 16) == s.block and tx["to"].lower() == s.to and int(tx["gas"], 16) == s.gas_limit
        assert bytes.fromhex(tx["input"][2:]) == s.calldata
        receipt = rpc.call("eth_getTransactionReceipt", [s.hash])
        assert int(receipt["gasUsed"], 16) == s.gas_used
