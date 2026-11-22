# Panel API

The panel runs on top of a small JSON API. You can use it from your own
scripts, for example to start sites on a schedule from Home Assistant.

## Signing in

```bash
# sign in and save the session cookie
curl -c farm.cookie -H 'Content-Type: application/json' -H 'X-Requested-With: BotFarm' \
     -d '{"password": "your password"}' http://192.168.1.10:8092/api/login

# then pass the cookie along
curl -b farm.cookie http://192.168.1.10:8092/api/status
```

Rules:

- Every request except `/api/session` and `/api/login` requires the
  `botfarm_session` cookie. Without it the response is
  `401 {"error": "нужно войти"}` ("sign-in required").
- Every **POST** must carry the `X-Requested-With: BotFarm` header, otherwise
  the response is `403`.
- A POST body is a JSON object. An empty body means `{}`.
- Errors come back as `{"error": "text"}` with code 400, 401, 403, 404, 429 or
  500.

## Reading (GET)

| Path | What it returns |
| --- | --- |
| `/api/session` | `{signedIn, hasPassword}`; works without signing in |
| `/api/status` | `{platforms: [site snapshot…], wins: [unmarked wins], profiles: [{id, name, asfBot, main}], time}`; each site has `profile`, the profile id |
| `/api/summary?days=30` | per-day series for the chart: `{days: [...], sites: [{key, title, unit, today, spentToday, entered, spent, wins, winsWeek, entries[], spentByDay[], winsByDay[], importedByDay[], luck}]}`; `luck` is `null` for free sites and before the first entry, else `{entries, known, unknown, forecast, expected, wins, spent, perWin, avgCost, since}` |
| `/api/history?kind=entries&site=&q=&page=1&per=50` | `{rows, total, page, pages}`; `kind` is `entries` or `wins` |
| `/api/history.csv?kind=entries&site=&q=` | the same selection as CSV |
| `/api/farm/settings` | `{schema, values, info: {zones, panelURLs, startedAt, now, zone}}` |
| `/api/platforms/<key>/settings` | `{schema, values, autostart, guide, connectFields, presets}` |
| `/api/platforms/<key>/logs?after=<id>` | log lines newer than the given `id` |
| `/api/platforms/<key>/history` | the site's last 50 entries and wins, plus `lists` |

A site snapshot in `/api/status` looks like this (the `reason` here reads
"Out of iS (0), waiting for a top-up"):

```json
{"key": "indiegala", "title": "IndieGala", "state": "sleeping", "reason": "Закончился iS (0), ждёт пополнения",
 "error": "", "balance": 0, "unit": "iS", "account": "…", "nextCycle": 1795180000.0, "lastCycle": 1795176400.0,
 "configured": true, "autostart": true, "category": "points", "needs": "cookie",
 "totals": {"entered": 131, "spent": 581, "wins": 1, "today": 3},
 "limits": {"entries": {"used": 3, "max": 30}, "spend": {"used": 20, "max": 40}, "hours": "08:00-23:00", "opensAt": null},
 "lists": ["blacklist", "priority"]}
```

`state` is one of `running`, `sleeping`, `stopped`, `error`, `auth`.

## Actions (POST)

**The whole farm**

| Path | Body | What it does |
| --- | --- | --- |
| `/api/login` | `{password}` | signs in, sets the cookie |
| `/api/logout` | — | signs out |
| `/api/logout-all` | — | ends all other sessions |
| `/api/password` | `{current, new}` | changes the password |
| `/api/start-all`, `/api/stop-all` | — | start or stop all connected sites |
| `/api/farm/settings` | `{values: {...}}` | save the farm settings; you can pass only some of the fields |
| `/api/farm/report` | — | send the summary to Telegram |
| `/api/notify-test` | — | a test message to Telegram |
| `/api/telegram/chats` | `{token?}` | chats where someone wrote to the bot |
| `/api/steam/check` | — | check the library and the wishlist |
| `/api/asf/check` | — | check ASF → `{ok, message, bots, online}` |
| `/api/profiles/create` | `{name, asfBot?}` | create a [profile](Multiple-Profiles-EN.md) → `{ok, id, name}` |
| `/api/profiles/<id>/update` | `{name?, asfBot?}` | rename a profile, change its ASF bot |
| `/api/profiles/<id>/delete` | — | delete a profile with all its sites; `main` cannot be deleted |
| `/api/accounts/add` | `{kind, profile, values: {cookie}}` | connect a site to a profile: checks the cookie on the site and only then creates the card → `{ok, key, title, account, balance}` |

**A single site**: the path starts with `/api/platforms/<key>/`, where `<key>`
is one of `steamgifts`, `indiegala`, `opiumpulses`, `steamfree`, `gog`,
`itch`, and for sites in [added profiles](Multiple-Profiles-EN.md) it carries
a number: `steamgifts-2`, `indiegala-3`.

| Action | Body | What it does |
| --- | --- | --- |
| `start`, `stop`, `restart` | — | start, stop, restart |
| `run-now` | — | a run right now, ignoring the pause and working hours |
| `autostart` | `{value: true}` | whether to start together with the farm |
| `settings` | `{values, autostart?, connect?}` | save settings; secrets passed empty are left unchanged |
| `preset` | `{name}` | apply a preset: `balanced`, `economy`, `maximum`, `games` |
| `check` | `{values: {cookie}}` | test the connection without saving → `{ok, account, balance}` |
| `disconnect` | — | forget the cookies and stop |
| `preview` | — | a trial run → `{balance, items: [{name, url, cost, entries, enter, reason}], note}` |
| `list` | `{list: "blacklist" \| "priority", value}` | add a game to a list |
| `win` | `{time, name, status}` or `{time, name, key}` | a win's status or its key |
| `redeem` | `{time, name}` | activate a win's key through ASF |
| `label` | `{label}` | a custom card name instead of the profile name → `{ok, title}` |
| `key-bot` | `{bot}` | the ASF bot for keys of this particular site; empty means the profile's bot |
| `remove` | — | remove the site from its profile (a site's first card can only be `disconnect`ed) |

## Example: start IndieGala on a schedule

```bash
curl -s -b farm.cookie -H 'X-Requested-With: BotFarm' -X POST \
     http://192.168.1.10:8092/api/platforms/indiegala/start
```

Keep in mind that a session lives for 30 days. For permanent automation it is
simpler to set "Working hours" («Часы работы») right in the site's settings.
