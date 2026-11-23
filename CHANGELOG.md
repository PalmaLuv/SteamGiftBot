# Changelog

What changed in each release, newest first. The text under a version is what
its [GitHub release](https://github.com/PalmaLuv/SteamGiftBot/releases) says.

## [3.0.0] - 2026-11-23

SteamGiftBot grows from one bot for one site into a **bot farm**: several
giveaway sites and free game sources run side by side, each in its own thread,
behind a web panel you can open from your phone. The command line bot stays as
it was and keeps its `config.ini`; the farm reads the same file for SteamGifts.

### Downloads

| File | What it is |
| --- | --- |
| **BotFarm.exe** | The farm for Windows. Put it in a folder of its own and run it: it asks once for a password for its panel, then opens the panel in your browser at `http://127.0.0.1:8092/`. Its data (`farm.json`, history, logs) stays next to it. |
| **SteamGiftBot.exe** | The command line bot for SteamGifts alone, as before. |
| `*.sha256` | Checksums. The programs are not code signed, so compare: `certutil -hashfile BotFarm.exe SHA256`. |

On Linux, macOS or a server: `git clone`, `pip install -r requirements.txt`,
`python -m steamgiftbot.farm --set-password`, then
`python -m steamgiftbot.farm --host <your LAN address>`. Docker:
`ghcr.io/palmaluv/steamgiftbot:3.0.0`, the same image runs the bot and the
farm (commands in the README).

### Sites

- **SteamGifts**: giveaways for points. The farm walks the listing by the best
  chance per point (copies shared among the entrants, for what they cost), or
  in the site's order. SteamGifts' own filters (level, entries, price) are added
  to the listing's address, so fewer pages are fetched. Saving mode
  (`save_up_to`) keeps points until a balance is reached, and the gift type
  *Group* is supported. Keys the creator sends show on the won page and are
  taken onto the win; "received" can be marked on the site (opt-in,
  experimental).
- **IndieGala**: giveaways for Galasilver. A "smart" order enters the best
  chance per Galasilver first, using a forecast of how many people each
  giveaway will have by its end; a priority list may dip into the reserve;
  an optional cap on tickets per game. Wins are checked on the site every
  three hours.
- **OpiumPulses**: free and OP giveaways.
- **Free Steam games**: free-to-keep Steam promotions from the ASFinfo list,
  added to the library through ArchiSteamFarm, to every ASF bot or to the
  ones you name.
- **GOG**: the giveaway on GOG's home page.
- **itch.io**: games on a 100% sale.

### Connecting a site

- A step-by-step wizard per site: copy the site's request as cURL in the
  browser (`F12` → Network), paste it, and the farm checks it on the site and
  shows the account and balance it found. No site ever gets your password.
- Ready-made sets of settings to start with: Balanced, Economy, Maximum, Games
  only.
- A warning about the site's rules and the risk of a ban, shown in the wizard
  and on the connection tab.
- A reminder before a site's cookie expires, and a card when the site stops
  accepting it.

### Accounts for several people

- An account is a person (yours, a brother's): each has its own set of sites,
  and each site in it has its own cookies, settings, limits, history and log.
- The Sites page opens one account at a time, with tabs for every account and
  "New account". The account is renamed in place, in its header.
- Each account has its own Steam: the ASF bot that gets the keys its sites win.
- The same site account cannot be connected twice; the farm compares the
  account name on the site.

### Rules for every site

- Working hours, such as `08:00-23:00`, in the farm's time zone.
- Daily limits on entries and on spending.
- Skip DLC, soundtracks and packs; skip adult games; skip games already in
  your Steam library (with a Steam Web API key); your Steam wishlist first.
- **What it would take**: a dry run lists every current giveaway and says why
  the farm would enter it or skip it, with "skip" and "priority" buttons.
- A walk that finds nothing waits longer each time (15 → 30 → 60 min) instead of
  fetching the same pages every quarter hour.
- A card if a site has entered nothing for a day.

### Wins and keys

- One table for every site, with the key and its status (new, key received,
  activated), filters by status and by account.
- Keys found on the sites' won pages are stored on the win.
- **ArchiSteamFarm**: a key is activated in the right bot with one button, or as
  soon as it appears (`auto_redeem`). A key that hits Steam's rate limit is
  retried later on its own.
- A "luck" tile on the overview: wins against what the entries' odds promised.

### Telegram

- A card for every win, with buttons to mark the key received or activate it.
- Commands: `/status`, `/start`, `/pause`, `/run`, `/preview`, `/wins`,
  `/report`, `/donate`, `/help`.
- A daily report at the hour you choose, which also reminds about wins not
  marked yet.

### The panel

- Sections: Overview, Sites, Wins, Log, Settings; a tab bar at the bottom on
  phones; installable on the home screen.
- In English, Ukrainian and Russian; four colour themes; a short tour on the
  first visit.
- A chart of entries per day, a searchable log with filters, history with
  pages and CSV export.
- The command line bot's history (entries and wins from its logs) is imported
  once on the first start.
- Settings in collapsible sections: time zone, Telegram, Steam library,
  ArchiSteamFarm, the panel's password, and a guide for opening the panel on a
  phone, at home or through Tailscale.

### Safety and reliability

- The panel needs a password; sessions can be ended on every other device at
  once; repeated wrong passwords are slowed down.
- Data files are written atomically with a `.bak` copy; a broken file stops
  the start instead of starting empty and saving over the data.
- Logs and saved pages are readable by the owner only; cookies, tokens and
  keys are masked in logs and in Telegram.
- After a network failure the farm retries in 1, 2 and 5 minutes, then every 15.

### The command line bot

- Nothing changes in how it is run or configured.
- The account's name and the last won page are read along with the balance.
- The walk asks hooks that an embedding program can override: one giveaway at
  a time (`tryGiveaway`), extra rules (`extraSkipReason`), skipped giveaways
  (`skipped`) and the win message (`tellWin`).

### Packaging

- `pip install` brings the farm's panel and a `steamgiftbot-farm` command.
- Docker images are tagged with the version (`3.0.0`, `3.0`); `latest` follows
  main.
- The release builds and checks both programs before publishing them.
- A project page in Russian, Ukrainian and English:
  https://palmaluv.github.io/SteamGiftBot/

### Upgrading from 2.2.2

The command line bot needs nothing. For the farm, keep `config.ini` where it
is: the farm takes SteamGifts' settings from it and imports the bot's log
history once. The wiki has a page for every step:
https://github.com/PalmaLuv/SteamGiftBot/wiki

### По-русски

SteamGiftBot вырос из бота для одного сайта в **ферму раздач**: несколько
площадок сразу и веб-панель, которую можно открыть с телефона. Бот для
командной строки работает как раньше.

- **Скачать**: `BotFarm.exe` — ферма для Windows: один раз спросит пароль панели
  и откроет её в браузере, данные хранит рядом с собой. `SteamGiftBot.exe` —
  бот только для SteamGifts. Рядом с каждым файлом — `.sha256` для проверки.
- **Площадки**: SteamGifts (обход по лучшему шансу на поинт, фильтры самого
  сайта, режим накопления, ключи со страницы выигрышей), IndieGala («умный»
  порядок с прогнозом участников, приоритетный список, проверка выигрышей),
  OpiumPulses, бесплатные игры Steam через ArchiSteamFarm, GOG и itch.io.
- **Подключение** — пошаговый мастер: скопировать запрос как cURL, вставить,
  ферма проверит его на сайте. Пароли от сайтов ферме не нужны. Готовые
  наборы настроек, предупреждение о рисках, напоминание до истечения cookie.
- **Учётки**: у каждого человека свой набор площадок со своими cookie,
  лимитами, историей и своим Steam-ботом в ASF для ключей. Учётка
  переименовывается прямо в шапке.
- **Правила**: часы работы, дневные лимиты, пропуск DLC, 18+ и игр из
  библиотеки, сначала список желаемого, пробный проход «Что возьмёт» с
  причинами, отступление, когда подходящих раздач нет.
- **Выигрыши**: одна таблица на все площадки, ключи со страниц выигрышей,
  активация в ArchiSteamFarm кнопкой или сразу, плитка «удача» на обзоре.
- **Telegram**: карточка на каждый выигрыш с кнопками, команды `/status`,
  `/start`, `/pause`, `/run`, `/preview`, `/wins`, `/report`, `/donate`,
  `/help`, сводка за сутки.
- **Панель**: русский, украинский и английский, четыре темы, работа с
  телефона и установка на главный экран, график, журнал с поиском, история с
  выгрузкой в CSV, импорт истории бота для командной строки.
- **Надёжность**: пароль панели, атомарная запись данных с копией `.bak`,
  логи только для владельца, cookie и токены скрыты в логах и Telegram,
  повторы после сбоя сети.
- **Обновление с 2.2.2**: оставьте `config.ini` на месте — ферма возьмёт из
  него настройки SteamGifts и один раз импортирует историю бота. Подробно — в
  [вики](https://github.com/PalmaLuv/SteamGiftBot/wiki).

**Full Changelog**: https://github.com/PalmaLuv/SteamGiftBot/compare/v2.2.2...v3.0.0

## Earlier releases

2.2.2 and older are described on their
[release pages](https://github.com/PalmaLuv/SteamGiftBot/releases).
