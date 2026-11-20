# Free Steam games

Now and then Steam gives games away for keeps: a game becomes free for a
while, and if you add it to your library, it stays yours for good. This site
adds such games by itself.

The farm itself does not sign in to Steam: the games are added by
[ArchiSteamFarm](ArchiSteamFarm-EN.md) (ASF) on behalf of your bots. That is
why this site needs no cookies, but it does need a running ASF.

## Connecting

1. Make sure ASF is running and its bots are online. If ASF runs on the same
   server with an IPC password in `~/asf/config/ASF.json`, nothing else needs
   to be set up. Otherwise enter the ASF address and password in **Settings →
   ArchiSteamFarm (Настройки → ArchiSteamFarm)**.
2. **Sites → Free Steam games → Connect → Test connection (Площадки →
   Бесплатные игры Steam → Подключить → Проверить подключение).** The farm
   asks ASF for its list of bots and shows which of them are online.
3. Choose a preset and press **Save and start (Сохранить и запустить)**.

## Where the game list comes from

The farm uses the public [ASFinfo](https://github.com/C4illin/ASFinfo) list,
the same one the FreePackages plugin for ASF uses. It is plain text where
each line is `a/<appid>` (a game) or `s/<subid>` (a package), newest first.

## How a run goes

1. The farm downloads the list and picks out what it has not tried yet.
2. It looks up the game titles in the Steam store so it can apply the
   filters: the blacklist, "no DLC", "no 18+".
3. It takes no more than "Max per run" («Не больше за проход») items (20 by
   default): Steam limits the number of free licences per hour.
4. It sends them to ASF in one request (`AddLicense`) for all bots.
5. It writes every result to the log. Added games go into the entry history.

| Result | What the farm does |
| --- | --- |
| added to the library | records an entry and leaves this game alone from then on |
| already in the library | leaves this game alone from then on |
| Steam asks to wait or did not reply | tries on the next run |
| other refusals | leaves this game alone from then on |

## Settings

**What to enter (Что брать)**

| Setting | Default | What it does |
| --- | --- | --- |
| ASF bots (Боты ASF) | empty | each ASF bot is a separate Steam account; names separated by commas, empty means all bots |
| Max per run | `20` | Steam limits the number of free licences per hour |
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
| Check every (min) (Проверять раз в (мин)) | `180` |  |

**Schedule and limits (Расписание и лимиты)**

| Setting | Default | What it does |
| --- | --- | --- |
| Working hours (Часы работы) | empty | for example 08:00-23:00 or 09:00-13:00, 18:00-02:00; empty means around the clock. The time zone is set in the farm settings |
| Max entries per day (Макс. входов за сутки) | empty | empty means no limit |
| Max spending per day (Макс. трат за сутки) | empty | in the site's currency; empty means no limit |

"Max spending per day" means nothing for this site: the games are free.
"Max entries per day" works as usual.
