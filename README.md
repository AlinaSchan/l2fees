# l2fees

[![ci](https://github.com/AlinaSchan/l2fees/actions/workflows/ci.yml/badge.svg)](https://github.com/AlinaSchan/l2fees/actions/workflows/ci.yml)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license mit](https://img.shields.io/badge/license-MIT-2b7a74)
[![release](https://img.shields.io/github/v/release/AlinaSchan/l2fees?color=2b7a74)](https://github.com/AlinaSchan/l2fees/releases)
[![openssf scorecard](https://api.scorecard.dev/projects/github.com/AlinaSchan/l2fees/badge)](https://scorecard.dev/viewer/?uri=github.com/AlinaSchan/l2fees)

what a transaction costs right now on ethereum and thirteen rollups. two real transactions from
mainnet, a plain transfer and a uniswap swap, priced on every chain the way the chain itself prices
them: the execution gas at the gas price the node suggests, and the layer-1 data fee from the
chain's own oracle for the bytes of that transaction. public endpoints, no keys, no fee tracker
in between.

```
$ l2fees
what a transaction costs right now, at $2,475 an eth (coingecko). 2026-09-15 12:05 utc

                                transfer, 21,000 gas        swap, 140,642 gas, 772 bytes of calldata
chain            gas price       exec   l1 data     total        exec   l1 data     total
ethereum            0.0647     0.336¢         -    0.336¢       2.25¢         -     2.25¢
blast               0.0010    0.0052¢   0.0000¢  0.00523¢     0.0348¢   0.0001¢   0.0349¢
ink                 0.0010    0.0052¢   0.0002¢  0.00539¢     0.0348¢   0.0004¢   0.0352¢
op mainnet          0.0010    0.0052¢   0.0002¢  0.00543¢     0.0348¢   0.0005¢   0.0353¢
soneium             0.0010    0.0052¢   0.0004¢  0.00561¢     0.0348¢   0.0009¢   0.0357¢
unichain            0.0015    0.0078¢   0.0001¢  0.00793¢     0.0522¢   0.0003¢   0.0525¢
mode                0.0010    0.0052¢  0.00276¢  0.00796¢     0.0348¢  0.00579¢   0.0406¢
zora                0.0010    0.0052¢  0.00278¢  0.00797¢     0.0348¢  0.00583¢   0.0406¢
world chain         0.0015    0.0078¢   0.0003¢  0.00812¢     0.0522¢   0.0007¢   0.0529¢
scroll              0.0001    0.0006¢   0.0294¢     0.03¢    0.00418¢    0.544¢    0.548¢
base                0.0060    0.0312¢   0.0002¢   0.0314¢      0.209¢   0.0004¢    0.209¢
polygon zkevm       0.0100     0.052¢         -    0.052¢      0.348¢         -    0.348¢
arbitrum one        0.0200     0.104¢   0.0009¢    0.105¢      0.696¢   0.0009¢    0.697¢
linea               0.0503    0.0000¢    0.197¢    0.197¢     0.0000¢     0.34¢     0.34¢

  polygon zkevm: the gas price carries the layer-1 cost

gas price: what the node suggests (eth_gasPrice) and a wallet pays, in gwei: the base fee and a tip on top.
exec: gas used x gas price. l1 data: what the rollup's own oracle charges for the bytes of that transaction
on ethereum; ethereum has none, and polygon zkevm folds it into its gas price. the two transactions are real
ones from mainnet (hashes in the readme); the swap's calldata is priced as it is, its execution gas as it was used.
numbers, not calls: a cheap chain is a cheap chain right now, this table says nothing about tomorrow.
```

on op mainnet the transfer costs 0.0054 cents, so a cent buys almost two hundred of them, and the
bytes it leaves on ethereum are a twentieth of that. the spread between the rollups is not the
bytes, it is the floor each chain puts under its gas price: 0.001 gwei on the op stack, 0.006 on
base, 0.02 on arbitrum. linea has no floor and prices the bytes through the priority fee instead,
which makes it the dearest rollup for a transfer and still five times cheaper than ethereum. scroll's
oracle charges the most for the bytes themselves, and mode and zora charge ten times what op mainnet
does for the same bytes: same oracle, different scalars.

## install

```
pipx install git+https://github.com/AlinaSchan/l2fees
```

or clone it and run `python -m l2fees` from the folder. python 3.10 or newer, no dependencies.

## use

```
l2fees                                        # every chain, dollars from coingecko
l2fees --chains base,arbitrum,scroll          # just these (a name, "optimism", or a chain id)
l2fees --no-usd                               # ether only, no price lookup
l2fees --eth-usd 2500                         # your own price
l2fees --json                                 # every number in wei, every oracle's answer, the median tips
l2fees --rpc base=https://your.base.node      # your endpoint first for one chain
l2fees --summary-append data/daily.csv --quiet   # one row per chain, the dataset
```

## how it works

- **the two transactions** are real ones from mainnet, kept as the signed bytes in
  [l2fees/samples.py](l2fees/samples.py): [`0x2dab…d254`](https://etherscan.io/tx/0x2dab183b48f8ab9ba1916a9b2e08895238c97470e5f3b153f6874199d125d254)
  (a transfer, block 25,982,582, 21,000 gas) and [`0xc221…82cc`](https://etherscan.io/tx/0xc221257f93e4c688438f1c68a0db806031e248c09672a679e18b7f455ec382cc)
  (a swap through the uniswap universal router, block 25,982,574, 140,642 gas used, 772 bytes of
  calldata). a small rlp module takes them apart; the unsigned part (the type byte and the first
  nine fields) is what the oracles are asked about, since they add the signature's bytes themselves.
  the live test fetches both by hash and checks every field.
- **exec** is the gas the transaction used on mainnet times `eth_gasPrice` on the chain, the price
  the node suggests and a wallet pays. `eth_feeHistory` splits it into the base fee and the tip, and
  the json carries the median tip the last four blocks actually paid next to it: on the op stack that
  median is a few wei and the suggestion a thousand times more, and the suggestion is what goes into
  the transaction.
- **l1 data**, by chain kind, in [l2fees/chains.py](l2fees/chains.py):
  - op stack (op mainnet, base, unichain, ink, soneium, world chain, mode, zora, blast): the
    `GasPriceOracle` predeploy at `0x42…0F`, `getL1Fee(bytes)` with the unsigned transaction. fjord
    pricing: a fastlz estimate of the compressed size times the chain's scalars over the l1 base fee
    and blob base fee the oracle last saw.
  - arbitrum one: the `NodeInterface` at `0xc8`, `gasEstimateL1Component(to, false, calldata)`,
    which answers in units of layer-2 gas; that times the layer-2 base fee is the fee.
  - scroll: the `L1GasPriceOracle` predeploy at `0x53…02`, `getL1Fee(bytes)`, the same shape as the op
    stack's.
  - linea: `linea_estimateGas` for a call with the transaction's calldata to an address without
    code. linea prices the bytes through the priority fee it returns, so the data part is the
    estimated gas times that fee, and the execution part is the gas used times the base fee (seven
    wei). an endpoint without `linea_estimateGas` leaves the bytes unpriced and says so.
  - polygon zkevm: the gas price carries the layer-1 cost; there is nothing to add.
  - ethereum: execution only, it is the layer 1.
- the fourteen chains are read four at a time; a chain whose endpoints all fail, or whose endpoint
  answers with the wrong chain id, gets one line with the reason and no numbers. the ether price is
  coingecko, then coinbase, then kraken, whichever answers first.

## reading the table

- the rollups are sorted by what the transfer costs, cheapest first. the order changes with the
  hour: ethereum's base fee moves the l1 data column, each chain's own base fee moves the rest.
- an l1 data fee is what the chain's oracle says at this moment; after a fee spike on ethereum an
  oracle can lag by a few minutes. the table reads it, it does not check it (that is
  [an open issue](https://github.com/AlinaSchan/l2fees/issues)).
- the swap's execution gas is what it used on mainnet. on a rollup the same swap would use about the
  same, but not exactly: different pools, different state. the calldata is priced as it is.
- cents, not dollars: nearly every number on a rollup is below a cent, and the digits after the
  decimal point are the whole story.
- numbers, not calls: a cheap chain is a cheap chain right now. security, withdrawal times, who
  runs the sequencer and whether the chain is still there next year are outside these columns.

## the dataset

`data/daily.csv` gets one row per chain every night at 01:03 utc: the gas price, and the execution
and layer-1 parts of both transactions in wei, with the ether price used. columns are in
[data/README.md](data/README.md); a rerun for the same day replaces the day.

## exit codes and scripting

`0` after a table, `2` when a chain name is wrong, `--rpc` is malformed or no chain answered.
`--json` carries every oracle's answer, so
`l2fees --json --no-usd | jq '.chains[] | {chain, transfer: .quotes.transfer.total_wei}'` lists the
transfers in wei.

## see also

- [blobwatch](https://github.com/AlinaSchan/blobwatch): what the rollups pay ethereum for the blobs those bytes end up in
- [gasweek](https://github.com/AlinaSchan/gasweek): when ethereum itself is cheapest, by hour of day
- the notes: [alinaschanz.life](https://alinaschanz.life), the short version on [x](https://x.com/alinaschanz)

## verify a release

every release carries the sdist and the wheel, a `SHA256SUMS` file, an opentimestamps proof of that
file, and a build provenance attestation made in github's own signing flow. with the files downloaded
into one folder:

    sha256sum -c SHA256SUMS
    gh attestation verify ./*.whl --owner AlinaSchan
    ots verify SHA256SUMS.ots

the commit itself is [signed](https://alinaschanz.life/verify/#commits).

## license

[mit](LICENSE). numbers, not calls. not financial advice.
