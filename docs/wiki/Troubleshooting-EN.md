# Troubleshooting

First open the **Log (Журнал)** and the site that is behaving oddly, and then
its **Preview (Что возьмёт)** tab. The reason is almost always written there.

## Panel

| Problem | Cause and fix |
| --- | --- |
| The panel does not open from other devices | the port is blocked by the firewall ([Server and service](Server-and-Service-EN.md#firewall)) or `--host` has a different address |
| It does not open even on the server | the farm is not running: `systemctl status botfarm`, `journalctl -u botfarm -n 50` |
| "Password not set" («Пароль не задан») on the sign-in page | run `env/bin/python -m steamgiftbot.farm --set-password` |
| "Too many attempts, wait 10 minutes" («Слишком много попыток, подождите 10 минут») | 10 wrong passwords in a row; wait, or set the password again with the command above |
| "No connection to the farm" («Нет связи с фермой») in the menu | the farm is restarting or has crashed; reload the page in a minute |
| You still see the old panel after an update | reload the page and clear the cache: `Ctrl+Shift+R` |

## Sites

| Message | What it means | What to do |
| --- | --- | --- |
| "Sign-in required" («Нужен вход заново»), "… does not recognise the cookies" («… не узнаёт cookie») | the cookies no longer work | **Reconnect (Подключить заново)** ([Connecting sites](Connecting-Sites-EN.md)) |
| "Error, retrying" («Ошибка, повтор»), "… is unavailable" («… недоступна»), "HTTP 5xx" | the site is temporarily not responding | nothing: the farm retries in 15 minutes |
| "… asks to slow down (HTTP 429)" («… просит притормозить (HTTP 429)») | too many requests | nothing: the farm waits and continues |
| "IndieGala showed an Incapsula check" («IndieGala показала проверку Incapsula») | the site's protection is not letting the farm in | open IndieGala in the same browser, pass the check and reconnect the site |
| "SteamGifts answered with a Cloudflare check" | the same for SteamGifts | open the site in the browser; the farm retries later |
| "Outside working hours, next run at 08:00" («Вне часов работы, следующий проход в 08:00») | working hours are set | that is by design; see [Rules and filters](Rules-and-Filters-EN.md#working-hours) |
| "Daily limit reached" («Дневной лимит исчерпан») | the entry or spending limit was reached | that is by design; the limit is rolling, over 24 hours |
| "Site stopped: …" («Площадка остановлена: …») | the site answered in a way that makes continuing impossible (for example, "account banned from giveaways") | read the message and sort it out on the site |
| "Unexpected error" («Неожиданная ошибка») with a traceback | a bug in the farm | the farm retries in 15 minutes; if it keeps happening, open an issue with these log lines |

## SteamGifts

| Problem | Fix |
| --- | --- |
| "No suitable giveaways" («Подходящих раздач нет») | nothing affordable with the current balance passes the filters. The farm will wait for points. Check "Max participants" («Макс. участников») and the level |
| Almost everything is skipped | set your contributor level, otherwise giveaways with a level above yours are filtered out for nothing |
| It does not enter even though there are points | the balance is below "Keep balance above" («Не опускать баланс ниже») |

## IndieGala

| Problem | Fix |
| --- | --- |
| It enters nothing | Preview shows the reason: most often "not enough iS" («не хватает iS») or a wrong level |
| "Skipped: already entered" («Пропущено: уже участвуете») | you have already entered these giveaways, for example by hand on the site |
| It entered a game you did not want | turn on the "no 18+" and "no DLC" filters or apply the "Games only" («Только игры») preset; add a specific game to the blacklist with the 🚫 button |

## OpiumPulses

| Problem | Fix |
| --- | --- |
| "giveaways on the page: 0" («раздач на странице: 0») | check in the browser. If there are no giveaways there either, just wait. If the browser has them but the farm does not, attach `debug/opiumpulses-giveaways.html` to an issue |

## Telegram and ASF

- **Telegram**: see [Telegram → If it does not work](Telegram-EN.md#if-it-does-not-work).
- **ASF**: see [ArchiSteamFarm → Connection errors](ArchiSteamFarm-EN.md#connection-errors).

## The Steam library does not load

Press **Settings → Steam library → Check (Настройки → Библиотека Steam →
Проверить)** and look at the response:

| Response | Fix |
| --- | --- |
| "Steam did not accept the API key" («Steam не принял API-ключ») | the key is wrong or revoked. Get a new one at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) |
| "Steam did not return the game list" («Steam не отдал список игр») | make "Game details" public in your profile's privacy settings |
| "the wishlist is empty or hidden" («список желаемого пуст или скрыт») | make the "Wishlist" public in your profile's privacy settings |
| "could not find the Steam profile" («не нашёл профиль Steam») | check the profile link; a link like `/id/name` needs an API key |

## How to collect data for an issue

1. Log → the site → **Errors (Ошибки)** → **Download (Скачать)**.
2. `journalctl -u botfarm --since "-1 hour" > botfarm.txt`.
3. Before sending, remove cookies, tokens and addresses from the files. The
   farm does not write them to the log, but it is better to check.
