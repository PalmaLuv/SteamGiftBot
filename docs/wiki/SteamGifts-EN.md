# SteamGifts

[steamgifts.com](https://www.steamgifts.com/) runs Steam key giveaways for
points (P). The site awards points roughly every 15 minutes while you visit
it. The farm visits it by itself, so points keep piling up without you.

Inside the farm runs the same code as in the
[command-line bot](Command-Line-Bot-EN.md). That is why SteamGifts settings
are kept in `config.ini`, and both the farm and the command-line bot read them
from there.

## Connecting

**Sites (Площадки) → SteamGifts → Connect (Подключить)**. Sign in to the site
through Steam, copy the `steamgifts.com` request as cURL and paste it into the
wizard. The farm only needs the `PHPSESSID` cookie and discards the rest. You
can also paste the `PHPSESSID` value itself from **F12 → Application →
Cookies**.

## How a run goes

1. The farm reads the balance and checks for new wins.
2. If "Wishlist games first" («Сначала игры из списка желаемого») is on (in
   the farm settings), the site's **Wishlist** section is visited first.
3. Then the farm pages through the chosen section ("Giveaway type" («Тип
   раздач»)) and decides for each giveaway whether to enter it. It pauses
   3–7 seconds between entries.
4. If the balance drops below "Keep balance above" («Не опускать баланс
   ниже»), the farm waits about 15 minutes for points to accumulate.
5. If it has looked through "Pages per run" («Страниц за проход») and found
   no giveaway it can afford with the current balance, the farm also waits
   about 15 minutes. Without this limit it would page through the whole
   catalogue over and over. If the next runs enter nothing either and the
   balance has not grown by at least 10 P meanwhile, the pause grows to 30,
   then 60 minutes. Any entry, or the balance growing by 10 P, brings back
   15 minutes.
6. These pauses are not exact on purpose: each is up to 20 % longer or
   shorter (the 60-minute one only shorter), so the farm does not visit the
   site with a robot's even rhythm.

## Why a giveaway was skipped

The farm checks the conditions in order and stops at the first one that does
not fit:

1. already entered;
2. pinned, while "Enter pinned giveaways" («Входить в закреплённые») is off;
3. the giveaway level is above your contributor level;
4. region-locked, while "Skip region-locked" («Пропускать региональные») is
   on;
5. more entries than "Max participants" («Макс. участников»);
6. costs more than "Max giveaway cost" («Макс. цена раздачи»);
7. the title matches the blacklist or does not match the whitelist;
8. not enough points;
9. "Only games with cards" («Только игры с карточками») is on and the game
   has no cards. For this check the farm queries the Steam store, so the run
   is slower;
10. working hours are over or the daily limit is used up; then the run stops
    until the hours open or the limit resets;
11. the farm-wide filters: DLC and packs, 18+, game already in the library.

## Settings

**Account (Аккаунт)**

| Setting | Default | What it does |
| --- | --- | --- |
| Cookie PHPSESSID | — | the steamgifts.com request copied as cURL, or the PHPSESSID value itself (F12 → Application → Cookies) |
| Your contributor level (Ваш contributor level) | empty | giveaways with a higher level are skipped without extra requests |
| Browser User-Agent (User-Agent браузера) | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36` | taken from cURL automatically; otherwise from the same browser the cookie came from |

**What to enter (Что брать)**

| Setting | Default | What it does |
| --- | --- | --- |
| Giveaway type | `All` | Options: `All`, `WishList`, `Recommended`, `Copies`, `DLC`, `New`. |
| Keep balance above | `30` |  |
| Max giveaway cost | empty | empty means no limit |
| Max participants | empty | skip giveaways that already have more than N entries |
| Enter pinned giveaways | on |  |
| Only games with cards | off |  |
| Skip region-locked | off |  |
| Blacklist (Чёрный список) | empty | words separated by commas |
| Whitelist (Белый список) | empty | if set, only these |
| Track wins (Следить за выигрышами) | on |  |

**Filters (Фильтры)**

| Setting | Default | What it does |
| --- | --- | --- |
| Skip games in my Steam library (Пропускать игры из моей библиотеки Steam) | off | needs a Steam API key and a profile in the farm settings |
| Skip DLC, soundtracks, artbooks, packs (Пропускать DLC, саундтреки, артбуки, паки) | off |  |
| Skip 18+ (Пропускать 18+) | off |  |

**Browsing (Обход)**

| Setting | Default | What it does |
| --- | --- | --- |
| Pages per run | `10` | a page holds 50 giveaways; without a limit the bot would page through the whole catalogue |

**Wins (Выигрыши)**

| Setting | Default | What it does |
| --- | --- | --- |
| Mark as received on the site (Отмечать на сайте «получено») | off | when a win is marked "Key received" or "Activated" in the panel, the farm clicks the same on SteamGifts. Experimental: the site's request is undocumented |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

**Tips.**

- **Set your contributor level.** Most SteamGifts giveaways require a level,
  and without this setting the farm wastes requests on giveaways it will not
  be let into anyway. The level is shown in your profile on the site; a new
  account has level 0.
- **"Max participants" around 500** noticeably improves your chances:
  giveaways with thousands of participants are almost hopeless.
- **"Keep balance above" at 30–50** leaves a reserve of points for entering by
  hand.

## Wins

The farm checks the [won giveaways](https://www.steamgifts.com/giveaways/won)
page after every run. A new win appears in [Wins](Wins-and-Keys-EN.md), and a
message arrives on Telegram.

**SteamGifts requires you to mark wins as received** with the "received"
button on the won page. Unmarked and unactivated keys can earn you a warning
or a ban. Therefore:

- the daily Telegram summary reminds you about wins that are not marked yet;
- the **"Mark as received on the site"** setting clicks that button itself
  when you mark a win in the panel. It is experimental and off by default:
  SteamGifts does not document this request anywhere. The result shows up in
  the SteamGifts log.

## Log messages

The SteamGifts code was inherited from the command-line bot, so some of its
messages are in English:

| Message | What it means |
| --- | --- |
| `Getting games from page N` | the farm is paging through page N |
| `One more game X` | the farm entered giveaway X |
| `Skipping X: not enough points` | not enough points for this giveaway |
| `Not enough points: 13, need at least 30. Waiting 15 min.` (`Мало поинтов: 13, нужно минимум 30. Жду 15 мин.`) | the balance is below the minimum; the farm waits |
| `Looked through 10 pages, not going further this run.` (`Просмотрено 10 стр., дальше в этом проходе не иду.`) | the "Pages per run" limit was reached |
| `No suitable giveaways, balance 31P.` (`Подходящих раздач нет, баланс 31P.`) | nothing affordable with the current balance passed the filters |
| `Re-authorisation needed` (`Нужна новая авторизация`) | the cookie no longer works; you need to [reconnect](Connecting-Sites-EN.md) |
| `SteamGifts answered with a Cloudflare check` | the site showed a Cloudflare check. Open it in the browser; the farm retries in 15 minutes |
