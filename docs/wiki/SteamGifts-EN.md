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

## Risk to the account

SteamGifts' rules do not allow entering giveaways with scripts and bots, and
the account on the site can be banned for it. Your Steam account is not
affected. The connect wizard and the Connection («Подключение») tab say so
plainly.

What the farm does to lower the risk:

- it sends your browser's User-Agent (the one from the copied cURL), not one
  shared by every bot;
- it pauses 3–7 seconds between entries and about 15 minutes between runs,
  varied by up to 20 %;
- it looks through no more than "Pages per run" and asks the site to drop the
  giveaways you cannot enter or cannot afford;
- it backs off when the site asks it to slow down and does not get around
  Cloudflare checks.

The risk cannot be removed entirely: by connecting SteamGifts you take it on
yourself. Bans most often come for unactivated wins, so activate the keys and
mark them received (see [Wins](#wins)).

## How a run goes

1. The farm reads the balance and checks for new wins.
2. If "Wishlist games first" («Сначала игры из списка желаемого») is on (in
   the farm settings), the site's **Wishlist** section is visited first.
3. Then the farm opens the chosen section ("Giveaway type" («Тип раздач»))
   and decides for each giveaway whether to enter it. It pauses 3–7 seconds
   between entries.
   - "Site-side filters" («Фильтры на стороне сайта», on by default): the
     listing address carries SteamGifts' own filters — level no higher than
     yours, price no higher than the points to spare (the balance minus "Keep
     balance above"), entrants no more than "Max entries". Giveaways you
     cannot enter never come back, and fewer pages are needed.
   - The `odds` order (the default): the farm gathers every page of the run
     first, then enters the best chance per point first:
     `odds = min(1, copies / (entrants + 1)) / price`. A 10-copy giveaway with
     300 entrants for 10 P ranks above a single copy with 4000 entrants for
     5 P. The `site` order enters as the site lists them, page by page.
4. If the balance drops below "Keep balance above" («Не опускать баланс
   ниже»), the farm waits about 15 minutes for points to accumulate.
5. If it has looked through "Pages per run" («Страниц за проход») and found
   no giveaway it can afford with the current balance, the farm also waits
   about 15 minutes. Without this limit it would page through the whole
   catalogue over and over. If the next runs enter nothing either and the
   balance has not grown by at least 10 P meanwhile, the pause grows to 30,
   then 60 minutes. Any entry, or the balance growing by 10 P, brings back
   15 minutes.
6. "Save up to (P)" («Копить до (P)»): when set, the farm enters nothing
   until the balance reaches that number (the site stops adding points at
   400), then spends it on the best odds down to "Keep balance above", and
   saves again. Without it, a balance just over the reserve only fits
   giveaways of a couple of points. The log and the card show "Saving points:
   120 of 300 P" («Копит поинты: 120 из 300 P»).
7. These pauses are not exact on purpose: each is up to 20 % longer or
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
| Giveaway type | `All` | Options: `All`, `WishList`, `Recommended`, `Copies`, `DLC`, `New`, `Group`. |
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
| Order (Порядок) | `odds` | odds: best chance per point first (copies, entrants, price) across all pages of the run; site: as the site lists them, page by page |
| Site-side filters (Фильтры на стороне сайта) | on | the site itself leaves out giveaways above your level, dearer than the points to spare or too crowded: fewer pages and requests |
| Save up to (P) (Копить до (P)) | empty | do not enter until the balance reaches N P (the site stops at 400), then spend on the best odds down to “Keep balance above”: this way the expensive giveaways get a chance too. Empty means enter right away |
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

- the daily Telegram summary reminds you about wins that are not marked yet,
  and about wins whose key is not activated yet;
- when the giveaway's creator has sent the key and SteamGifts shows it on the
  won page, the farm puts the key on the win itself (see below);
- the **"Mark as received on the site"** setting clicks that button itself
  when you mark a win in the panel. It is experimental and off by default:
  SteamGifts does not document this request anywhere. The result shows up in
  the SteamGifts log.

### The key from the won page

Unactivated wins are what SteamGifts bans for most often. So every time the
farm checks the won page (its first page, the same one it reads for new
wins), it looks for a key there:

- a Steam key (`AAAAA-BBBBB-CCCCC`, several of them for a bundle) or a gift
  link in the key box is saved on the win in [Wins](Wins-and-Keys-EN.md); the
  log says "Key for «…» taken from the SteamGifts won page" («Ключ к «…» взят
  со страницы выигрышей SteamGifts»);
- a link shown in the key box counts only when it looks like a gift or
  redeem link (`/gift`, `/redeem`, `/claim`, `key=`...): a shop's game page or
  the creator's site there is not taken. A link behind the copy button is
  taken as it is;
- outside the key box, a key is taken from the row's text only as Steam
  prints it: capitals and digits in groups of five, with at least one digit.
  Words like `rogue-lite-deck` are not keys;
- if "Activate won keys immediately" («Активировать выигранные ключи сразу») is on
  in the [farm settings](Farm-Settings-EN.md), a Steam key goes to ASF at once
  and the result arrives on Telegram. Otherwise a 🔑 KEY RECEIVED message
  arrives (it never shows the key itself);
- a key the win already has (pasted by hand or found earlier) is never
  replaced. A win with the "Activated" status is left alone;
- the farm presses nothing on the site: if the key is hidden behind the
  "View Key" button, it is not on the page and nothing happens. Reveal the key
  on the site yourself and the farm picks it up on the next check. Other codes
  (not Steam keys and not links) are pasted by hand;
- if the page does not look the way the farm expects, keys are simply not
  read and everything else works as usual.

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
