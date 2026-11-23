# Development

## How it is put together

```
steamgiftbot/
  bot.py, filters.py, …   the command-line bot (SteamGifts)
  farm/
    __main__.py           startup: options, logs, listeners, autostart
    manager.py            FarmManager: farm.json, state, summary, Telegram, ASF
    base.py               Platform: site thread, waits, limits, settings forms, cookie parsing
    rules.py              word filters, working hours, Steam library and wishlist
    steamgifts.py …       one module per site
    asf.py                ArchiSteamFarm IPC client
    telegram.py           Telegram commands (long polling)
    web.py                HTTP server and JSON API on the stdlib
    static/index.html     the whole panel: a single page, no build step
scripts/build-wiki.py     fills the settings tables in this wiki from the code
tests/                    pytest, no network
```

**Threads.** Each site has its own thread (`Platform.loop`). There is also the
farm clock (the daily summary, once a minute), the Telegram command thread and
one HTTP server per address from `--host`. Sites do not share sessions with
each other. The trial run works on a copy of the site (`Platform.sandbox`)
with its own session, so it does not interfere with a run in progress.

**Errors.** A site reports a problem with exceptions from `base.py`:

| Exception | What the farm does |
| --- | --- |
| `AuthError` | stops the site, status "Sign-in required" («Нужен вход заново»), a message on Telegram |
| `PlatformError` | stops the site with an error, a message on Telegram |
| `RetryLater` | status "Error, retrying" («Ошибка, повтор»), a new attempt in 15 minutes. Raised `from` a `requests.ConnectionError` or `Timeout` (the site was not reached at all), it is retried sooner: after 1, 2, 5 minutes, then every 15 |
| anything else | the same as an unreached site (1, 2, 5, then 15 minutes), plus a traceback in the log |

## How to add a site

1. Create `steamgiftbot/farm/mysite.py` with a class derived from `Platform`.
   The labels in the example are in Russian, like the rest of the panel's
   labels in the code:

```python
from steamgiftbot.farm.base import (Platform, AuthError, RetryLater, buildSession, cookieGuide,
                                    field, grouped, parseCookies, presetFields, scheduleFields)


class MySitePlatform(Platform):
    key, title, unit = 'mysite', 'MySite', 'MP'
    siteURL = 'https://mysite.example/giveaways'
    description = 'Раздачи за MP.'
    category = 'points'              # or 'free'

    def schema(self):                # settings form; groups become sections
        return grouped('Аккаунт', [
            field('cookie', 'Cookie', 'secret', help='скопируйте запрос как cURL'),
        ]) + grouped('Работа', [
            field('interval', 'Пауза между проходами (мин)', 'int', 60),
        ]) + presetFields() + scheduleFields()

    def configured(self):
        return bool(self.settings().get('cookie'))

    def guide(self):                 # connection wizard steps
        return cookieGuide('MySite', self.siteURL)

    def check(self, values):         # the wizard's check, without saving
        conf = self.trialSettings(values)
        box = self.sandbox()
        box.session = buildSession(None, parseCookies(conf['cookie']), '.mysite.example')
        ...                          # sign in, read the balance; AuthError if refused
        return {'account': 'name', 'balance': 42}

    def preview(self):               # Preview: spend nothing
        return {'balance': 42, 'account': '', 'note': '', 'items': [
            {'name': 'Game', 'url': '…', 'cost': 1, 'entries': 10, 'enter': True, 'reason': ''}]}

    def run(self):                   # main loop
        while not self.stopped:
            conf = self.gate()       # waits for working hours and limits; None means stopped
            if conf is None:
                return
            ...                      # a run: self.ruleReason(), self.dailyLeft(),
                                     # self.recordEntry(name, cost, url), self.pause()
            if not self.wait(conf['interval'] * 60):
                return
```

   (In the example: `'Раздачи за MP.'` is "Giveaways for MP.", `'Аккаунт'` is
   "Account", `'скопируйте запрос как cURL'` is "copy the request as cURL",
   `'Работа'` is "Operation", `'Пауза между проходами (мин)'` is "Pause
   between runs (min)".)

2. Register the class in `FarmManager.__init__` (`manager.py`), in the list of
   sites.
3. If the site has a different currency, add its colour to
   `static/index.html` (`--s-mysite`); otherwise it gets the shared colour.
4. Write tests: page parsing (an HTML fixture in `tests/fixtures`), a run
   against a fake site (like `FakeIndieGala` in `tests/test_farm.py`),
   `check()` and `preview()`.
5. Add a page to the wiki with a `<!-- settings:mysite --><!-- /settings -->`
   block and run `env/bin/python scripts/build-wiki.py`. The script fills the
   block from the code in Russian, so it goes on the Russian page; the English
   pages carry the settings tables as plain text without these blocks.

**What to use from `Platform`:**

- `self.settings()`: the current settings;
- `self.gate()`, `self.wait()`, `self.pause()`: waits that the "Stop"
  («Стоп») button interrupts;
- `self.ruleReason(conf, name, appid, owned)`: the shared filters;
- `self.ownedGames(conf)`: the Steam library;
- `self.dailyLeft(conf)`, `self.closedFor(conf)`: limits and working hours;
- `self.recordEntry()`, `self.recordWin()`: writing to the history;
- `self.manager.state.seen/markSeen`: what has already been processed;
- `self.info()`, `self.warn()`: the log;
- `self.notify()`: Telegram;
- `self.balance`, `self.account`, `self.waitReason`: what is shown on the
  card.

## Checks

```bash
pip install -r requirements-dev.txt
pytest                                         # all tests, no network and no cookies
ruff check .                                   # linter, as in CI
env/bin/python scripts/build-wiki.py --check   # the wiki tables are not out of date
```

The panel's JavaScript syntax can be checked without Node.js on the server:

```bash
docker run --rm -v "$PWD/steamgiftbot/farm/static":/w:ro node:22-alpine sh -c \
  "sed -n '/<script>/,/<\/script>/p' /w/index.html | sed '1d;\$d' > /tmp/p.js && node --check /tmp/p.js"
```

## Publishing the wiki

The pages of this wiki live in `docs/wiki/`. They can be moved to the GitHub
wiki with a script:

```bash
scripts/publish-wiki.sh
```

The script needs write access to `<repository>.wiki.git`. Deploy keys do not
work for wikis; you need an account SSH key. And the wiki itself has to be
created once on GitHub: the **Wiki → Create the first page** tab.
