# IndieGala

[IndieGala Giveaways](https://www.indiegala.com/giveaways) runs Steam key
giveaways that you enter with Galasilver (iS). The site awards iS for
purchases and daily rewards. Each giveaway allows one ticket per person; some
giveaways let you take extra tickets (extra odds).

## Connecting

**Sites (Площадки) → IndieGala → Connect (Подключить)**. Sign in to the site
(Login at the top right), open `indiegala.com/giveaways` and copy the first
request as cURL. Be sure to do it in the same browser you signed in with:
IndieGala is protected by Incapsula and matches the cookies against the
browser. When you copy as cURL, the farm also takes the browser's User-Agent.

**Right after connecting, set "Your IndieGala level" («Ваш уровень на
IndieGala»).** It is shown in your profile on the site. IndieGala only shows
giveaways for your level, and level 0 on a new account is normal.

## How a run goes

1. The farm reads the iS balance.
2. It collects giveaways from the site's pages. Only pages with new giveaways
   count, so if the first pages have already been gone through completely,
   the farm pages further. The end of the list is the first empty page; it
   never looks at more than 40 pages per run.
3. It sorts the giveaways by the chosen order. Priority games and wishlist
   games are moved to the front.
4. It enters the giveaways one by one, pausing 3–7 seconds, as long as there
   is iS above the reserve and the daily limit is not used up.
5. At the end it writes a summary to the log: "Skipped: not enough iS — 33,
   18+ — 3, …" («Пропущено: не хватает iS — 33, 18+ — 3, …»).
6. It waits for "Pause between runs" («Пауза между проходами»), 60 minutes by
   default.

## The smart order

With the `smart` order, giveaways are ranked by the chance of winning per iS
spent. A giveaway's value is calculated like this:

```
value = 1 / ((participants by the end + 1) × max(1, price in iS))
```

"Participants by the end" is a forecast: the people already in plus those
still to come before the giveaway ends. The farm sees the same giveaways on
every run and remembers how fast they fill up. A giveaway's own pace is known
20 minutes after the farm first saw it; until then the typical pace of the
others stands in. Right after a start there is no forecast yet, and only the
current participants count.

So a giveaway that ends in 10 minutes with 20 participants ranks above one with
15 participants that still has two days to gather people. When the value is
equal, the one that ends sooner goes first. The forecast shows in Preview («Что
возьмёт», the arrow next to the participant count) and in the entry details in
the log.

The other orders repeat the site's own sorting: `expiry` (ending soonest
first), `price`, `participants`, `level`.

## Tickets per game

Developers often give the same game away many times, and without a limit the
farm took a ticket for each of those giveaways: 21 tickets for Puzzle Chambers
in two days. One key is enough, so "Tickets per game" («Билетов на одну игру»,
3 by default) limits how many giveaways of one game the farm enters over 7
days. Titles are compared ignoring case and the ™ ® marks. Priority games are
not limited, and an empty field removes the limit.

## Priority games and the reserve

- **Priority games (Приоритетные игры)**: words separated by commas, for
  example `hades, hollow knight`. Giveaways with these words in the title go
  first and are marked with ★ in the log.
- **Steam wishlist games** also count as priority if "Wishlist games first"
  («Сначала игры из списка желаемого») is on in the
  [farm settings](Farm-Settings-EN.md).
- **"Keep balance above" («Не опускать баланс ниже»)** is the iS reserve that
  the farm does not spend on ordinary giveaways.
- **"Allow spending the reserve on priority games" («На приоритетные можно
  тратить резерв»)**: for a priority game the farm will spend the reserve too.

## Wins

IndieGala does not tell you about a win: a finished giveaway waits in the
library, under Giveaways → Completed to check, until someone presses "Check if
you won". Every 3 hours the farm presses "Check all" there, then reads
Completed won, and for each new win it:

- records it under "Wins" in the panel together with the key (or the gift
  link);
- sends a card to Telegram, without the key itself;
- sends the key to ASF if "Activate won keys immediately" («Активировать
  выигранные ключи сразу») is on in the [farm settings](Farm-Settings-EN.md).

On the first check the farm only remembers what was won before and does not
announce old wins. Turn it off with "Check for wins" («Проверять выигрыши»).

## Settings

**Account (Аккаунт)**

| Setting | Default | What it does |
| --- | --- | --- |
| Cookie | — | indiegala.com/giveaways → F12 → Network → F5 → right-click the first request → Copy → Copy as cURL, paste all of it. A Cookie-Editor export or a Cookie line also works |
| Browser User-Agent (User-Agent браузера) | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36` | taken from cURL automatically; otherwise use the one from the browser the cookies came from |
| Your IndieGala level | `0` | only giveaways of this level are shown |
| Check for wins (Проверять выигрыши) | on | every 3 hours the farm presses “Check all” in the IndieGala library and saves the keys of your wins |

**Balance and priorities (Баланс и приоритеты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Keep balance above (iS) | `0` |  |
| Priority games | empty | words separated by commas: the farm enters these giveaways first |
| Allow spending the reserve on priority games | on |  |

**What to enter (Что брать)**

| Setting | Default | What it does |
| --- | --- | --- |
| Min ticket price (iS) (Мин. цена билета (iS)) | empty | cheap tickets usually mean cheap games; empty means any |
| Max ticket price (iS) (Макс. цена билета (iS)) | empty | empty means any |
| Max participants (Макс. участников) | empty | skip giveaways with more participants |
| Only ending within N hours (Только кончающиеся в ближайшие N часов) | empty | near the end of a giveaway you can tell how many rivals there will be; empty means any |
| Tickets per game (Билетов на одну игру) | `3` | how many giveaways of the same game to enter over 7 days: one key is enough anyway. Empty means no limit; priority games are not limited |
| Take extra tickets (extra odds) (Брать доп. билеты (extra odds)) | off | repeat tickets for the same giveaway |
| Whitelist (Белый список) | empty | if set, only these games |
| Blacklist (Чёрный список) | empty | words separated by commas |

**Filters (Фильтры)**

| Setting | Default | What it does |
| --- | --- | --- |
| Skip games in my Steam library (Пропускать игры из моей библиотеки Steam) | off | needs a Steam API key and a profile in the farm settings |
| Skip DLC, soundtracks, artbooks, packs (Пропускать DLC, саундтреки, артбуки, паки) | off |  |
| Skip 18+ (Пропускать 18+) | off |  |

**Browsing order (Порядок обхода)**

| Setting | Default | What it does |
| --- | --- | --- |
| Order (Порядок) | `smart` | smart: best chance per iS first (few participants, cheap ticket); expiry: ending soonest first; price, participants, level: as on the site. Options: `smart`, `expiry`, `price`, `participants`, `level`. |
| Pages per run (Страниц за проход) | `5` | only pages with new giveaways count |
| Pause between runs (min) | `60` |  |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

## Site responses

| Response | What the farm does |
| --- | --- |
| already entered, giveaway ended, level too low, participant limit reached, it is your own giveaway | does not try this giveaway again |
| not enough silver | ends the run |
| too many requests | waits 2 minutes and continues |
| asks you to sign in again | stops the site and reports it on Telegram |
| account banned from giveaways | stops the site |
| Incapsula check, HTTP 429 or 5xx | tries again in 15 minutes |

## FAQ

**The farm enters nothing.** Open the Preview (Что возьмёт) tab: every
giveaway there has a reason. Most often the iS ran out ("not enough iS") or
the level is wrong.

**"Skipped: already entered" («Пропущено: уже участвуете»).** It means you
have already entered this giveaway, for example by hand on the site.

**Balance 0 iS.** The farm will continue once it is topped up: iS is awarded
for purchases and daily rewards on IndieGala.
