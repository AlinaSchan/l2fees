# changelog

all notable changes to l2fees. the format follows [keep a changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [semver](https://semver.org/) as far as a command line tool has an api.

## [0.1.0] - 2026-09-15

first cut: what a transaction costs right now on ethereum and thirteen rollups.

- two real mainnet transactions taken apart with a small rlp module: a plain transfer and a uniswap swap; the hashes
  are in the source and the live test recomputes them
- the op stack chains through the GasPriceOracle predeploy, arbitrum through the NodeInterface, scroll through its
  L1GasPriceOracle, linea through `linea_estimateGas`, polygon zkevm through its gas price alone
- the gas price a wallet pays split into the base fee and what sits on top, the median tip of the last blocks next to it
- dollars from coingecko, coinbase or kraken; the table, `--json`, `--chains`, `--rpc chain=url`, `--no-usd`, and a daily
  workflow that writes `data/daily.csv`
