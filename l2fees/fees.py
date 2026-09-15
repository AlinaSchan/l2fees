"""the price of gas on a chain, and the layer-1 data fee of a sample transaction by that chain's own oracle."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .chains import (
    ARBITRUM_NODE_INTERFACE,
    GAS_ESTIMATE_L1_COMPONENT,
    GET_L1_FEE,
    OP_GAS_PRICE_ORACLE,
    SCROLL_GAS_PRICE_ORACLE,
    SENDER,
    Chain,
)
from .rpc import RpcError
from .samples import Sample

NOBODY = "0x000000000000000000000000000000000000dEaD"  # an address without code: a call to it runs nothing and reverts nothing


@dataclass(frozen=True)
class Price:
    base: int  # wei per gas, the next block's base fee (0 when the chain has no fee history)
    tip: int  # wei per gas, what the node suggests on top of it
    source: str
    median_tip: int | None = None  # wei per gas, what the last four blocks' median transaction paid on top

    @property
    def per_gas(self) -> int:
        return self.base + self.tip


def abi_bytes(data: bytes) -> str:
    """one dynamic `bytes` argument: offset, length, the bytes padded to a word."""
    padded = data + bytes(-len(data) % 32)
    return (32).to_bytes(32, "big").hex() + len(data).to_bytes(32, "big").hex() + padded.hex()


def gas_price(rpc) -> Price:
    """`eth_gasPrice`, the price the node suggests and a wallet pays, split into the next block's base fee and what
    sits on top; the median priority fee of the last four blocks next to it, from `eth_feeHistory` where a chain has it.
    the suggestion is used, not the median: on the op stack the median tip is a few wei and the suggestion a thousand times
    that, and the suggestion is what goes into the transaction."""
    suggested = int(rpc.call("eth_gasPrice", []), 16)
    try:
        history = rpc.call("eth_feeHistory", ["0x4", "latest", [50]])
        base = int(history["baseFeePerGas"][-1], 16)
        rewards = [int(r[0], 16) for r in history.get("reward") or [] if r]
        median_tip = int(statistics.median(rewards)) if rewards else None
    except (RpcError, KeyError, IndexError, TypeError, ValueError):
        return Price(0, suggested, "eth_gasPrice")
    return Price(min(base, suggested), max(0, suggested - base), "eth_gasPrice, eth_feeHistory", median_tip)


@dataclass(frozen=True)
class Quote:
    sample: str
    gas_used: int
    exec_wei: int
    l1_wei: int | None
    l1_source: str
    note: str = ""

    @property
    def total_wei(self) -> int:
        return self.exec_wei + (self.l1_wei or 0)


def quote(rpc, chain: Chain, sample: Sample, price: Price) -> Quote:
    gas_used = sample.gas_used
    if chain.kind == "opstack" or chain.kind == "scroll":
        oracle = OP_GAS_PRICE_ORACLE if chain.kind == "opstack" else SCROLL_GAS_PRICE_ORACLE
        answer = rpc.eth_call(oracle, "0x" + GET_L1_FEE + abi_bytes(sample.unsigned))
        return Quote(sample.name, gas_used, gas_used * price.per_gas, int.from_bytes(answer[:32], "big"),
                     f"{oracle[:6]}…{oracle[-4:]} getL1Fee")
    if chain.kind == "arbitrum":
        data = "0x" + GAS_ESTIMATE_L1_COMPONENT + sample.to[2:].lower().rjust(64, "0") + "0" * 64 + abi_bytes(sample.calldata)
        answer = rpc.eth_call(ARBITRUM_NODE_INTERFACE, data)
        gas_for_l1, base_fee = int.from_bytes(answer[:32], "big"), int.from_bytes(answer[32:64], "big")
        return Quote(sample.name, gas_used, gas_used * price.per_gas, gas_for_l1 * (base_fee or price.base),
                     f"NodeInterface gasEstimateL1Component: {gas_for_l1:,} gas")
    if chain.kind == "linea":
        try:
            call = {"from": SENDER, "to": NOBODY, "value": "0x0", "data": "0x" + sample.calldata.hex()}
            answer = rpc.call("linea_estimateGas", [call])
            limit, base, priority = (int(answer[k], 16) for k in ("gasLimit", "baseFeePerGas", "priorityFeePerGas"))
        except (RpcError, KeyError, TypeError, ValueError) as exc:
            return Quote(sample.name, gas_used, gas_used * price.per_gas, None, "",
                         f"no linea_estimateGas here ({str(exc)[:60]}); bytes unpriced")
        return Quote(sample.name, gas_used, gas_used * base, limit * priority, f"linea_estimateGas: {limit:,} gas x priority fee")
    note = "" if chain.kind == "l1" else "the gas price carries the layer-1 cost"
    return Quote(sample.name, gas_used, gas_used * price.per_gas, None, "", note)


@dataclass(frozen=True)
class ChainResult:
    chain: Chain
    price: Price | None
    quotes: list[Quote]
    error: str = ""
    endpoint: str = ""
