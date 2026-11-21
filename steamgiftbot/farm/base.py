"""What every site in the farm has in common: a worker thread that can be
started, stopped and woken early, a log the web panel can tail, a short history
of what was entered, and settings described well enough to draw a form from."""
import copy
import json
import logging
import random
import re
import shlex
import socket
import threading
import time
import traceback

from contextlib import contextmanager

from collections import deque
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from steamgiftbot.farm import cards, rules
from steamgiftbot.logging_setup import RedactFilter, redactSecrets

# A recent desktop Chrome. Sites behind Incapsula or Cloudflare tie their
# cookies to the browser that earned them, so each site lets the user paste
# their own User-Agent over this one.
DEFAULT_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

TIMEOUT        = 30
LOG_LINES      = 600
DEBUG_LINES    = 1500
HISTORY_LENGTH = 2000

# After an unexpected failure the worker waits this long and tries again.
ERROR_RETRY_SECONDS = 15 * 60

# The first tries after a failure come sooner: at boot the network (DNS) is
# often not up yet, and a flat quarter hour cost every site its first pass.
# Past these steps the worker waits ERROR_RETRY_SECONDS. watch() hears only
# of the first failure and of tries a full ERROR_RETRY_SECONDS apart (see
# retryDelay), so the quick steps do not bring its hourly alert forward.
# Only a site that could not be reached gets them (see networkDown): one that
# answered 429, a Cloudflare or Incapsula check or a 5xx has asked for time,
# and coming back within a minute is what gets a bot blocked.
RETRY_STEPS = (60, 2 * 60, 5 * 60)

# What a network that is not up (yet) looks like: no DNS, refused or dropped
# connections, no answer in time. A RetryError (urllib3 gave up on 429s or
# 5xx) is the site answering, so it is not among them.
NETWORK_ERRORS = (requests.ConnectionError, requests.Timeout,
                  ConnectionError, TimeoutError, socket.gaierror)

# Waits a site picks for itself (for points, 'nothing suits') vary by this
# share either way: the same quarter hour to the second, day and night, is a
# robot's rhythm.
WAIT_JITTER = 0.2

# Failed tries in a row before Telegram hears about it: about an hour.
WATCH_AFTER = 4

# A site that keeps making passes and enters nothing is told once: a day of
# passes, at least IDLE_PASSES of them, without a single entry.
IDLE_ALERT  = 24 * 3600
IDLE_PASSES = 6

# Passes a giveaway may fail for a passing reason before it is given up on,
# and how many such counters a site keeps at most.
FAILED_TRIES = 3
FAILED_KEPT  = 300

STOPPED  = 'stopped'
RUNNING  = 'running'
SLEEPING = 'sleeping'
ERROR    = 'error'
AUTH     = 'auth'      # the cookie no longer works: only the user can fix that


# The session is gone and retrying will not bring it back.
class AuthError(Exception):
    pass


# The site said something the worker cannot carry on from (ban, bad setup).
class PlatformError(Exception):
    pass


# Temporary trouble (site down, Cloudflare check): wait and try again.
class RetryLater(Exception):
    pass


# Whether `error` comes from a network that did not reach the site. Sites
# raise RetryLater from the requests exception they caught, so the cause
# chain tells an outage from a site that answered 'not now'.
def networkDown(error):
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, NETWORK_ERRORS):
            return True
        seen.add(id(error))
        error = error.__cause__
    return False


# One field of a settings form. kind: text, secret, int, bool, select, list,
# hours (working hours like 08:00-23:00) or zone (a time zone name). group
# puts a heading above the first field of each group in the form.
def field(name, label, kind='text', default=None, help='', options=None, group=''):
    return {'name': name, 'label': label, 'kind': kind, 'default': default,
            'help': help, 'options': options or [], 'group': group}


def grouped(group, fields):
    return [{**item, 'group': group} for item in fields]


# Working hours and daily limits: the same on every site.
def scheduleFields():
    return grouped('Расписание и лимиты', [
        field('active_hours', 'Часы работы', 'hours', '',
              'например 08:00-23:00 или 09:00-13:00, 18:00-02:00; пусто — круглосуточно. '
              'Часовой пояс задаётся в настройках фермы'),
        field('daily_entries', 'Макс. входов за сутки', 'int', None, 'пусто — без лимита'),
        field('daily_spend', 'Макс. трат за сутки', 'int', None,
              'в валюте площадки; пусто — без лимита'),
    ])


# Ready-made filters the sites share.
def presetFields():
    return grouped('Фильтры', [
        field('skip_owned', 'Пропускать игры из моей библиотеки Steam', 'bool', False,
              'нужны Steam API-ключ и профиль в настройках фермы'),
        field('skip_junk', 'Пропускать DLC, саундтреки, артбуки, паки', 'bool', False),
        field('skip_adult', 'Пропускать 18+', 'bool', False),
    ])


# ---- connecting a site ---------------------------------------------------------

def cookieGuide(site, url, signIn='войдите в свой аккаунт', page=None, extra=()):
    """The steps the panel shows when a site is connected with browser cookies."""
    page = page or url
    return [
        {'title': f'Войдите на {site}',
         'text': f'Откройте сайт в браузере на компьютере и {signIn}. Оставайтесь в аккаунте: '
                 'если выйти из него в браузере, cookie перестанут работать и подключение '
                 'придётся повторить.',
         'link': url},
        {'title': 'Откройте инструменты разработчика',
         'text': f'Перейдите на страницу {page} и нажмите F12 (на Mac — ⌥⌘I). Откройте '
                 'вкладку Network («Сеть»), затем обновите страницу клавишей F5.'},
        {'title': 'Скопируйте запрос как cURL',
         'text': 'Самый первый запрос в списке — сама страница. Нажмите на него правой кнопкой → '
                 'Copy → Copy as cURL (bash). В Firefox: «Копировать» → «Копировать как cURL '
                 '(POSIX)». В Chrome на Windows можно и «Copy as cURL (cmd)» — ферма поймёт '
                 'оба варианта.'},
        {'title': 'Вставьте и проверьте',
         'text': 'Вставьте скопированное целиком в поле ниже и нажмите «Проверить». Ферма '
                 'возьмёт из текста только cookie и User-Agent браузера; сам текст в панели '
                 'больше не показывается. Cookie дают доступ к аккаунту — никому их не '
                 'пересылайте.'},
        *extra,
    ]


# Ready-made settings. Each site takes the values its own form has.
PRESETS = [
    {'name': 'balanced', 'title': 'Сбалансировано',
     'description': 'Хороший шанс на выигрыш и разумные траты. Подходит большинству.',
     'values': {'skip_junk': True, 'skip_adult': False, 'skip_owned': True, 'sort': 'smart',
                'max_entries': 1000, 'reserve': 5, 'min_points': 50, 'free_only': False}},
    {'name': 'economy', 'title': 'Экономно',
     'description': 'Только раздачи с малым числом участников, запас баланса не трогается.',
     'values': {'skip_junk': True, 'skip_adult': True, 'skip_owned': True, 'sort': 'smart',
                'max_entries': 300, 'reserve': 20, 'min_points': 100, 'free_only': True}},
    {'name': 'maximum', 'title': 'Максимум',
     'description': 'Входить везде, где хватает баланса. Больше входов, но и больше мусора.',
     'values': {'skip_junk': False, 'skip_adult': False, 'skip_owned': False, 'sort': 'expiry',
                'max_entries': None, 'reserve': 0, 'min_points': 10, 'free_only': False,
                'max_pages': 10}},
    {'name': 'games', 'title': 'Только игры',
     'description': 'Пропускать DLC, саундтреки, 18+ и то, что уже есть в библиотеке Steam.',
     'values': {'skip_junk': True, 'skip_adult': True, 'skip_owned': True}},
]


def applySettings(schema, current, incoming):
    """Merges a submitted form into the current values. A secret left empty
    keeps what was there; any bad value aborts the whole save."""
    current = dict(current)
    for item in schema:
        name = item['name']
        if name not in incoming:
            continue
        raw = incoming[name]
        if item['kind'] == 'secret' and (raw is None or raw == '' or raw is True):
            continue
        try:
            current[name] = coerce(item['kind'], raw, item['default'])
        except ValueError as error:
            raise ValueError(f"{item['label']}: {error}") from error
    return current


def publicValues(schema, values):
    values = dict(values)
    for item in schema:
        if item['kind'] == 'secret':
            values[item['name']] = bool(values.get(item['name']))
    return values


def coerce(kind, value, default=None):
    if kind == 'hours':
        return rules.normalizeHours('' if value is None else str(value))
    if kind == 'zone':
        name = '' if value is None else str(value).strip()
        if not name:
            return default
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"нет такого часового пояса «{name}»") from error
        return name
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('1', 'yes', 'true', 'on')
    if kind == 'int':
        if value is None or str(value).strip() == '':
            return default
        number = int(str(value).strip())
        if number < 0:
            raise ValueError("не может быть отрицательным")
        return number
    if kind == 'list':
        if isinstance(value, (list, tuple)):
            items = value
        else:
            items = str(value or '').replace('\n', ',').split(',')
        return [item.strip() for item in items if item.strip()]
    return '' if value is None else str(value).strip()


CURL_START   = re.compile(r'\s*curl(\.exe)?\s', re.I)
HEADER_LINE  = re.compile(r'([A-Za-z0-9-]+)\s*:\s*(.*)')
COOKIE_LINE  = re.compile(r'cookie\s*:', re.I)
COOKIE_LABEL = re.compile(r'cookie\s*(:\s*|\s+)', re.I)

CURL_HEADER  = ('-H', '--header')
CURL_COOKIE  = ('-b', '--cookie')
CURL_AGENT   = ('-A', '--user-agent')


def curlArguments(text):
    """The arguments of a devtools 'Copy as cURL' command, bash or Windows cmd
    flavour; None when the text is not one, [] when it is but will not split."""
    if not CURL_START.match(text):
        return None
    if '^"' in text:
        # cmd escapes every special character with ^, line breaks included.
        text = re.sub(r'\^(.)', r'\1', text, flags=re.S)
    text = text.replace('\\\r\n', ' ').replace('\\\n', ' ')
    try:
        return shlex.split(text)
    except ValueError:
        return []


def curlHeaders(arguments):
    headers, cookies = {}, []
    pending = iter(arguments)
    for argument in pending:
        if argument not in CURL_HEADER + CURL_COOKIE + CURL_AGENT:
            continue
        value = next(pending, '')
        # bash's $'...' quoting, which Chrome uses for unusual characters
        if value.startswith('$'):
            value = value[1:]
        if argument in CURL_COOKIE:
            cookies.append(value)
        elif argument in CURL_AGENT:
            headers['user-agent'] = value
        else:
            name, _, rest = value.partition(':')
            headers[name.strip().lower()] = rest.strip()
    if 'cookie' in headers:
        cookies.append(headers['cookie'])
    if cookies:
        headers['cookie'] = '; '.join(cookies)
    return headers


def pastedHeaders(text):
    """Lower-cased header name → value from a pasted 'Copy as cURL' command or a
    block of request headers; None when the text is neither."""
    text = (text or '').strip()
    arguments = curlArguments(text)
    if arguments is not None:
        return curlHeaders(arguments)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1 and any(COOKIE_LINE.match(line) for line in lines):
        headers = {}
        for line in lines:
            match = HEADER_LINE.fullmatch(line)
            if match:
                headers[match.group(1).lower()] = match.group(2).strip()
        return headers
    return None


def userAgentFrom(text):
    """The browser's User-Agent when the cookie was pasted as a cURL command or
    a headers block, so the two always come from the same browser."""
    return (pastedHeaders(text) or {}).get('user-agent') or None


def cookiesFromJSON(text):
    """Cookie-Editor / EditThisCookie export: a list of {name, value, ...}."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get('cookies'), list):
        data = data['cookies']
    if isinstance(data, dict):
        return {str(name): str(value) for name, value in data.items()
                if isinstance(value, (str, int, float))}
    if isinstance(data, list):
        return {str(item['name']): str(item.get('value', '')) for item in data
                if isinstance(item, dict) and item.get('name')}
    return None


def cookiesFromNetscape(text):
    """cookies.txt: domain, flag, path, secure, expiry, name, value per line."""
    jar = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif line.startswith('#'):
            continue
        columns = line.split('\t')
        if len(columns) >= 7 and columns[5]:
            jar[columns[5]] = columns[6]
    return jar


# Accepts what people actually paste: devtools 'Copy as cURL', the 'Cookie:'
# header or a whole block of request headers, a Cookie-Editor export (JSON or
# cookies.txt), a 'name=value; name=value' list, or a bare value.
def parseCookies(text, bareName=None):
    text = (text or '').strip()
    if not text:
        return {}
    if text[0] in '[{':
        jar = cookiesFromJSON(text)
        if jar is not None:
            return jar
    headers = pastedHeaders(text)
    if headers is not None:
        text = headers.get('cookie', '')
    elif '\t' in text:
        jar = cookiesFromNetscape(text)
        if jar:
            return jar
    label = COOKIE_LABEL.match(text)
    if label:
        text = text[label.end():].strip()
    if not text:
        return {}
    if '=' not in text:
        return {bareName: text} if bareName else {}
    jar = {}
    for part in text.split(';'):
        if '=' not in part:
            continue
        name, value = part.split('=', 1)
        if name.strip():
            jar[name.strip()] = value.strip()
    return jar


# requests refuses .get() when a server re-sets a cookie for a narrower domain
# and two copies end up in the jar. The newest one is the one that counts.
def cookieValue(jar, name):
    found = None
    for cookie in jar:
        if cookie.name == name:
            found = cookie.value
    return found


def buildSession(userAgent, cookies, domain):
    session = requests.Session()
    # GET only: replaying a POST could enter a giveaway twice.
    retry = Retry(total=4, connect=4, read=4, backoff_factor=0.5,
                  status_forcelist=(500, 502, 503, 504), allowed_methods=('GET',))
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': userAgent or DEFAULT_USER_AGENT,
        'Accept-Language': 'en-US,en;q=0.9',
    })
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=domain, path='/')
    return session


# Which site the current thread works for. SteamGiftBot logs through one
# package logger however many SteamGifts accounts run, so each account's
# panel log keeps only the lines its own threads wrote.
ACTING = threading.local()


@contextmanager
def actingFor(platform):
    previous = getattr(ACTING, 'platform', None)
    ACTING.platform = platform
    try:
        yield
    finally:
        ACTING.platform = previous


class OwnLines(logging.Filter):
    """Passes a shared logger's record to one site: the one acting in that
    thread, or the main account when no site is acting (the command line)."""

    def __init__(self, platform):
        super().__init__()
        self.platform = platform

    def filter(self, record):
        owner = getattr(ACTING, 'platform', None)
        return owner is self.platform or (owner is None and self.platform.primary)


class RingHandler(logging.Handler):
    """Keeps the last lines of one site's log for the web panel."""

    def __init__(self, platform):
        super().__init__()
        self.platform = platform
        # The panel shows these lines as they are: mask secrets in error texts
        # here as well, not only in the file and the journal.
        self.addFilter(RedactFilter())

    def emit(self, record):
        try:
            self.platform.addLine(record.levelname, self.format(record),
                                  getattr(record, 'details', None))
        except Exception:
            self.handleError(record)


class Platform:
    key         = ''
    unit        = ''
    title       = ''
    siteURL     = ''
    description = ''
    # For the catalog: 'points' (raffles paid with site currency) or 'free'
    # (games that are free to keep), and what connecting it takes.
    category    = 'points'
    # What connecting the site may cost the account, said before it is
    # connected (the panel shows it in the wizard and on 'Подключение').
    risk        = ''
    needs       = 'cookie'
    # Fields the connect wizard asks for; the rest keep their defaults.
    connectFields = ('cookie',)
    # Whether a second account of this site can be added. Each account is
    # its own instance: key 'steamgifts-2', its own settings, limits, history.
    multiAccount = True

    def __init__(self, manager, key=None):
        self.manager = manager
        self.kind    = type(self).key
        self.key     = key or self.kind
        self.primary = self.key == self.kind
        self.number  = 1 if self.primary else int(self.key.rsplit('-', 1)[1])
        self.baseTitle = type(self).title
        self.title     = self.baseTitle
        self.logger  = logging.getLogger(f'botfarm.{self.key}')
        self.lines   = deque(maxlen=LOG_LINES)
        # Per-giveaway 'why skipped' lines come by the hundred; kept apart so
        # they never push the ordinary log out.
        self.debugLines = deque(maxlen=DEBUG_LINES)
        self.lineSeq = 0
        self.lock    = threading.Lock()

        self.thread  = None
        self.stopFlag = threading.Event()
        self.wakeFlag = threading.Event()

        self.state     = STOPPED
        self.lastError = ''
        self.startedAt = None
        self.lastCycle = None
        self.nextCycle = None
        self.balance   = None
        self.account   = ''
        self.sessionEntered = 0
        self.sessionSpent   = 0
        self.forced = False
        # Why the worker is waiting, in words, for the card in the panel.
        self.waitReason = ''
        self.previewLock = threading.Lock()

        handler = RingHandler(self)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        # DEBUG lines (why each giveaway was skipped) reach the panel's
        # 'Подробно' view only: the file and console handlers stay at INFO.
        self.logger.setLevel(logging.DEBUG)
        self.passStartedAt = None
        self.passClaims = []
        # Failed tries in a row (site or network down); see watch().
        self.failures = 0
        # Where the worker is in RETRY_STEPS, and when the current try began.
        self.retryStep = 0
        self.triedAt = None
        # Its own generator, so a test can put a predictable one in its place.
        self.rng = random.Random()

    # ---- things a site fills in -------------------------------------------

    # The settings form, as a list of field() dicts.
    def schema(self):
        return []

    # Does the work until stopped. Raise AuthError / PlatformError when the
    # site will not let it continue.
    def run(self):
        raise NotImplementedError

    # Called from the web thread when the user presses stop.
    def onStop(self):
        pass

    # What one pass would do right now, entering nothing: {'balance', 'items':
    # [{name, url, cost, entries, enter, reason}], 'note'}.
    def preview(self):
        raise ValueError("пробный проход для этой площадки не поддерживается")

    # Lists the panel may add a game to straight from the history.
    QUICK_LISTS = ('blacklist', 'priority')

    # Told when the user marks a win in the panel ('received', 'activated'
    # or '' to take it back). SteamGifts passes it on to the site.
    def onWinStatus(self, win, status):
        pass

    # Steps of the connect wizard: [{'title', 'text', 'link'?}].
    def guide(self):
        return cookieGuide(self.title, self.siteURL)

    # Tries the given connection values without saving them; returns what the
    # site said about the account ({'account', 'balance'}). Raises on failure.
    def check(self, values):
        raise ValueError("проверка подключения для этой площадки не поддерживается")

    def presets(self):
        names = {item['name'] for item in self.schema()}
        found = []
        for preset in PRESETS:
            values = {key: value for key, value in preset['values'].items() if key in names}
            if values:
                found.append({**preset, 'values': values})
        return found

    def applyPreset(self, name):
        for preset in self.presets():
            if preset['name'] == name:
                self.updateSettings(preset['values'])
                return preset
        raise ValueError("нет такого набора настроек")

    # Forgets the account: stops the site and drops the connection secrets.
    def disconnect(self):
        self.stop(wait=10)
        with self.manager.lock:
            stored = self.manager.platformSettings(self.key)
            for name in self.connectFields:
                stored.pop(name, None)
            self.manager.savePlatformSettings(self.key, stored)
        self.manager.setAutostart(self.key, False)

    # The connection values merged over the saved settings, for check().
    def trialSettings(self, values):
        conf = dict(self.settings())
        schema = {item['name']: item for item in self.schema()}
        for name in self.connectFields:
            if name in (values or {}) and values[name] not in (None, ''):
                item = schema[name]
                conf[name] = coerce(item['kind'], values[name], item['default'])
        return conf

    # ---- settings ----------------------------------------------------------

    def settings(self):
        stored = self.manager.platformSettings(self.key)
        values = {}
        for item in self.schema():
            values[item['name']] = stored.get(item['name'], item['default'])
        return values

    def publicSettings(self):
        return publicValues(self.schema(), self.settings())

    # Read, change and save under the farm's lock, so a change made at the
    # same moment (the panel and a Telegram command) is not written over.
    def updateSettings(self, incoming):
        with self.manager.lock:
            current = applySettings(self.schema(), self.settings(), incoming)
            self.manager.savePlatformSettings(self.key, current)
        return current

    # The settings the schedule and the daily limits are read from.
    def limitSettings(self):
        return self.settings()

    def quickLists(self):
        names = {item['name'] for item in self.schema() if item['kind'] == 'list'}
        return [name for name in self.QUICK_LISTS if name in names]

    # Adds a game name to the blacklist or the priority list. False when it
    # was there already.
    def addToList(self, name, value):
        value = ' '.join(str(value or '').split())
        if name not in self.quickLists():
            raise ValueError("у этой площадки нет такого списка")
        if not value:
            raise ValueError("пустое название")
        # One lock over the read and the write: two words added at once
        # used to each start from the same list, and the second save dropped
        # the first word.
        with self.manager.lock:
            current = list(self.settings().get(name) or [])
            if any(item.lower() == value.lower() for item in current):
                return False
            self.updateSettings({name: current + [value]})
        return True

    # ---- log and history ---------------------------------------------------

    def addLine(self, level, text, details=None, moment=None, restored=False):
        with self.lock:
            self.lineSeq += 1
            line = {'id': self.lineSeq, 'time': moment or time.time(), 'level': level,
                    'text': text}
            if details:
                line['details'] = details
            if restored:
                line['restored'] = True
            (self.debugLines if level == 'DEBUG' else self.lines).append(line)

    # Adds facts to the newest line that mentions `name` (the entry line a
    # site has just written), so the panel can show them under it. Falls back
    # to a line of its own when there is none.
    def attachDetails(self, name, details):
        with self.lock:
            for line in list(self.lines)[-6:][::-1]:
                if name and name in line['text'] and 'details' not in line:
                    line['details'] = details
                    return
        self.logger.debug(f"Подробности: {name}", extra={'details': details})

    def logLines(self, after=0):
        with self.lock:
            lines = [line for line in self.lines if line['id'] > after]
            lines += [line for line in self.debugLines if line['id'] > after]
        return sorted(lines, key=lambda line: line['id'])

    def info(self, text, **details):
        self.logger.info(text, extra={'details': details} if details else None)

    # Only for the panel's 'Подробно' view: one line per skipped giveaway.
    def debug(self, text, **details):
        self.logger.debug(text, extra={'details': details} if details else None)

    # Counts a skipped giveaway for the pass summary and says why, by name,
    # in the 'Подробно' view.
    def skip(self, counter, reason, name, **details):
        counter[reason] += 1
        self.debug(f"Пропуск: {name} — {reason}",
                   **{key: value for key, value in details.items() if value not in (None, '')})

    # 'Проход окончен …' with how long the pass took.
    def finishPass(self, text):
        took = ''
        if self.passStartedAt:
            seconds = int(time.time() - self.passStartedAt)
            took = f" · за {seconds // 60} мин {seconds % 60} с" if seconds >= 60 \
                else f" · за {seconds} с"
        started, self.passStartedAt = self.passStartedAt, None
        self.info(text + took)
        self.recovered()
        self.watchIdle(started)

    # Counts passes in a row that entered nothing (see IDLE_ALERT). Free
    # sources are left out: most of their passes find nothing new, and that
    # is how they work.
    def watchIdle(self, started):
        if self.category != 'points' or started is None:
            return
        state = self.manager.state
        now = time.time()
        idle = dict(state.value(self.key, 'idle') or {})
        if state.usage(self.key, now - started + 1)[0]:
            if idle:
                state.setFlag(self.key, 'idle', {})
            return
        idle['from'] = idle.get('from') or started
        idle['passes'] = idle.get('passes', 0) + 1
        due = (not idle.get('told') and idle['passes'] >= IDLE_PASSES
               and now - idle['from'] >= IDLE_ALERT and not self.idleExplained())
        if due:
            idle['told'] = True
        state.setFlag(self.key, 'idle', idle)
        if due:
            self.tellIdle(now - idle['from'], idle['passes'])

    # True when the site has already said why nothing is entered.
    def idleExplained(self):
        return False

    def tellIdle(self, seconds, passes):
        lines = []
        if self.waitReason:
            lines.append(f"Причина ожидания: {self.waitReason}")
        if self.balance is not None:
            lines.append(f"Баланс: {self.balance} {self.unit}")
        self.notify('\n'.join(lines), '⚠️', title='СТОИТ БЕЗ ВХОДОВ',
                    headline=f"Ни одного входа за {int(seconds // 3600)} ч, проходов: {passes}",
                    note="Проходы идут, но ферма ни во что не входит: проверьте баланс, "
                         "резерв и фильтры. «Что возьмёт» покажет, почему раздачи пропускаются.",
                    buttons=[("Что возьмёт", self.manager.panelLink(f'/site/{self.key}/preview')),
                             ("Настройки", self.manager.panelLink(f'/site/{self.key}/settings'))])

    # A pass went through: if the site had been failing long enough to be
    # reported, say it works again.
    def recovered(self):
        if self.failures >= WATCH_AFTER:
            self.notify('', '✅', title='СНОВА РАБОТАЕТ', headline="Проход прошёл без ошибок.")
        self.failures = 0

    # A failed try. Said once, after about an hour of them; a single blip is
    # not worth a message.
    def watch(self, error):
        self.failures += 1
        if self.failures == WATCH_AFTER:
            minutes = WATCH_AFTER * ERROR_RETRY_SECONDS // 60
            self.notify(str(error), '⚠️', title='НЕ РАБОТАЕТ',
                        headline=f"Не работает уже {minutes} мин",
                        note=f"Ферма пробует снова каждые {ERROR_RETRY_SECONDS // 60} мин.",
                        buttons=[("Журнал", self.manager.panelLink('/journal/log'))])

    # How long to wait before trying again after a failure, counting it for
    # watch() on the way. A new run of trouble starts with the quick steps:
    # after a good pass (recovered() zeroes the failures, as start() does) or
    # after a try that went on long enough to have been working. Only a
    # `quick` failure (the site was not reached) takes them; any other one
    # waits the full time and counts, and so does the rest of its run.
    def retryDelay(self, error, quick=False):
        if self.failures == 0 or (self.triedAt is not None
                                  and time.time() - self.triedAt >= ERROR_RETRY_SECONDS):
            self.retryStep = 0
        if not quick:
            self.retryStep = max(self.retryStep, len(RETRY_STEPS) + 1)
        step = self.retryStep
        self.retryStep += 1
        if step == 0 or step > len(RETRY_STEPS):
            self.watch(error)
        return RETRY_STEPS[step] if step < len(RETRY_STEPS) else ERROR_RETRY_SECONDS

    def warn(self, text):
        self.logger.warning(text)

    def recordEntry(self, name, cost, url='', **extra):
        self.sessionEntered += 1
        self.sessionSpent   += cost or 0
        # What else the site knew (participants, priority) stays in the history.
        kept = {key: value for key, value in extra.items() if value not in (None, '')}
        self.manager.state.addEntry(self.key, {'time': time.time(), 'name': name,
                                               'cost': cost, 'url': url, **kept})
        if not cost:
            self.passClaims.append(name)
        details = {'cost': f"{cost or 0} {self.unit}" if cost else 'бесплатно',
                   'balance': None if self.balance is None else f"{self.balance} {self.unit}",
                   'today': self.manager.state.usage(self.key)[0], 'url': url, **extra}
        self.attachDetails(name, {key: value for key, value in details.items()
                                  if value not in (None, '')})

    # Returns the win's time, which tells it apart later (setWinKey and the like).
    def recordWin(self, name, url=''):
        moment = time.time()
        self.manager.state.addWin(self.key, {'time': moment, 'name': name, 'url': url})
        return moment

    # One look for every message a site sends: a card (see cards.py) with
    # this site's name and code. text gives the plain lines under the headline.
    def notify(self, text='', icon='ℹ️', title='', headline='', link='', note='',
               buttons=None):
        self.manager.notify(card=cards.Card(
            icon, title, self.title, self.key, headline, link,
            [line for line in (text or '').split('\n') if line], note=note,
            buttons=list(buttons or [])))

    # Free games taken this pass, in one message rather than one per game.
    def announceClaims(self):
        names = self.passClaims
        self.passClaims = []
        if not names:
            return
        lines = [f"• {name}" for name in names[:10]]
        if len(names) > 10:
            lines.append(f"…и ещё {len(names) - 10}")
        self.notify('\n'.join(lines), '🎁', headline=f"−100% · забрано игр: {len(names)}",
                    buttons=[("Площадка", self.manager.panelLink(f'/site/{self.key}'))])

    # ---- rules every site shares -------------------------------------------

    # The owned-games list when this site is set to skip them, else None.
    def ownedGames(self, conf):
        return self.manager.ownedGames() if conf.get('skip_owned') else None

    def ruleReason(self, conf, name, appid=None, owned=None):
        reason = rules.presetReason(name, conf.get('skip_junk'), conf.get('skip_adult'))
        if reason:
            return reason
        if conf.get('blacklist') and rules.containsAny(name, conf['blacklist']):
            return 'в чёрном списке'
        if conf.get('whitelist') and not rules.containsAny(name, conf['whitelist']):
            return 'не в белом списке'
        if owned is not None and owned.has(appid, name):
            return 'уже есть в Steam'
        return None

    # (entries, spend) still allowed in the last 24 hours; None = no limit.
    def dailyLeft(self, conf):
        count, spent, _oldest = self.manager.state.usage(self.key)
        entries = conf.get('daily_entries')
        spend = conf.get('daily_spend')
        return (None if entries is None else max(0, entries - count),
                None if spend is None else max(0, spend - spent))

    def limitReached(self, conf):
        entries, spend = self.dailyLeft(conf)
        return entries == 0 or spend == 0

    # When the oldest entry of the last 24 hours drops out of the window.
    def limitResetIn(self):
        oldest = self.manager.state.usage(self.key)[2]
        if oldest is None:
            return 15 * 60
        return int(min(86400, max(300, oldest + 86400 - time.time())))

    def closedFor(self, conf):
        windows = rules.parseHours(conf.get('active_hours') or '')
        return rules.secondsUntilOpen(windows, self.manager.localNow())

    # ---- giveaways that failed for now ---------------------------------------

    # A site's final answer (entered, already in, ended): the giveaway is
    # remembered and never asked about again.
    def settle(self, ident):
        state = self.manager.state
        tries = state.value(self.key, 'tries') or {}
        if ident in tries:
            state.setFlag(self.key, 'tries', {k: v for k, v in tries.items() if k != ident})
        state.markSeen(self.key, ident)

    # A failure that may well pass next time (an HTTP error, an unconfirmed
    # entry, a claim that did not go through). Marking it seen at once would
    # bury the giveaway for good over one hiccup, so it is retried on later
    # passes; after FAILED_TRIES failures it is settled after all, so one that
    # always fails does not cost a request every pass. Returns the tries so far.
    def failedTry(self, ident):
        state = self.manager.state
        tries = dict(state.value(self.key, 'tries') or {})
        count = tries.pop(ident, 0) + 1
        if count >= FAILED_TRIES:
            state.setFlag(self.key, 'tries', tries)
            state.markSeen(self.key, ident)
            return count
        tries[ident] = count
        # Newest last; the oldest counters go first, the flags stay small.
        state.setFlag(self.key, 'tries', dict(list(tries.items())[-FAILED_KEPT:]))
        return count

    def gate(self):
        """Waits out the working hours and the daily limits before a pass and
        returns the settings to run it with; None once stopped. 'Run now'
        lets one pass through regardless."""
        while not self.stopped:
            conf = self.settings()
            if self.forced:
                self.forced = False
                self.passStartedAt = time.time()
                return conf
            closed = self.closedFor(conf)
            if closed:
                opens = self.manager.localNow() + timedelta(seconds=closed)
                self.info(f"Вне часов работы, следующий проход в {opens:%H:%M}.")
                if not self.wait(closed, reason=f"Вне часов работы, откроется в {opens:%H:%M}"):
                    return None
                continue
            if self.limitReached(conf):
                wait = self.limitResetIn()
                resets = self.manager.localNow() + timedelta(seconds=wait)
                self.info(f"Дневной лимит исчерпан, следующий проход через {wait // 60} мин.")
                if not self.wait(wait, reason=f"Дневной лимит исчерпан, сброс в {resets:%H:%M}"):
                    return None
                continue
            self.passStartedAt = time.time()
            return conf
        return None

    def logSkips(self, skipped):
        if skipped:
            parts = ', '.join(f"{reason} — {count}" for reason, count in skipped.most_common())
            self.info(f"Пропущено: {parts}")

    # ---- the worker --------------------------------------------------------

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return False
        self.stopFlag.clear()
        self.wakeFlag.clear()
        self.lastError = ''
        self.state     = RUNNING
        self.startedAt = time.time()
        self.failures = 0
        self.passClaims = []
        self.sessionEntered = 0
        self.sessionSpent   = 0
        self.forced = False
        self.thread = threading.Thread(target=self.loop, name=f'farm-{self.key}', daemon=True)
        self.thread.start()
        return True

    def stop(self, wait=0):
        self.stopFlag.set()
        self.wakeFlag.set()
        try:
            self.onStop()
        except Exception as error:
            self.warn(f"Ошибка при остановке: {error}")
        if wait and self.thread is not None:
            self.thread.join(wait)

    def wakeUp(self):
        self.forced = True
        self.wakeFlag.set()

    @property
    def stopped(self):
        return self.stopFlag.is_set()

    # Sleeps, but returns at once on stop or 'run now'. False means stopped.
    # The wake flag is cleared only after it has woken us: clearing it first
    # would swallow a stop (or 'run now') pressed while a pass was running,
    # and the worker would then sleep through the whole interval.
    def wait(self, seconds, sleeping=True, reason=''):
        if self.stopped:
            return False
        if sleeping and self.forced:
            # 'Run now' is waiting for the next pass; gate() will take it.
            return True
        if sleeping:
            self.state     = SLEEPING
            self.nextCycle = time.time() + seconds
            self.waitReason = reason
        self.wakeFlag.wait(max(0, seconds))
        self.wakeFlag.clear()
        self.nextCycle = None
        if sleeping:
            self.waitReason = ''
        if not self.stopped:
            self.state = RUNNING
        return not self.stopped

    # `seconds`, give or take WAIT_JITTER of it.
    def jittered(self, seconds):
        return max(0, round(seconds * self.rng.uniform(1 - WAIT_JITTER, 1 + WAIT_JITTER)))

    # A short human pause between two entries.
    def pause(self, low=3, high=7):
        return self.wait(random.uniform(low, high), sleeping=False)

    def loop(self):
        ACTING.platform = self
        self.info("Запущено")
        while not self.stopped:
            try:
                self.state = RUNNING
                self.triedAt = time.time()
                self.run()
                break
            except AuthError as error:
                self.state = AUTH
                self.lastError = str(error)
                self.warn(f"Нужна новая авторизация: {error}")
                self.notify(str(error), '🔑', headline="Сессия больше не действует",
                            note="Площадка остановлена до нового подключения.",
                            buttons=[("Подключить заново",
                                      self.manager.panelLink(f'/connect/{self.key}'))])
                return
            except PlatformError as error:
                self.state = ERROR
                self.lastError = str(error)
                self.warn(f"Площадка остановлена: {error}")
                self.notify(str(error), '⛔', headline="Продолжать нельзя",
                            buttons=[("Открыть площадку",
                                      self.manager.panelLink(f'/site/{self.key}'))])
                return
            except RetryLater as error:
                self.state = ERROR
                self.lastError = str(error)
                delay = self.retryDelay(error, quick=networkDown(error))
                self.warn(f"{error} Повтор через {delay // 60} мин.")
                if not self.wait(delay):
                    break
                self.lastError = ''
            except Exception as error:
                self.state = ERROR
                self.lastError = f"{type(error).__name__}: {error}"
                self.logger.error(f"Неожиданная ошибка: {self.lastError}")
                # A bug or a connection a site did not catch: quick, but not
                # when requests carries the site's own answer (urllib3 gave
                # up on its 429s, an HTTP error status).
                delay = self.retryDelay(self.lastError, quick=networkDown(error) or not
                                        isinstance(error, requests.RequestException))
                self.logger.debug(traceback.format_exc())
                for line in traceback.format_exc().strip().splitlines()[-4:]:
                    self.logger.error("  " + line)
                if not self.wait(delay):
                    break
                self.lastError = ''
        self.state = STOPPED
        self.nextCycle = None
        self.waitReason = ''
        self.info("Остановлено")

    # A copy that shares the settings and history but not the worker: its own
    # session and stop flag, so a dry run neither disturbs a pass in progress
    # nor gives up because the site is stopped.
    def sandbox(self):
        clone = copy.copy(self)
        clone.stopFlag = threading.Event()
        clone.wakeFlag = threading.Event()
        return clone

    def previewNote(self, conf):
        closed = self.closedFor(conf)
        if not closed:
            return ''
        opens = self.manager.localNow() + timedelta(seconds=closed)
        return f"Сейчас нерабочие часы: так ферма войдёт, когда они начнутся, в {opens:%H:%M}."

    def runPreview(self):
        if not self.previewLock.acquire(blocking=False):
            raise ValueError("пробный проход уже идёт")
        try:
            with actingFor(self):
                return self.preview()
        finally:
            self.previewLock.release()

    # Today's use of the daily limits and whether the working hours are open.
    def limits(self):
        try:
            conf = self.limitSettings()
        except Exception:
            return None
        count, spent, _oldest = self.manager.state.usage(self.key)
        try:
            closed = self.closedFor(conf)
        except ValueError:
            closed = 0
        opens = None
        if closed:
            opens = (self.manager.localNow() + timedelta(seconds=closed)).strftime('%H:%M')
        return {
            'entries': {'used': count, 'max': conf.get('daily_entries')},
            'spend': {'used': spent, 'max': conf.get('daily_spend')},
            'hours': conf.get('active_hours') or '',
            'opensAt': opens,
        }

    # Called when an added account is removed for good, after disconnect().
    def forget(self):
        pass

    def snapshot(self):
        return {
            'key': self.key, 'title': self.title, 'url': self.siteURL,
            'kind': self.kind, 'baseTitle': self.baseTitle, 'primary': self.primary,
            'multi': self.multiAccount,
            'label': self.manager.platformEntry(self.key).get('label', ''),
            'keyBot': self.manager.keyBotFor(self.key),
            'profile': self.manager.profileOf(self.key),
            'description': self.description,
            'state': self.state, 'error': redactSecrets(self.lastError),
            'balance': self.balance, 'account': self.account,
            'startedAt': self.startedAt, 'lastCycle': self.lastCycle,
            'nextCycle': self.nextCycle, 'reason': self.waitReason,
            'limits': self.limits(), 'lists': self.quickLists(),
            'unit': self.unit, 'category': self.category, 'needs': self.needs,
            'risk': self.risk,
            'sessionEntered': self.sessionEntered, 'sessionSpent': self.sessionSpent,
            'autostart': self.manager.autostart(self.key),
            'totals': self.manager.state.totals(self.key),
            'configured': self.configured(),
        }

    def configured(self):
        return True
