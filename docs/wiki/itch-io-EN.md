# itch.io

On [itch.io](https://itch.io/games/on-sale), developers sometimes put their
games at 100% off: while the discount lasts, the game can be added to your
library for free, for good. The farm finds such games and claims them a few
at a time.

## Connecting

**Sites (Площадки) → itch.io → Connect (Подключить)**. Sign in to itch.io,
open `itch.io/my-purchases` and copy the first request as cURL. The farm needs
the `itchio` cookie (the sign-in) and `itchio_token` (form protection). Both
end up in the cURL automatically.

## Where the game list comes from

The list comes from the [ItchClaim](https://github.com/Smart123s/ItchClaim)
project, which lists the games currently at 100% off. Before claiming a game,
the farm checks on itch.io itself that it is still free.

## How a run goes

1. The farm checks the sign-in and downloads the list.
2. It drops games it has already claimed and applies the filters.
3. It claims no more than "Max per run" («Не больше за проход») games (15 by
   default), pausing 6–12 seconds: itch.io quickly answers "too many
   requests".
4. A game is claimed with the same request as the site's "Download or claim"
   button. After that the game appears in "My library".

## Settings

**Account (Аккаунт)**

| Setting | Default | What it does |
| --- | --- | --- |
| Cookie | — | itch.io → F12 → Network → F5 → right-click the first request → Copy → Copy as cURL |
| Browser User-Agent (User-Agent браузера) | empty | taken from cURL automatically |

**What to enter (Что брать)**

| Setting | Default | What it does |
| --- | --- | --- |
| Max per run | `15` | itch.io quickly answers "too many requests", so a few at a time is better |
| Whitelist (Белый список) | empty | if set, only these |
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
| Pause between runs (min) (Пауза между проходами (мин)) | `120` |  |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

## Keep in mind

- Most itch.io giveaways are indie games, assets, sounds and fonts. The
  blacklist and whitelist and the "no DLC and packs" filter help weed out
  what you don't want.
- If itch.io answers HTTP 429, the farm waits 15 minutes and continues.
