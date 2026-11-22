# OpiumPulses

[OpiumPulses](https://www.opiumpulses.com/giveaways) runs key giveaways. Some
giveaways are free; the rest cost OP, points the site awards for activity.

## Connecting

**Sites (Площадки) → OpiumPulses → Connect (Подключить)**. Sign in to the
site through Steam, open `opiumpulses.com/giveaways` and copy the first
request as cURL.

### Session and cookie expiry

The farm keeps one session with the site from run to run while the pasted
text and the User-Agent stay the same. Cookies the site refreshes on its own
(bot protection, a renewed sign-in) are no longer lost that way. The new values
of the cookies that were in the pasted text are written to `farm.json` next to
it (`sessionCookies` of the site); the text itself is left as it was. After a
restart the farm puts them over the paste. A new paste starts from scratch, and
disconnecting the site erases what was kept. When the site stops accepting the
session (🔑 SIGN-IN NEEDED), what was kept is erased too: the next start,
the Start («Старт») button in the panel included, begins from the pasted text
again. The log only ever shows cookie names, never their values.

When the expiry of the sign-in cookie (`PHPSESSID` or the "remember me" cookie) is known, the Connection
(«Подключение») tab shows it. A Cookie-Editor export (JSON) and cookies.txt
carry it, and so does a Set-Cookie when the site renews the cookie itself; cURL
and a Cookie line do not. 3 days before it, a running site sends one
🔑 COOKIE EXPIRES SOON message with a Reconnect («Подключить заново») button.
If the site renews the cookie for a long time, the farm reminds about the new
date separately. If the site only moves the date a little with every answer (a
cookie for a day or two), there is no second reminder: such a cookie does not
expire while the farm is running.

## How a run goes

1. The farm opens the giveaway list and checks that you are signed in.
2. It reads the OP balance and the giveaways on the page, then moves on to
   the next pages, up to "Pages per run" («Страниц за проход») in total.
3. It skips giveaways you have already entered, paid ones (if "Free only"
   («Только бесплатные») is on), ones that are too expensive and ones removed
   by the filters.
4. It enters the rest, pausing 3–7 seconds between giveaways.
5. If "Track won keys" («Следить за выигранными ключами») is on, it checks
   the [your keys](https://www.opiumpulses.com/user/giveawaykeys) page. On the
   first check the farm only remembers the keys that are already there, so it
   does not send notifications about old ones.

## Settings

**Account (Аккаунт)**

| Setting | Default | What it does |
| --- | --- | --- |
| Cookie | — | opiumpulses.com/giveaways → F12 → Network → F5 → right-click the first request → Copy → Copy as cURL, paste all of it. A Cookie-Editor export or a Cookie line also works |
| Browser User-Agent (User-Agent браузера) | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36` | taken from cURL automatically; otherwise use the one from the browser the cookies came from |

**What to enter (Что брать)**

| Setting | Default | What it does |
| --- | --- | --- |
| Free only | off |  |
| Keep balance above (OP) (Не опускать баланс ниже (OP)) | `0` |  |
| Max price (OP) (Макс. цена (OP)) | empty | empty means any |
| Whitelist (Белый список) | empty | if set, only these games |
| Blacklist (Чёрный список) | empty | words separated by commas |

**Filters (Фильтры)**

| Setting | Default | What it does |
| --- | --- | --- |
| Skip games in my Steam library (Пропускать игры из моей библиотеки Steam) | off | needs a Steam API key and a profile in the farm settings |
| Skip DLC, soundtracks, artbooks, packs (Пропускать DLC, саундтреки, артбуки, паки) | off |  |
| Skip 18+ (Пропускать 18+) | off |  |

**Operation (Работа)**

| Setting | Default | What it does |
| --- | --- | --- |
| Pages per run | `5` |  |
| Track won keys | on |  |
| Pause between runs (min) (Пауза между проходами (мин)) | `120` |  |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

## If there are no giveaways

Sometimes OpiumPulses shows no giveaways at all, even in the browser and even
with the filters reset. Then the log says "giveaways on the page: 0" («раздач
на странице: 0»), and the farm simply checks again on the next run.

If the browser does show giveaways but the farm sees 0, the site has changed
its markup. The farm saves the page it received to
`debug/opiumpulses-giveaways.html` and writes "The giveaway page does not look
as expected" («Страница раздач выглядит не так, как ожидалось») to the log.
Attach that file to an issue: it is what the page parsing can be fixed from.
