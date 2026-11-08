# Data audit

| File | Rows | Columns | SHA-256 |
|---|---:|---:|---|
| accounts.csv | 4,500 | 4 | `e8e135af1601201f7fdc1e6563387efd0c7aefdc039d05f0d921970d8235b877` |
| cards.csv | 892 | 4 | `4d3c1121da2ea725d249d44af26ff1f5367e577451a29f0f309b010033029158` |
| clients.csv | 5,369 | 4 | `99b30e4f3257cb9eb2f15731a0af64077ea785cc53c998714cb32cb8a4129ad8` |
| dispositions.csv | 5,369 | 4 | `f6c7ebc1ef6479ea37f1f4b9dbf27a9b3e9c9a8fee441761950336b91ea9c473` |
| districts.csv | 77 | 16 | `fa0f0355164e5dad3241f539983660ca0e3c755ffae14e003ef0db5e09117bc6` |
| loans.csv | 682 | 9 | `a4eb2e5e3aa76198b26431c9dcbcff858befcf7c38ccd326c18307e5c13a9ebf` |
| monthly_summary.csv | 185,326 | 19 | `2fedfed4509c96588b05738247fb99595afdce929e962a08af1c083694666e83` |
| standing_orders.csv | 6,471 | 6 | `0a4c4759c8209856335c7ff3e66273a83035880837dac86df11ced131ca2f6a5` |
| transactions.csv | 1,056,320 | 11 | `e00502005bdda8b4d8bb7ab04b2b31911a9d3e1622f98e652e605a52bf78fd8b` |

Month range: 2020-01–2025-12; unique accounts: 4,500.
Duplicate account/month rows: 0.
Missing required monthly values: 0.
Recent months excluded from recovered-overdraft analysis for missing data: 0.
Accounts with fewer than six rows: 0.
Accounts with fewer than 12 recent rows: 76.
Stale accounts at dataset cutoff: 76.
Unknown loan-account joins: 0.

README/PDF count (185,326 monthly rows) is correct; the master guide’s 26,846 is not.
The classification pipeline reads monthly_summary and loans. Other files are inventoried only.
Required numeric fields reject nulls, infinities, malformed months, and duplicate keys.
Optional missing liquidity signals produce null features and explicit quality flags.
CSV exports retain full precision; ratios supplied to APIs retain full precision as well.
No raw data or existing outputs are overwritten. No classifier API was called for discovery.
