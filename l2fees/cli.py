"""command line entry point: l2fees [--chains base,arbitrum] [--json] [--summary-append FILE]"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import __version__
from .chains import CHAINS, Chain, by_name
from .fees import ChainResult, gas_price, quote
from .rpc import Rpc, RpcError, RpcUnavailable
from .samples import SAMPLES

USER_AGENT = "l2fees/0.1 (+https://github.com/alinaschanz/l2fees)"
SUMMARY_FIELDS = ("date_utc", "time_utc", "chain", "chain_id", "base_fee_wei", "tip_wei", "transfer_exec_wei", "transfer_l1_wei",
                  "transfer_total_wei", "swap_exec_wei", "swap_l1_wei", "swap_total_wei", "eth_usd")


def _get_json(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def eth_usd(timeout: float = 15.0) -> tuple[float, str] | None:
    """coingecko, then coinbase, then kraken: the first one that answers."""
    for name, url, pick in (
        ("coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd", lambda d: d["ethereum"]["usd"]),
        ("coinbase", "https://api.coinbase.com/v2/prices/ETH-USD/spot", lambda d: d["data"]["amount"]),
        ("kraken", "https://api.kraken.com/0/public/Ticker?pair=ETHUSD", lambda d: d["result"]["XETHZUSD"]["c"][0]),
    ):
        try:
            return float(pick(_get_json(url, timeout))), name
        except Exception:  # any failure means "ask the next one"
            continue
    return None


def money(usd: float | None) -> str:
    if usd is None:
        return "-"
    if usd >= 1:
        return f"${usd:,.2f}"
    cents = usd * 100
    return f"{cents:.3g}¢" if cents >= 0.001 else f"{cents:.4f}¢"


def gwei(wei: int) -> str:
    return f"{wei / 1e9:.4f}" if wei >= 1e5 else f"{wei / 1e9:.3g}"


def read_chain(chain: Chain, overrides: dict[str, str]) -> ChainResult:
    urls = ([overrides[chain.name]] if chain.name in overrides else []) + list(chain.rpcs)
    rpc = Rpc(urls)
    try:
        found = rpc.chain_id()
        if found != chain.chain_id:
            return ChainResult(chain, None, [], f"endpoint answers chain id {found}, not {chain.chain_id}")
        price = gas_price(rpc)
        quotes = [quote(rpc, chain, s, price) for s in SAMPLES]
    except (RpcError, RpcUnavailable) as exc:
        return ChainResult(chain, None, [], str(exc)[:160])
    return ChainResult(chain, price, quotes, endpoint=rpc.urls[0])


def summary(results: list[ChainResult], usd: tuple[float, str] | None, stamp: datetime) -> dict:
    rate = usd[0] if usd else None

    def dollars(wei: int | None) -> float | None:
        return None if wei is None or rate is None else wei / 1e18 * rate

    chains = []
    for r in results:
        item = {"chain": r.chain.name, "chain_id": r.chain.chain_id, "kind": r.chain.kind, "endpoint": r.endpoint, "error": r.error,
                "base_fee_wei": r.price.base if r.price else None, "tip_wei": r.price.tip if r.price else None,
                "median_tip_wei": r.price.median_tip if r.price else None,
                "price_source": r.price.source if r.price else None, "quotes": {}}
        for q in r.quotes:
            item["quotes"][q.sample] = {"gas_used": q.gas_used, "exec_wei": q.exec_wei, "l1_wei": q.l1_wei, "total_wei": q.total_wei,
                                        "exec_usd": dollars(q.exec_wei), "l1_usd": dollars(q.l1_wei), "total_usd": dollars(q.total_wei),
                                        "l1_source": q.l1_source, "note": q.note}
        chains.append(item)
    return {"time_utc": stamp.isoformat(), "eth_usd": rate, "eth_usd_source": usd[1] if usd else None,
            "samples": [{"name": s.name, "what": s.what, "hash": s.hash, "block": s.block, "gas_used": s.gas_used, "bytes": s.size,
                         "calldata_bytes": len(s.calldata)} for s in SAMPLES],
            "chains": chains}


def order(results: list[ChainResult]) -> list[ChainResult]:
    """ethereum first, then the rollups from the cheapest transfer up, the ones that did not answer last."""
    def key(r: ChainResult):
        if r.chain.kind == "l1":
            return (0, 0)
        if r.error or not r.quotes:
            return (2, 0)
        return (1, r.quotes[0].total_wei)
    return sorted(results, key=key)


def table(s: dict) -> str:
    price = f"at ${s['eth_usd']:,.0f} an eth ({s['eth_usd_source']})" if s["eth_usd"] else "in ether: no price source answered"
    lines = [f"what a transaction costs right now, {price}. {s['time_utc'][:16].replace('T', ' ')} utc", ""]
    transfer, swap = s["samples"]
    head_t = f"transfer, {transfer['gas_used']:,} gas"
    head_w = f"swap, {swap['gas_used']:,} gas, {swap['calldata_bytes']} bytes of calldata"
    lines.append(f"{'':<14} {'':>11}  {head_t:^29}   {head_w:^29}")
    lines.append(f"{'chain':<14} {'gas price':>11}  {'exec':>9} {'l1 data':>9} {'total':>9}   {'exec':>9} {'l1 data':>9} {'total':>9}")

    def cell(q: dict, key: str) -> str:
        if s["eth_usd"]:
            return money(q[key + "_usd"])
        wei = q[key + "_wei"]
        return "-" if wei is None else f"{wei / 1e18:.2e}"

    notes = []
    for c in s["chains"]:
        if c["error"]:
            lines.append(f"{c['chain']:<14} {'-':>11}  {c['error'][:70]}")
            continue
        t, w = c["quotes"]["transfer"], c["quotes"]["swap"]
        lines.append(f"{c['chain']:<14} {gwei(c['base_fee_wei'] + c['tip_wei']):>11}  "
                     f"{cell(t, 'exec'):>9} {cell(t, 'l1'):>9} {cell(t, 'total'):>9}   "
                     f"{cell(w, 'exec'):>9} {cell(w, 'l1'):>9} {cell(w, 'total'):>9}")
        if t["note"]:
            notes.append(f"{c['chain']}: {t['note']}")
    lines.append("")
    lines += [f"  {n}" for n in dict.fromkeys(notes)]
    if notes:
        lines.append("")
    lines += ["gas price: what the node suggests (eth_gasPrice) and a wallet pays, in gwei: the base fee and a tip on top.",
              "exec: gas used x gas price. l1 data: what the rollup's own oracle charges for the bytes of that transaction",
              "on ethereum; ethereum has none, and polygon zkevm folds it into its gas price. the two transactions are real",
              "ones from mainnet (hashes in the readme); the swap's calldata is priced as it is, its execution gas as it was used.",
              "numbers, not calls: a cheap chain is a cheap chain right now, this table says nothing about tomorrow."]
    return "\n".join(line.rstrip() for line in lines)


def summary_rows(s: dict) -> list[dict]:
    stamp = s["time_utc"]
    out = []
    for c in s["chains"]:
        if c["error"]:
            continue
        t, w = c["quotes"]["transfer"], c["quotes"]["swap"]
        out.append({"date_utc": stamp[:10], "time_utc": stamp[11:19], "chain": c["chain"], "chain_id": c["chain_id"],
                    "base_fee_wei": c["base_fee_wei"], "tip_wei": c["tip_wei"],
                    "transfer_exec_wei": t["exec_wei"], "transfer_l1_wei": t["l1_wei"] if t["l1_wei"] is not None else "",
                    "transfer_total_wei": t["total_wei"], "swap_exec_wei": w["exec_wei"],
                    "swap_l1_wei": w["l1_wei"] if w["l1_wei"] is not None else "", "swap_total_wei": w["total_wei"],
                    "eth_usd": f"{s['eth_usd']:.2f}" if s["eth_usd"] else ""})
    return out


def append_summary(path: str, rows: list[dict]) -> None:
    """one row per chain per utc date: a rerun on the same day replaces that day's rows."""
    existing: list[dict] = []
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, newline="", encoding="utf-8") as f:
            existing = [r for r in csv.DictReader(f) if r.get("date_utc")]
    fresh = {r["date_utc"] for r in rows}
    merged = [r for r in existing if r["date_utc"] not in fresh] + rows
    merged.sort(key=lambda r: r["date_utc"])  # stable: the chain order stays
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="l2fees",
                                 description="what a transaction costs right now on ethereum and the rollups, by their own oracles.")
    ap.add_argument("--chains", default="all", help=f"comma separated, or all (default): {', '.join(c.name for c in CHAINS)}")
    ap.add_argument("--json", action="store_true", help="json instead of the table")
    ap.add_argument("--summary-append", metavar="PATH", help="one row per chain appended to a csv (one set per utc date)")
    ap.add_argument("--quiet", action="store_true", help="no table on stdout")
    ap.add_argument("--rpc", action="append", default=[], metavar="CHAIN=URL", help="your endpoint for a chain, tried first (repeatable)")
    ap.add_argument("--eth-usd", type=float, default=None, help="use this ether price instead of asking coingecko")
    ap.add_argument("--no-usd", action="store_true", help="ether only, no price lookup")
    ap.add_argument("--workers", type=int, default=4, help="chains read at the same time (default 4)")
    ap.add_argument("--version", action="version", version=f"l2fees {__version__}")
    args = ap.parse_args(argv)

    if args.chains.strip().lower() == "all":
        chains = list(CHAINS)
    else:
        chains = []
        for text in args.chains.split(","):
            found = by_name(text)
            if not found:
                print(f"error: unknown chain {text.strip()!r}, pick from {', '.join(c.name for c in CHAINS)}", file=sys.stderr)
                return 2
            chains.append(found)
    overrides = {}
    for item in args.rpc:
        name, _, url = item.partition("=")
        found = by_name(name)
        if not found or not url.startswith("http"):
            print(f"error: --rpc wants CHAIN=URL, got {item!r}", file=sys.stderr)
            return 2
        overrides[found.name] = url

    usd = None if args.no_usd else ((args.eth_usd, "given") if args.eth_usd else eth_usd())
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(lambda c: read_chain(c, overrides), chains))
    results = order(results)
    if all(r.error for r in results):
        print(f"error: no chain answered ({results[0].error})", file=sys.stderr)
        return 2
    s = summary(results, usd, datetime.now(tz=timezone.utc).replace(microsecond=0))
    if args.summary_append:
        append_summary(args.summary_append, summary_rows(s))
    if args.quiet:
        return 0
    print(json.dumps(s, indent=2) if args.json else table(s))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
