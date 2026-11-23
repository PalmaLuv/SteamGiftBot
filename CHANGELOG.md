# Changelog

What changed in each release, newest first. The text under a version is what
its [GitHub release](https://github.com/PalmaLuv/SteamGiftBot/releases) says.

## [3.0.0] - 2026-11-23

SteamGiftBot grows from one bot for one site into a farm: several giveaway
sites and free game sources side by side, run from a web panel you can open on
your phone. The command line bot stays as it was and keeps its settings.

### Downloads

- **BotFarm.exe**: the farm for Windows. Put it in its own folder and run it:
  it asks for a panel password once, then opens the panel in your browser.
  Its data (`farm.json`, history, logs) stays next to it.
- **SteamGiftBot.exe**: the command line bot for SteamGifts alone, as before.
- Each file has a `.sha256` checksum beside it: the programs are not code
  signed, so the checksum is how a download is told apart from a tampered copy.
- On Linux, macOS or a server: `git clone` and `python -m steamgiftbot.farm`,
  or the Docker image `ghcr.io/palmaluv/steamgiftbot:3.0.0`. See the README.

### The farm

- **Sites**: SteamGifts, IndieGala and OpiumPulses giveaways; free-to-keep
  Steam games through ArchiSteamFarm; GOG and itch.io giveaways.
- **Connecting a site** is a step-by-step wizard: copy the request as cURL from
  the browser, paste it, and the farm checks it on the site. No site ever gets
  your password.
- **Accounts for several people**: each account has its own set of sites, with
  their own cookies, limits, history and log, and its own Steam (an ASF bot)
  for the keys it wins.
- **What it would take**: a dry run shows every current giveaway and why the
  farm would enter it or skip it.
- **Rules for every site**: working hours, daily limits on entries and
  spending, ready-made sets of settings, skipping DLC, adult games and games
  you already own, your Steam wishlist first, the best chance per point first.
- **Wins**: one table for every site, with the key and its status. Keys found
  on the won pages are taken onto the win, and ArchiSteamFarm can activate
  them as soon as they appear.
- **Telegram**: a card for every win, a daily report, a reminder before a
  cookie expires, and commands (`/status`, `/pause`, `/run`, `/preview`…) with
  buttons.
- **The panel**: in Russian, Ukrainian and English, light and dark, installable
  on a phone's home screen. A chart of entries per day, a searchable log and
  history with CSV export.
- **Safety**: the panel needs a password, data files are written atomically
  with a backup, logs and saved pages are readable by the owner only, and
  secrets are masked in logs and messages.

### The command line bot

- The account's name and the last won page are read along with the balance, so
  whoever embeds the bot can tell accounts apart and take keys off the page.
- The walk asks hooks that an embedding program can override: one giveaway at
  a time (`tryGiveaway`), extra rules (`extraSkipReason`), skipped giveaways
  (`skipped`) and the win message (`tellWin`). Nothing changes for the command
  line itself.

## Earlier releases

2.2.2 and older are described on their
[release pages](https://github.com/PalmaLuv/SteamGiftBot/releases).
