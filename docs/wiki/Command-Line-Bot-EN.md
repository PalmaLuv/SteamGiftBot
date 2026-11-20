# Command-line bot

The original SteamGiftBot: it works with SteamGifts only, with no panel and no
server. It suits you if you need a single site or want the bot to run on a
schedule on an ordinary computer. The full description in English is in the
[README](../../README.md#first-run).

## First run

```bash
env/bin/python main.py
```

The bot asks for the `PHPSESSID` cookie and a few settings, saves them to
`config.ini` and starts working. How to get the cookie is described in
[Connecting sites](Connecting-Sites-EN.md); the bot needs just the
`PHPSESSID` value.

It is worth seeing first what the bot is going to do:

```bash
env/bin/python main.py --dry-run
```

The bot goes through the site as usual, applies all the filters and shows
what it would have entered, without spending anything. It is also the quickest
way to check whether the cookie works.

## Options

| Option | What it does |
| --- | --- |
| `--setup` | open the settings menu instead of running |
| `--config PATH` | path to `config.ini` |
| `--no-input` | ask nothing; if a setting is missing, exit with an error |
| `--once` | one run and exit, without waiting for points; for cron and the Task Scheduler |
| `--dry-run` | show what it would enter, without spending anything |
| `--cookie VALUE` | `PHPSESSID` |
| `--type TYPE` | `All`, `WishList`, `Recommended`, `Copies`, `DLC`, `New` |
| `--min-points N` | keep the balance above N |
| `--pinned` / `--no-pinned` | whether to enter pinned giveaways |
| `--points-wait SECONDS` | how long to wait for points (900 by default) |
| `--max-cost N` | skip giveaways that cost more than N |
| `--max-entries N` | skip giveaways with more than N participants |
| `--level N` | your contributor level |
| `--skip-region-locked` | skip region-locked giveaways |
| `--cards-only` | only games with Steam trading cards |
| `--blacklist WORDS`, `--whitelist WORDS` | words separated by commas |
| `--telegram-token`, `--telegram-chat` | Telegram |
| `--telegram-chat-id` | show the IDs of chats that wrote to the bot, and exit |
| `--notify-test` | send a test message and exit |
| `--no-telegram`, `--no-check-wins` | turn off Telegram or the win check |
| `--log` / `--no-log` | whether to write a log to `log/` |

Any option can also be set with an environment variable prefixed with
`STEAMGIFTBOT_`, for example `STEAMGIFTBOT_COOKIE` or `STEAMGIFTBOT_MIN_POINTS`.
The priority is: command-line options, then environment variables, then
`config.ini`.

## On a schedule

**cron, every 12 hours:**

```
0 */12 * * * cd /path/to/SteamGiftBot && env/bin/python main.py --once --no-input
```

**Windows Task Scheduler:**

```
schtasks /create /tn SteamGiftBot /sc hourly /mo 12 /tr "C:\SteamGiftBot\SteamGiftBot.exe --once --no-input"
```

**Docker:**

```bash
docker run --rm -e STEAMGIFTBOT_COOKIE=your_PHPSESSID -e STEAMGIFTBOT_GIFT_TYPE=All \
  -e STEAMGIFTBOT_MIN_POINTS=0 -e STEAMGIFTBOT_PINNED=no ghcr.io/palmaluv/steamgiftbot:latest --once
```

## Moving to the farm

The farm reads the same `config.ini`, so SteamGifts is connected in it right
away, with the same settings. Do not run the command-line bot and the farm at
the same time on the same account: they would spend the same points.
