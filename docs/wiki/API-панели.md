# API панели

Панель работает поверх небольшого JSON API. Им можно пользоваться из своих
скриптов, например чтобы запускать площадки по расписанию из Home Assistant.

## Вход

```bash
# войти и сохранить cookie сессии
curl -c farm.cookie -H 'Content-Type: application/json' -H 'X-Requested-With: BotFarm' \
     -d '{"password": "ваш пароль"}' http://192.168.1.10:8092/api/login

# дальше передавать cookie
curl -b farm.cookie http://192.168.1.10:8092/api/status
```

Правила:

- Все запросы, кроме `/api/session` и `/api/login`, требуют cookie
  `botfarm_session`. Без него ответ — `401 {"error": "нужно войти"}`.
- Каждый **POST** обязан нести заголовок `X-Requested-With: BotFarm`, иначе ответ — `403`.
- Тело POST — JSON-объект. Пустое тело означает `{}`.
- Ошибки приходят как `{"error": "текст"}` с кодом 400, 401, 403, 404, 429 или 500.

## Чтение (GET)

| Путь | Что возвращает |
| --- | --- |
| `/api/session` | `{signedIn, hasPassword}`; работает без входа |
| `/api/status` | `{platforms: [снимок площадки…], wins: [неотмеченные выигрыши], profiles: [{id, name, asfBot, main}], time}`; у площадки есть `profile` — id учётки |
| `/api/summary?days=30` | ряды по дням для графика: `{days: [...], sites: [{key, title, unit, today, spentToday, entered, spent, wins, winsWeek, entries[], spentByDay[], winsByDay[], importedByDay[], luck}]}`; `luck` — `null` у бесплатных площадок и до первого входа, иначе `{entries, known, unknown, forecast, expected, wins, spent, perWin, avgCost, since}` |
| `/api/history?kind=entries&site=&q=&page=1&per=50` | `{rows, total, page, pages}`; `kind` — `entries` или `wins` |
| `/api/history.csv?kind=entries&site=&q=` | та же выборка в CSV |
| `/api/farm/settings` | `{schema, values, info: {zones, panelURLs, startedAt, now, zone}}` |
| `/api/platforms/<key>/settings` | `{schema, values, autostart, guide, connectFields, presets}` |
| `/api/platforms/<key>/logs?after=<id>` | строки лога новее указанного `id` |
| `/api/platforms/<key>/history` | последние 50 входов и выигрышей площадки, плюс `lists` |

Снимок площадки в `/api/status` выглядит так:

```json
{"key": "indiegala", "title": "IndieGala", "state": "sleeping", "reason": "Закончился iS (0), ждёт пополнения",
 "error": "", "balance": 0, "unit": "iS", "account": "…", "nextCycle": 1795180000.0, "lastCycle": 1795176400.0,
 "configured": true, "autostart": true, "category": "points", "needs": "cookie",
 "totals": {"entered": 131, "spent": 581, "wins": 1, "today": 3},
 "limits": {"entries": {"used": 3, "max": 30}, "spend": {"used": 20, "max": 40}, "hours": "08:00-23:00", "opensAt": null},
 "lists": ["blacklist", "priority"]}
```

`state` — одно из `running`, `sleeping`, `stopped`, `error`, `auth`.

## Действия (POST)

**Ферма целиком**

| Путь | Тело | Что делает |
| --- | --- | --- |
| `/api/login` | `{password}` | вход, ставит cookie |
| `/api/logout` | — | выход |
| `/api/logout-all` | — | завершает все остальные сессии |
| `/api/password` | `{current, new}` | смена пароля |
| `/api/start-all`, `/api/stop-all` | — | запустить или остановить все подключённые площадки |
| `/api/farm/settings` | `{values: {...}}` | сохранить настройки фермы; можно передать только часть полей |
| `/api/farm/report` | — | прислать сводку в Telegram |
| `/api/notify-test` | — | тестовое сообщение в Telegram |
| `/api/telegram/chats` | `{token?}` | чаты, где боту писали |
| `/api/steam/check` | — | проверить библиотеку и список желаемого |
| `/api/asf/check` | — | проверить ASF → `{ok, message, bots, online}` |
| `/api/profiles/create` | `{name, asfBot?}` | создать [учётку](Несколько-учёток.md) → `{ok, id, name}` |
| `/api/profiles/<id>/update` | `{name?, asfBot?}` | переименовать учётку, сменить её бота ASF |
| `/api/profiles/<id>/delete` | — | удалить учётку со всеми её площадками; `main` удалить нельзя |
| `/api/accounts/add` | `{kind, profile, values: {cookie}}` | подключить площадку в учётку: проверяет cookie на сайте и только тогда заводит карточку → `{ok, key, title, account, balance}` |

**Одна площадка** — путь начинается с `/api/platforms/<key>/`, где `<key>` — одно из
`steamgifts`, `indiegala`, `opiumpulses`, `steamfree`, `gog`, `itch`, а у
[добавленных учёток](Несколько-учёток.md) — с номером: `steamgifts-2`, `indiegala-3`.

| Действие | Тело | Что делает |
| --- | --- | --- |
| `start`, `stop`, `restart` | — | запуск, остановка, перезапуск. Если площадка ещё останавливается, `start` и `restart` запускают её, как только она остановится, и отвечают `{started: true}` |
| `run-now` | — | проход сейчас, без учёта паузы и часов работы |
| `autostart` | `{value: true}` | запускать ли вместе с фермой |
| `settings` | `{values, autostart?, connect?}` | сохранить настройки; секреты, переданные пустыми, не меняются |
| `preset` | `{name}` | применить набор: `balanced`, `economy`, `maximum`, `games` |
| `check` | `{values: {cookie}}` | проверить подключение без сохранения → `{ok, account, balance}` |
| `disconnect` | — | забыть cookie и остановить |
| `preview` | — | пробный проход → `{balance, items: [{name, url, cost, entries, enter, reason}], note}` |
| `list` | `{list: "blacklist" \| "priority", value}` | добавить игру в список |
| `win` | `{time, name, status}` или `{time, name, key}` | статус выигрыша или его ключ |
| `redeem` | `{time, name}` | активировать ключ выигрыша через ASF |
| `label` | `{label}` | своё имя карточки вместо имени учётки → `{ok, title}` |
| `key-bot` | `{bot}` | бот ASF для ключей именно этой площадки; пусто — бот учётки |
| `remove` | — | убрать площадку из учётки (первую карточку сайта можно только `disconnect`) |

## Пример: запустить IndieGala по расписанию

```bash
curl -s -b farm.cookie -H 'X-Requested-With: BotFarm' -X POST \
     http://192.168.1.10:8092/api/platforms/indiegala/start
```

Учтите, что сессия живёт 30 дней. Для постоянной автоматизации проще задать
«Часы работы» прямо в настройках площадки.
