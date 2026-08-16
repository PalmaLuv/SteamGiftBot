<div align="center">
  <img src="https://user-images.githubusercontent.com/84909252/221827123-c7fd5d1e-7f6b-4d78-a225-4491305b6a87.png" height="250"/>
</div>

<div align="center">

  [![](https://img.shields.io/github/v/release/PalmaLuv/SteamGiftBot?include_prereleases&label=Version&color=blueviolet)](https://github.com/PalmaLuv/SteamGiftBot/releases/latest)
  [![](https://img.shields.io/github/license/PalmaLuv/SteamGiftBot?color=%231E90FF&label=License)](LICENSE)
  ![Python](https://img.shields.io/badge/Python_Version-3.9--3.13-yellow?logo=python)
  [![](https://img.shields.io/github/downloads/PalmaLuv/SteamGiftBot/total.svg?label=Downloads&logo=github&cacheSeconds=600&color=blueviolet)](https://github.com/PalmaLuv/SteamGiftBot/releases)
  [![SteamGiftBot Docker Build](https://github.com/PalmaLuv/SteamGiftBot/actions/workflows/docker-publish.yml/badge.svg)](https://ghcr.io/palmaluv/steamgiftbot:latest)

</div>

Enters giveaways on [SteamGifts](https://www.steamgifts.com/) for you, and tells
you on Telegram when you win one.

![image](https://github.com/PalmaLuv/SteamGiftBot/assets/84909252/34b5e86f-54d1-462a-aadf-fe9c5ccb823c)

- Walks the giveaway pages and enters what is worth your points
- Filters by price, by contributor level, by how crowded a giveaway already is,
  by name, by whether the game has Steam trading cards
- Waits for points instead of burning through them
- Paces itself between entries and backs off when the site asks it to
- Runs unattended: as a service, from cron, or in Docker
- Messages you on Telegram the moment you win, and when your session expires
- Keeps a log of every run

---

**Contents** · [Install](#install) · [First run](#first-run) ·
[Settings](#settings) · [Choosing giveaways](#choosing-giveaways) ·
[Telegram](#telegram) · [Running unattended](#running-unattended) ·
[Updating](#updating) · [When something goes wrong](#when-something-goes-wrong) ·
[Contributing](#contributing)

---

## Install

Pick one of three. They are the same program.

### The Windows executable

The simplest option, nothing to install.

1. Download `SteamGiftBot.exe` from
   [releases](https://github.com/PalmaLuv/SteamGiftBot/releases/latest).
2. Put it in a folder of its own. The bot writes `config.ini`, its state file and
   its logs beside itself, so give it somewhere to live rather than Downloads.
3. Run it.

### From source

Needs Python 3.9 or newer.

```bash
git clone https://github.com/PalmaLuv/SteamGiftBot.git
cd SteamGiftBot
python -m venv env
source env/Scripts/activate      # Linux and macOS: source env/bin/activate
pip install -r requirements.txt
python main.py
```

`python -m steamgiftbot` does exactly the same thing as `python main.py`.

### Docker

```bash
docker pull ghcr.io/palmaluv/steamgiftbot:latest
```

The container never asks questions, so its settings arrive as environment
variables or in a mounted `config.ini`. See
[Running unattended](#running-unattended).

## First run

The bot signs in as you, using the session cookie your browser already has.

1. Sign in to [SteamGifts](https://www.steamgifts.com/) with Steam.
2. Open the browser developer tools (`F12`) → *Application* or *Storage* →
   *Cookies* → `https://www.steamgifts.com`, and copy the value of `PHPSESSID`.

<p align="center">
  <img src="https://user-images.githubusercontent.com/84909252/211176701-6f0cedb7-7706-4ba0-b36e-3e57719b6f0a.png"/>
</p>
<p align="center">Take it from the site itself, not from anywhere else</p>

3. Start the bot. It asks for the cookie and a few other things, then remembers
   them in `config.ini`.

```bash
python main.py
```

4. Before letting it spend anything, see what it would do:

```bash
python main.py --dry-run
```

That walks the site exactly as a real run does, applies every filter and prints
what it would have entered — without entering anything. It is also the quickest
way to find out whether your cookie still works.

The cookie lasts weeks, not forever. When it expires the bot stops and says so,
and if Telegram is set up it will tell you there too.

## Settings

Everything lives in `config.ini`, next to `main.py` (or next to the `.exe`).
**Once every required setting is present the bot starts working straight away
and asks nothing.** You can write the file by hand instead of answering
questions:

```ini
[DEFAULT]
cookie = yourcookievalue
gift_type = All
pinned = no
min_points = 0
```

Those four are required. Everything below is optional.

| Setting | Values | Meaning |
| --- | --- | --- |
| `cookie` | your `PHPSESSID` | session cookie from steamgifts.com |
| `gift_type` | `All`, `WishList`, `Recommended`, `Copies`, `DLC`, `New` | which giveaways to walk through |
| `pinned` | `yes` / `no` | also enter pinned giveaways |
| `min_points` | number | stop entering once the balance falls below this; `0` spends everything |
| `log_info` | `yes` / `no` | write a log file for each run, into `log/` |
| `points_wait` | seconds | how long to sleep when the balance runs out (default 900) |

Run `python main.py --setup` at any time to change these from a menu.

> **Two things about `.ini` files.** Comments only work on a line of their own —
> `max_entries = 500  # recommended` makes the value `500  # recommended`, not a
> number. And an empty value is not the same as zero: `max_cost =` means *no
> limit*, `max_cost = 0` means *nothing qualifies*.

### The same settings elsewhere

Command line flags beat environment variables, which beat `config.ini`. Anything
you leave out keeps whatever the file says.

```bash
python main.py --help                        # every flag
python main.py                               # run with the saved settings
python main.py --setup                       # change the saved settings
python main.py --once                        # a single pass, then exit
python main.py --dry-run                     # show what it would enter, spend nothing
python main.py --no-input                    # never ask; fail if something is missing
python main.py --type WishList --min-points 50 --no-pinned
python main.py --level 2 --max-entries 500
python main.py --cards-only --max-cost 60
python main.py --blacklist "simulator, hentai"
```

Every setting has an environment variable named `STEAMGIFTBOT_` + its name in
capitals — `STEAMGIFTBOT_COOKIE`, `STEAMGIFTBOT_MAX_ENTRIES`,
`STEAMGIFTBOT_TELEGRAM_TOKEN`, and so on. This is how the Docker image is
configured.

Exit codes: `0` finished normally, `1` the run failed (bad cookie, dead
session), `2` the setup is incomplete. Worth knowing if a scheduler runs it.

`config.ini` holds a live session cookie. It is already in `.gitignore` — keep it
that way, and do not paste it anywhere.

## Choosing giveaways

These decide what your points go on. All optional; anything unset is not
filtered on.

| Setting | Values | Meaning |
| --- | --- | --- |
| `contributor_level` | your level | skip giveaways that ask for a higher one |
| `max_entries` | number | skip giveaways this many people already entered |
| `max_cost` | number | skip anything more expensive than this |
| `cards_only` | `yes` / `no` | only enter games that have Steam trading cards |
| `skip_region_locked` | `yes` / `no` | skip giveaways restricted to particular regions |
| `blacklist` | words, comma separated | skip a giveaway whose name contains any of them |
| `whitelist` | words, comma separated | enter *only* giveaways whose name contains one of them |

**Set your contributor level.** It is shown on your SteamGifts profile. Three
giveaways out of five ask for one, and entering those from a lower level is
refused by the site: your points stay, but the request is wasted and it brings
the rate limit closer. Measured across 126 live giveaways, a level 0 account was
attempting 71 it could never enter.

**`max_entries` decides your odds.** In that same sample the median giveaway
already had 554 people in it. What a limit does to that:

| `max_entries` | giveaways left | median entries among them |
| --- | --- | --- |
| 250 | 22% | 145 |
| **500** ← recommended | **46%** | **271** |
| 1000 | 74% | 447 |
| 2000 | 94% | 527 |
| unset | 100% | 554 |

500 is the balance: about half the giveaways stay available and the crowd around
each one halves. Below 250 so little qualifies that the bot sits on unspent
points, so `--setup` offers 500 and says so.

Name matching ignores case and looks anywhere in the name, so `portal` catches
`Portal 2`. The blacklist is checked before the whitelist. `cards_only` skips
bundles, because a `store.steampowered.com/sub/...` link carries no app id and
the question cannot be answered for it. `skip_region_locked` is off by default:
the listing says a giveaway is restricted, not that *you* are excluded, so
turning it on when you are inside the region throws away giveaways you could
have entered.

A worked example:

```ini
[DEFAULT]
cookie = yourcookievalue
gift_type = All
pinned = no
min_points = 0

contributor_level = 2
max_entries = 500
max_cost = 60
cards_only = no
blacklist = simulator, hentai, early access
```

## Telegram

The point of running this on a server is that nobody is watching it. So the bot
watches the *won giveaways* page and messages you the moment something new shows
up:

> You won Hollow Knight
> https://www.steamgifts.com/giveaway/win001/

It also speaks up when your **session expires**, which is the one failure you
have to act on:

> Your SteamGifts session has expired, so the bot stopped.
> Sign in at steamgifts.com, copy the new PHPSESSID cookie and run
> `python main.py --setup`.

Each win is announced once. The codes already sent live in
`steamgiftbot-state.json` beside `config.ini`, so a run every twelve hours does
not repeat itself.

### Setting it up

**1.** Open [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`,
answer the two questions. It hands you a token like `123456789:AAH...`. Put it in
`config.ini`:

```ini
telegram_token = 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
```

**2.** Open your new bot in Telegram and **send it any message** — `/start` will
do. This step is not optional: Telegram does not let a bot write to you first,
and will not reveal your chat id until you have spoken to it.

**3.** Ask who wrote to the bot:

```bash
python main.py --telegram-chat-id
```

```
Chats that have written to your bot:
  987654321  private    Palma

Put this in your config.ini:
  telegram_chat = 987654321
```

For a group, add the bot to it and write something there instead; the group
appears in the same list with a negative id.

**4.** The finished section:

```ini
telegram_enabled = yes
telegram_token = 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
telegram_chat = 987654321
check_wins = yes
```

**5.** Check it before trusting it:

```bash
python main.py --notify-test
```

One message, then it exits. Both this and `--telegram-chat-id` work before the
rest of the bot is set up, and need no cookie.

| Setting | Values | Meaning |
| --- | --- | --- |
| `telegram_enabled` | `yes` / `no` | switch messages off without deleting the token |
| `telegram_token` | token from BotFather | which bot sends the message |
| `telegram_chat` | chat id | where the message goes |
| `check_wins` | `yes` / `no` | watch the won giveaways page (on by default) |
| `discord_webhook` | webhook URL | the same messages, to Discord instead or as well |

A notification that cannot be delivered is reported and dropped: a dead webhook
never turns a good run into a failed one.

## Running unattended

By default the bot keeps running and sleeps whenever it is short on points. With
`--once` it makes a single pass and exits instead of sleeping, which is what you
want when a scheduler already decides how often it runs.

**cron**, every twelve hours:

```bash
0 */12 * * * cd /path/to/SteamGiftBot && /path/to/env/bin/python main.py --once --no-input
```

**Windows Task Scheduler:**

```bash
schtasks /create /tn SteamGiftBot /sc hourly /mo 12 /tr "C:\SteamGiftBot\SteamGiftBot.exe --once --no-input"
```

**Docker**, settings as variables:

```bash
docker run --rm -e STEAMGIFTBOT_COOKIE=yourcookievalue -e STEAMGIFTBOT_GIFT_TYPE=All -e STEAMGIFTBOT_MIN_POINTS=0 -e STEAMGIFTBOT_PINNED=no ghcr.io/palmaluv/steamgiftbot:latest --once
```

**Docker with a config file**, which is what you want if you use Telegram. The
bot needs somewhere to keep the wins it has already announced; without it a
restarted container announces every old win again:

```bash
docker run -d --name steamgiftbot --restart unless-stopped -v /srv/steamgiftbot:/app/data ghcr.io/palmaluv/steamgiftbot:latest --config /app/data/config.ini
```

Put your `config.ini` in `/srv/steamgiftbot` first. `--no-input` is already built
into the image, so an incomplete setup fails with exit code 2 instead of waiting
for an answer nobody will type.

## Updating

**The Windows executable.** Download the new `SteamGiftBot.exe` from
[releases](https://github.com/PalmaLuv/SteamGiftBot/releases/latest) and replace
the old one. Keep `config.ini` and `steamgiftbot-state.json` where they are —
your settings and the wins already announced carry over. New settings simply
start out unset, and the bot behaves as it did before you fill them in.

**From source:**

```bash
git pull
pip install -r requirements.txt --upgrade
```

The second line matters: an update may add or raise a dependency, and skipping it
gives confusing errors rather than a clear one. Your `config.ini` is not tracked
by git, so `git pull` leaves it alone.

**Docker:**

```bash
docker pull ghcr.io/palmaluv/steamgiftbot:latest
docker stop steamgiftbot && docker rm steamgiftbot
# then run it again with the same command as before
```

Because the config and the state file live in the mounted directory, nothing is
lost when the container is replaced.

**After any update**, a quick check that costs nothing:

```bash
python main.py --dry-run
```

If a new release adds a filter you want, add it to `config.ini` or run
`python main.py --setup`. Settings never disappear between versions; if one is
ever retired it is ignored rather than treated as an error.

## When something goes wrong

**"Missing settings: …" and exit code 2.** An unattended run found an incomplete
setup. The message names each absent setting; put them in `config.ini`, in
`STEAMGIFTBOT_*` variables, or on the command line.

**"Cookie is not valid, or the SteamGifts layout has changed."** The `PHPSESSID`
in `config.ini` no longer matches a signed in session — this is normal, cookies
expire. Sign in again, copy the fresh one, run `python main.py --setup`, then
confirm with `--dry-run`.

**"SteamGifts answered with a Cloudflare check instead of the site."** The site
decided the request did not come from a browser. The bot cannot answer that check
and this project will not try to work around it. Open steamgifts.com in a
browser, make sure it lets you in, and try again.

**"'telegram_token' does not look like a bot token."** Usually a comment left on
the same line, quotes around the value, or half the token. Copy it again from
@BotFather, unquoted, on a line of its own.

**Telegram says nothing.** Run `python main.py --notify-test`. It names the part
that is missing rather than making you guess — most often `telegram_chat`, which
stays empty until you have written to the bot and run
`python main.py --telegram-chat-id`.

**The bot enters nothing at all.** Run `--dry-run` and read the summary: it counts
every skipped giveaway and the reason. A `whitelist` that matches nothing, a
`max_cost` below the usual price, or a `max_entries` under 250 will quietly filter
out everything.

**The bot enters far less than it used to.** Check `contributor_level`. If it is
higher than your real level, most giveaways are being skipped for you.

## Contributing

```
main.py             entry point, kept where everybody expects it
steamgiftbot/
  cli.py            flags, settings resolution, startup
  settings.py       config.ini + environment + command line
  bot.py            the giveaway walker itself
  giveaway.py       one listing row, parsed
  filters.py        whether a giveaway is worth points
  wins.py           reading the won giveaways page
  state.py          which wins were already announced
  stats.py          what happened during a run
  notify.py         Discord and Telegram messages
  steam_api.py      Steam store lookups
  ui.py             the interactive questions
  console.py        banner, colours, progress lines
  logging_setup.py  the optional log file
tests/              pytest suite, HTML fixtures under tests/fixtures
```

```bash
pip install -r requirements-dev.txt
pytest                          # the whole suite, no network needed
ruff check .                    # the same lint the CI runs
bash scripts/check-docker.sh    # build the image and exercise it
pyinstaller SteamGiftBot.spec   # the Windows executable, into dist/
```

The tests replay trimmed SteamGifts pages from `tests/fixtures`, several of them
copied verbatim from the live site, so they never touch the real site and never
need a cookie.

Pushing a `v*.*.*` tag builds the executable on a Windows runner, checks that it
actually starts, and attaches it to the GitHub Release.

Suggestions are welcome
[here](https://github.com/PalmaLuv/SteamGiftBot/discussions/6).

## License

[MPL-2.0](LICENSE).

<div align="center" markdown="1">

<a href="http://twitter.com/intent/tweet?text=https://github.com/PalmaLuv/SteamGiftBot%0ASteamGiftBot">Share on Twitter</a><br>
<a href="http://www.linkedin.com/shareArticle?mini=true&url=https://github.com/PalmaLuv/SteamGiftBot&title=SteamGiftBot&summary=&source=">Share on LinkedIn</a><br>
<a href="https://t.me/share/url?url=https://github.com/PalmaLuv/SteamGiftBot">Share on Telegram</a><br>

</div>
