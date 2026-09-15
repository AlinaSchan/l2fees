"""offline: rlp, the two samples taken apart, every kind of chain against a fake node, the table, the json and the daily file."""
import csv
import json

import pytest

from l2fees import chains, cli, fees, rlp
from l2fees.chains import ARBITRUM_NODE_INTERFACE, OP_GAS_PRICE_ORACLE, SCROLL_GAS_PRICE_ORACLE, Chain, by_name
from l2fees.fees import Price, abi_bytes, gas_price, quote
from l2fees.rpc import RpcError, RpcUnavailable
from l2fees.samples import SWAP, TRANSFER

ITEMS = (b"", b"\x00", b"\x7f", b"\x80", b"dog", b"x" * 55, b"y" * 56, b"z" * 1024, [], [b"cat", b"dog"], [[], [[]], [b"a", [b"b"]]])


def test_rlp_round_trips():
    for item in ITEMS:
        assert rlp.decode(rlp.encode(item)) == item
    assert rlp.encode(b"dog") == b"\x83dog" and rlp.encode([]) == b"\xc0"
    assert rlp.encode(0) == b"\x80" and rlp.encode(1024) == b"\x82\x04\x00"
    assert rlp.to_int(b"") == 0 and rlp.to_int(b"\x52\x08") == 21000
    with pytest.raises(ValueError):
        rlp.decode(b"\x83dogs")


def test_the_samples_are_the_transactions_they_say():
    f = TRANSFER.fields
    assert len(f) == 12 and rlp.to_int(f[0]) == 1 and rlp.to_int(f[1]) == 13 and TRANSFER.gas_limit == 21000 and TRANSFER.calldata == b""
    assert TRANSFER.to == "0xb1f832375a874e1419260911f8a54673f4cac3b7" and rlp.to_int(f[6]) == 0x06D3A459A8C029 and f[8] == []
    assert TRANSFER.unsigned[0] == 2 and len(rlp.decode(TRANSFER.unsigned[1:])) == 9 and len(TRANSFER.unsigned) == 48
    assert SWAP.to == "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad" and SWAP.gas_limit == 202_495 and SWAP.gas_used == 140_642
    assert len(SWAP.calldata) == 772 and SWAP.calldata[:4].hex() == "3593564c" and SWAP.size == 892
    assert rlp.decode(SWAP.unsigned[1:])[7] == SWAP.calldata


def test_abi_bytes():
    assert abi_bytes(b"") == (32).to_bytes(32, "big").hex() + bytes(32).hex()
    assert abi_bytes(b"ab") == (32).to_bytes(32, "big").hex() + (2).to_bytes(32, "big").hex() + b"ab".hex() + "00" * 30
    assert len(abi_bytes(TRANSFER.unsigned)) == 2 * (64 + 64)  # 48 bytes padded to two words


GWEI = 10**9
BASES = {"l1": 56_766_000, "opstack": 5_000_000, "arbitrum": 20_000_000, "scroll": 120_000, "linea": 7, "zkevm": 10_000_000}
TIPS = {"l1": 10_000_000, "opstack": 1_000_000, "arbitrum": 0, "scroll": 100, "linea": 163_716_154, "zkevm": 0}


class FakeRpc:
    """one fake per chain kind: fee history, the oracles, linea's estimator."""

    def __init__(self, kind, chain_id=1, no_history=False, no_linea=False):
        self.kind, self.id, self.no_history, self.no_linea = kind, chain_id, no_history, no_linea
        self.urls = ["https://fake"]
        self.calls = []

    def call(self, method, params):
        self.calls.append(method)
        if method == "eth_chainId":
            return hex(self.id)
        if method == "eth_gasPrice":
            return hex(BASES[self.kind] + TIPS[self.kind])
        if method == "eth_feeHistory":
            if self.no_history:
                raise RpcError("method not found")
            base = BASES[self.kind]
            tip = TIPS[self.kind]
            return {"baseFeePerGas": [hex(base)] * 5, "reward": [[hex(tip)], [hex(tip * 3)], [hex(tip)], [hex(0)]]}
        if method == "linea_estimateGas":
            if self.no_linea:
                raise RpcError("the method linea_estimateGas does not exist")
            data = bytes.fromhex(params[0]["data"][2:])
            limit = 21_000 + 16 * len(data)
            return {"gasLimit": hex(limit), "baseFeePerGas": "0x7", "priorityFeePerGas": hex(39_657_142 if not data else 61_000_000)}
        if method == "eth_call":
            to, data = params[0]["to"].lower(), params[0]["data"]
            payload = bytes.fromhex(data[10:])
            if to == OP_GAS_PRICE_ORACLE.lower() and data[2:10] == chains.GET_L1_FEE:
                size = int.from_bytes(payload[32:64], "big")  # the unsigned bytes: the fee grows with them
                return "0x" + (585_170_000 + 2_000_000 * size).to_bytes(32, "big").hex()
            if to == SCROLL_GAS_PRICE_ORACLE.lower() and data[2:10] == chains.GET_L1_FEE:
                return "0x" + (288_000_000_000).to_bytes(32, "big").hex()
            if to == ARBITRUM_NODE_INTERFACE.lower() and data[2:10] == chains.GAS_ESTIMATE_L1_COMPONENT:
                size = int.from_bytes(payload[96:128], "big")  # the calldata length
                words = [211 + size, 20_000_000, 1_700_000]
                return "0x" + "".join(w.to_bytes(32, "big").hex() for w in words)
            raise RpcError("execution reverted")
        raise RpcError(f"unknown method {method}")

    def chain_id(self):
        return int(self.call("eth_chainId", []), 16)

    def eth_call(self, to, data):
        return bytes.fromhex(self.call("eth_call", [{"to": to, "data": data}, "latest"])[2:])


def test_gas_price():
    p = gas_price(FakeRpc("l1"))
    assert p.base == 56_766_000 and p.tip == 10_000_000 and p.per_gas == 66_766_000 and p.source == "eth_gasPrice, eth_feeHistory"
    assert p.median_tip == 10_000_000  # the median of 1x, 3x, 1x, 0 times the tip
    p = gas_price(FakeRpc("l1", no_history=True))
    assert p.per_gas == 66_766_000 and p.base == 0 and p.tip == 66_766_000 and p.source == "eth_gasPrice" and p.median_tip is None


def test_quotes_per_kind():
    op = Chain("base", 8453, "opstack", ())
    q = quote(FakeRpc("opstack"), op, TRANSFER, Price(5_000_000, 1_000_000, "eth_feeHistory"))
    assert q.exec_wei == 21_000 * 6_000_000 and q.l1_wei == 585_170_000 + 2_000_000 * 48 and q.total_wei == q.exec_wei + q.l1_wei
    assert "getL1Fee" in q.l1_source
    big = quote(FakeRpc("opstack"), op, SWAP, Price(5_000_000, 1_000_000, "eth_feeHistory"))
    assert big.l1_wei > q.l1_wei and big.exec_wei == 140_642 * 6_000_000
    arb = quote(FakeRpc("arbitrum"), Chain("arbitrum one", 42161, "arbitrum", ()), SWAP, Price(20_000_000, 0, "eth_feeHistory"))
    assert arb.l1_wei == (211 + 772) * 20_000_000 and arb.exec_wei == 140_642 * 20_000_000 and "983 gas" in arb.l1_source
    scroll = quote(FakeRpc("scroll"), Chain("scroll", 534352, "scroll", ()), TRANSFER, Price(120_000, 100, "eth_feeHistory"))
    assert scroll.l1_wei == 288_000_000_000 and scroll.exec_wei == 21_000 * 120_100
    linea = quote(FakeRpc("linea"), Chain("linea", 59144, "linea", ()), TRANSFER, Price(7, 163_716_154, "eth_feeHistory"))
    assert linea.exec_wei == 21_000 * 7 and linea.l1_wei == 21_000 * 39_657_142 and linea.note == ""
    linea_swap = quote(FakeRpc("linea"), Chain("linea", 59144, "linea", ()), SWAP, Price(7, 163_716_154, "eth_feeHistory"))
    assert linea_swap.exec_wei == 140_642 * 7 and linea_swap.l1_wei == (21_000 + 16 * 772) * 61_000_000
    blind = quote(FakeRpc("linea", no_linea=True), Chain("linea", 59144, "linea", ()), TRANSFER, Price(7, 163_716_154, "eth_feeHistory"))
    assert blind.l1_wei is None and "bytes unpriced" in blind.note and blind.exec_wei == 21_000 * 163_716_161
    plain = quote(FakeRpc("l1"), Chain("ethereum", 1, "l1", ()), TRANSFER, Price(56_766_000, 10_000_000, "eth_feeHistory"))
    assert plain.l1_wei is None and plain.total_wei == 21_000 * 66_766_000 and plain.note == ""
    zk = quote(FakeRpc("zkevm"), Chain("polygon zkevm", 1101, "zkevm", ()), TRANSFER, Price(10_000_000, 0, "eth_feeHistory"))
    assert zk.l1_wei is None and "carries the layer-1 cost" in zk.note


def test_by_name():
    assert by_name("base").chain_id == 8453 and by_name("Arbitrum-One").name == "arbitrum one" and by_name("10").name == "op mainnet"
    assert by_name("opmainnet").name == "op mainnet" and by_name("solana") is None
    assert by_name("arbitrum").chain_id == 42161 and by_name("optimism").chain_id == 10 and by_name("zkevm").chain_id == 1101


FAKES = {c.name: FakeRpc(c.kind, c.chain_id) for c in chains.CHAINS}


def fake_rpc_factory(urls, timeout=25.0):
    for c in chains.CHAINS:
        if urls[0] in c.rpcs or urls[0] == "https://mine.example":
            return FAKES[c.name]
    raise AssertionError(urls)


def test_cli_table_json_and_daily_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "Rpc", fake_rpc_factory)
    assert cli.main(["--eth-usd", "2479.6"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith("what a transaction costs right now, at $2,480 an eth (given)")
    assert lines[4].startswith("ethereum") and "0.0668" in lines[4] and "0.348¢" in lines[4] and "2.33¢" in lines[4]
    rollups = [line.split("  ")[0].strip() for line in lines[5:5 + len(chains.CHAINS) - 1]]
    assert "ethereum" not in rollups and len(rollups) == len(chains.CHAINS) - 1  # the cheapest transfer first, ethereum on top
    totals = [int(c["quotes"]["transfer"]["total_wei"]) for c in json.loads(run_json(monkeypatch, capsys))["chains"][1:]]
    assert totals == sorted(totals)
    assert "polygon zkevm: the gas price carries the layer-1 cost" in out
    assert cli.main(["--json", "--chains", "base,linea", "--eth-usd", "2000"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert sorted(c["chain"] for c in doc["chains"]) == ["base", "linea"]
    base = next(c for c in doc["chains"] if c["chain"] == "base")
    assert base["quotes"]["transfer"]["l1_wei"] == 585_170_000 + 2_000_000 * 48
    assert base["quotes"]["swap"]["total_usd"] > base["quotes"]["transfer"]["total_usd"]
    assert doc["samples"][1]["hash"] == SWAP.hash and doc["eth_usd"] == 2000
    path = tmp_path / "daily.csv"
    assert cli.main(["--summary-append", str(path), "--quiet", "--no-usd"]) == 0
    assert cli.main(["--summary-append", str(path), "--quiet", "--no-usd"]) == 0  # the same day again: replaced, not doubled
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(chains.CHAINS) and rows[0]["chain"] == "ethereum"
    assert rows[0]["transfer_l1_wei"] == "" and rows[0]["eth_usd"] == ""
    assert int(next(r for r in rows if r["chain"] == "base")["transfer_total_wei"]) == 21_000 * 6_000_000 + 585_170_000 + 2_000_000 * 48


def run_json(monkeypatch, capsys) -> str:
    monkeypatch.setattr(cli, "Rpc", fake_rpc_factory)
    assert cli.main(["--json", "--no-usd"]) == 0
    return capsys.readouterr().out


def test_cli_no_usd_rpc_override_and_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Rpc", fake_rpc_factory)
    assert cli.main(["--no-usd", "--chains", "ethereum", "--rpc", "ethereum=https://mine.example"]) == 0
    out = capsys.readouterr().out
    assert "in ether: no price source answered" in out and "1.40e-06" in out
    assert cli.main(["--chains", "solana"]) == 2 and cli.main(["--rpc", "base"]) == 2

    class Down:
        def __init__(self, urls, timeout=25.0):
            self.urls = list(urls)

        def chain_id(self):
            raise RpcUnavailable("all down")

    monkeypatch.setattr(cli, "Rpc", Down)
    assert cli.main(["--no-usd", "--chains", "base"]) == 2 and "all down" in capsys.readouterr().err


def test_wrong_chain_id_is_reported_not_priced(monkeypatch):
    monkeypatch.setattr(cli, "Rpc", lambda urls, timeout=25.0: FakeRpc("opstack", chain_id=10))
    result = cli.read_chain(Chain("base", 8453, "opstack", ("https://fake",)), {})
    assert result.error == "endpoint answers chain id 10, not 8453" and result.quotes == [] and result.price is None
    assert fees.gas_price(FakeRpc("opstack")).base == 5_000_000


def test_formatting():
    assert cli.money(None) == "-" and cli.money(1.5) == "$1.50" and cli.money(0.0035) == "0.35¢" and cli.money(0.000054) == "0.0054¢"
    assert cli.money(0.0000054) == "0.0005¢" and cli.money(0.234) == "23.4¢"
    assert cli.gwei(66_766_000) == "0.0668" and cli.gwei(1_001) == "1e-06"
