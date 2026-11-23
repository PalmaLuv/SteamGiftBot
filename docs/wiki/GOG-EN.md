# GOG

A few times a month a giveaway banner appears on the [GOG](https://www.gog.com/)
home page: the game can be claimed for free and stays in your GOG library for
good. The farm claims it by itself.

## Connecting

**Sites (Площадки) → GOG → Connect (Подключить)**. Sign in to gog.com, reload
the home page with the Network tab open and copy the first request as cURL.
The farm checks the sign-in and shows the account name.

## How it works

Every "Check every" («Проверять раз в») minutes (4 hours by default), the farm
sends the same request as the button on the banner (`/giveaway/claim`) and
looks at the response:

| GOG response | What it means |
| --- | --- |
| an empty `{}` response | the game was added to the library. The farm records an entry and reports it on Telegram |
| "Already claimed" | you have already claimed this giveaway |
| "Giveaway has ended", 404 | there is no giveaway right now |
| 401 | GOG no longer recognises the cookies; you need to [reconnect](Connecting-Sites-EN.md) |

GOG does not send the game's title in the response, so the farm takes it from
the banner on the home page. If the banner could not be read, the history
shows the entry "GOG giveaway" («Раздача GOG»).

## Settings

**Account (Аккаунт)**

| Setting | Default | What it does |
| --- | --- | --- |
| Cookie | — | gog.com → F12 → Network → F5 → right-click the first request → Copy → Copy as cURL |
| Browser User-Agent (User-Agent браузера) | empty | taken from cURL automatically |

**Operation (Работа)**

| Setting | Default | What it does |
| --- | --- | --- |
| Check every (min) | `240` | a giveaway stays up for several days, there is no point in checking more often |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

## Keep in mind

- When you claim a game, GOG may subscribe the account to its newsletter. You
  can unsubscribe in the GOG account settings, in the newsletter section.
- The Preview (Что возьмёт) tab shows the game only if the giveaway banner is
  currently visible on the home page. The farm tries to claim the game on
  every run regardless.
