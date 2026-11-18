# gta6-twitch-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/bowxxx/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/bowxxx/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts how many people will be watching Grand Theft Auto VI live on Twitch in each hour of its release day, as five quantiles an hour. It reads one case — everything recorded up to the end of the day's first hour, plus the hourly curves of comparable past launches — anchors on hour 1's print, and borrows the day's shape from the comparables: each one is grouped by the shape its own release day actually took (flat, rising, or explosive) and weighted by how well it matches the unlock pattern the case notes describe for the target, with the spread coming from how much the weighted pool disagreed. Standard library only, deterministic, no network, no model calls.

In leave-one-out testing over the comparable launches, it scored a mean pinball loss of 0.32 on rolling-midnight-local launches like this one, against 0.40 for the house baseline.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

The grader runs `python3 /bot/main.py` with the case in `/input` and writes the forecast to `/output`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=8bevpj6h&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
