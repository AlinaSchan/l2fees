# data

written by the [daily workflow](../.github/workflows/daily.yml) at 01:03 utc.

`daily.csv`: one row per chain per utc date. columns:

- `date_utc`, `time_utc`: when the endpoints were asked (the chains have different blocks, so no block column)
- `chain`, `chain_id`
- `base_fee_wei`, `tip_wei`: the next block's base fee and the median priority fee of the last four blocks, per gas
- `transfer_exec_wei`, `transfer_l1_wei`, `transfer_total_wei`: the plain transfer (21,000 gas): execution gas times
  the gas price, the layer-1 data fee from the chain's oracle (empty where the chain has none), and the sum
- `swap_exec_wei`, `swap_l1_wei`, `swap_total_wei`: the same for the uniswap swap (140,642 gas, 772 bytes of calldata)
- `eth_usd`: the ether price used for the dollar columns of that run (coingecko, coinbase or kraken), empty if none answered

a chain that did not answer that night has no row. a rerun for the same day replaces that day's rows.
columns are only ever appended.
