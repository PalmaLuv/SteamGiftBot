"""The web panel: one page plus a small JSON API, on the standard library so
the farm needs nothing beyond what the bot already installs.

Signing in sets an HttpOnly, SameSite=Strict cookie holding an expiry and an
HMAC of it; changing the password changes the key, which signs everyone out.
Every POST must also carry X-Requested-With, which a plain cross-site form
cannot send."""
import hashlib
import hmac
import json
import logging
import re
import threading
import time

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from steamgiftbot.farm.base import AuthError, PlatformError, RetryLater
from steamgiftbot.farm.manager import FARM_FIELDS

COOKIE_NAME     = 'botfarm_session'
SESSION_SECONDS = 30 * 86400
STATIC_DIR      = Path(__file__).resolve().parent / 'static'

log = logging.getLogger('botfarm')

PROFILE_ROUTE = re.compile(r'^/api/profiles/(?P<id>[a-z0-9]{1,12})/(?P<action>update|delete)$')
ROUTE = re.compile(r'^/api/platforms/(?P<key>[a-z]+(?:-[0-9]{1,3})?)/(?P<action>[a-z-]+)$')

# Files the page may load besides itself; everything else is 404.
STATIC_FILES = {
    'manifest.webmanifest': 'application/manifest+json',
    'sw.js': 'text/javascript; charset=utf-8',
    'icon.svg': 'image/svg+xml',
    'icon-192.png': 'image/png',
    'icon-512.png': 'image/png',
    # The panel's translations (scripts/i18n.py); Russian is the page itself.
    'i18n/en.json': 'application/json; charset=utf-8',
    'i18n/uk.json': 'application/json; charset=utf-8',
}


def makeToken(secret, expires=None):
    expires = int(expires or time.time() + SESSION_SECONDS)
    signature = hmac.new(secret.encode(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def tokenValid(secret, token):
    try:
        expires, signature = token.split('.', 1)
        if int(expires) < time.time():
            return False
    except (ValueError, AttributeError):
        return False
    expected = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class Handler(BaseHTTPRequestHandler):
    server_version = 'BotFarm'
    manager = None            # set by serve()
    failedLogins = {}
    loginLock = threading.Lock()

    def log_message(self, format, *args):
        pass

    # ---- plumbing ----------------------------------------------------------

    def send(self, status, body=b'', contentType='application/json; charset=utf-8',
             headers=None):
        self.send_response(status)
        self.send_header('Content-Type', contentType)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, data, status=HTTPStatus.OK, headers=None):
        self.send(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), headers=headers)

    def error(self, message, status=HTTPStatus.BAD_REQUEST):
        self.json({'error': message}, status)

    def body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > 1_000_000:
            raise ValueError("слишком большой запрос")
        raw = self.rfile.read(length) if length else b'{}'
        try:
            data = json.loads(raw or b'{}')
        except ValueError as error:
            raise ValueError("ожидался JSON") from error
        if not isinstance(data, dict):
            raise ValueError("ожидался JSON-объект")
        return data

    def signedIn(self):
        cookie = SimpleCookie(self.headers.get('Cookie') or '')
        morsel = cookie.get(COOKIE_NAME)
        return morsel is not None and tokenValid(self.manager.sessionSecret(), morsel.value)

    def sessionCookie(self, token, maxAge):
        return (f"{COOKIE_NAME}={token}; Path=/; Max-Age={maxAge}; HttpOnly; "
                "SameSite=Strict")

    # ---- GET ---------------------------------------------------------------

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ('/', '/index.html'):
            page = (STATIC_DIR / 'index.html').read_bytes()
            return self.send(HTTPStatus.OK, page, 'text/html; charset=utf-8',
                             {'Content-Security-Policy':
                              "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                              "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                              "frame-ancestors 'none'"})
        name = url.path.lstrip('/')
        if name in STATIC_FILES:
            # The service worker must come from the root to control the page.
            return self.send(HTTPStatus.OK, (STATIC_DIR / name).read_bytes(), STATIC_FILES[name],
                             {'Cache-Control': 'no-cache'} if name == 'sw.js' else None)
        if url.path == '/api/session':
            return self.json({'signedIn': self.signedIn(),
                              'hasPassword': self.manager.hasPassword(),
                              'ui': self.manager.uiSettings()})
        if not url.path.startswith('/api/'):
            return self.error('не найдено', HTTPStatus.NOT_FOUND)
        if not self.signedIn():
            return self.error('нужно войти', HTTPStatus.UNAUTHORIZED)

        query = parse_qs(url.query)
        if url.path == '/api/status':
            return self.json({'platforms': [platform.snapshot() for platform
                                            in self.manager.platforms.values()],
                              'wins': self.manager.openWins(),
                              'profiles': self.manager.publicProfiles(),
                              'time': time.time()})

        if url.path in ('/api/history', '/api/history.csv'):
            pick = {name: (query.get(name) or [''])[0] for name in ('kind', 'site', 'q')}
            kind = pick['kind'] or 'entries'
            try:
                if url.path.endswith('.csv'):
                    body = self.manager.historyCSV(kind, pick['site'], pick['q']).encode('utf-8')
                    return self.send(HTTPStatus.OK, body, 'text/csv; charset=utf-8',
                                     {'Content-Disposition':
                                      f'attachment; filename="botfarm-{kind}.csv"'})
                page = int((query.get('page') or ['1'])[0] or 1)
                per = int((query.get('per') or ['50'])[0] or 50)
                return self.json(self.manager.historyPage(kind, pick['site'], pick['q'],
                                                          page, per))
            except ValueError as error:
                return self.error(str(error))

        if url.path == '/api/summary':
            try:
                days = int((query.get('days') or ['30'])[0])
            except ValueError:
                days = 30
            return self.json(self.manager.summary(days))

        if url.path == '/api/farm/settings':
            return self.json({'schema': FARM_FIELDS, 'values': self.manager.publicFarmSettings(),
                              'info': self.manager.settingsInfo()})

        found = ROUTE.match(url.path)
        platform = self.manager.platforms.get(found['key']) if found else None
        if platform is None:
            return self.error('не найдено', HTTPStatus.NOT_FOUND)
        if found['action'] == 'logs':
            after = int((query.get('after') or ['0'])[0] or 0)
            return self.json({'lines': platform.logLines(after)})
        if found['action'] == 'settings':
            try:
                values = platform.publicSettings()
            except PlatformError as error:
                return self.error(str(error))
            return self.json({'schema': platform.schema(),
                              'values': values,
                              'autostart': self.manager.autostart(platform.key),
                              'guide': platform.guide(),
                              'connectFields': list(platform.connectFields),
                              'presets': platform.presets()})
        if found['action'] == 'history':
            return self.json({**self.manager.state.history(platform.key),
                              'lists': platform.quickLists()})
        return self.error('не найдено', HTTPStatus.NOT_FOUND)

    def do_HEAD(self):
        self.do_GET()

    # ---- POST --------------------------------------------------------------

    def do_POST(self):
        url = urlparse(self.path)
        if self.headers.get('X-Requested-With') != 'BotFarm':
            return self.error('запрос отклонён', HTTPStatus.FORBIDDEN)
        try:
            data = self.body()
        except ValueError as error:
            return self.error(str(error))

        if url.path == '/api/login':
            return self.login(data)
        if url.path == '/api/logout':
            return self.json({'ok': True},
                             headers={'Set-Cookie': self.sessionCookie('', 0)})
        if not self.signedIn():
            return self.error('нужно войти', HTTPStatus.UNAUTHORIZED)

        try:
            return self.action(url.path, data)
        except (ValueError, PlatformError) as error:
            # PlatformError here is a broken config.ini: say so, do not 500.
            return self.error(str(error))
        except Exception as error:
            log.exception("Ошибка в веб-панели")
            return self.error(f"{type(error).__name__}: {error}",
                              HTTPStatus.INTERNAL_SERVER_ERROR)

    def login(self, data):
        address = self.client_address[0]
        with self.loginLock:
            recent = [moment for moment in self.failedLogins.get(address, [])
                      if moment > time.time() - 600]
            self.failedLogins[address] = recent
        if len(recent) >= 10:
            return self.error('слишком много попыток, подождите 10 минут',
                              HTTPStatus.TOO_MANY_REQUESTS)
        password = str(data.get('password') or '')
        if not self.manager.hasPassword():
            return self.error('пароль панели не задан: python -m steamgiftbot.farm --set-password',
                              HTTPStatus.FORBIDDEN)
        if not self.manager.checkPassword(password):
            with self.loginLock:
                self.failedLogins.setdefault(address, []).append(time.time())
            time.sleep(1)
            return self.error('неверный пароль', HTTPStatus.UNAUTHORIZED)
        token = makeToken(self.manager.sessionSecret())
        return self.json({'ok': True},
                         headers={'Set-Cookie': self.sessionCookie(token, SESSION_SECONDS)})

    def action(self, path, data):
        manager = self.manager
        if path == '/api/ui':
            return self.json({'ui': manager.updateUi(data.get('values') or {})})
        if path == '/api/start-all':
            started = [key for key, platform in manager.platforms.items()
                       if platform.configured() and platform.start()]
            return self.json({'started': started})
        if path == '/api/stop-all':
            for platform in manager.platforms.values():
                platform.stop()
            return self.json({'ok': True})
        if path == '/api/notify-test':
            problems = manager.notify("✅ Бот-ферма на связи: это тестовое сообщение из панели.")
            if problems:
                raise ValueError('; '.join(problems))
            return self.json({'ok': True})
        if path == '/api/farm/settings':
            manager.updateFarmSettings(data.get('values') or {})
            return self.json({'ok': True})
        if path == '/api/telegram/chats':
            return self.json({'chats': manager.telegramChats(data.get('token'))})
        if path == '/api/steam/check':
            return self.json({'ok': True, 'message': manager.steamCheck()})
        if path == '/api/logout-all':
            manager.logoutEverywhere()
            token = makeToken(manager.sessionSecret())
            return self.json({'ok': True, 'message': 'Все остальные устройства вышли из панели'},
                             headers={'Set-Cookie': self.sessionCookie(token, SESSION_SECONDS)})
        if path == '/api/accounts/add':
            try:
                platform, found = manager.addAccount(str(data.get('kind') or ''),
                                                     data.get('values') or {},
                                                     str(data.get('profile') or 'main'))
            except (AuthError, PlatformError, RetryLater) as error:
                raise ValueError(str(error)) from error
            return self.json({'ok': True, 'key': platform.key, 'title': platform.title,
                              'account': found.get('account') or '',
                              'balance': found.get('balance')})
        if path == '/api/profiles/create':
            item = manager.createProfile(data.get('name'), data.get('asfBot') or '')
            return self.json({'ok': True, 'id': item['id'], 'name': item['name']})
        found = PROFILE_ROUTE.match(path)
        if found and found['action'] == 'update':
            item = manager.updateProfile(found['id'], name=data.get('name'),
                                         asfBot=data.get('asfBot'))
            return self.json({'ok': True, 'name': item['name']})
        if found and found['action'] == 'delete':
            manager.deleteProfile(found['id'])
            return self.json({'ok': True})
        if path == '/api/asf/check':
            found = manager.asf.check()
            online = ', '.join(found['online']) or 'ни одного'
            return self.json({'ok': True, 'message': f"ASF на связи. Ботов: {len(found['bots'])}, "
                                                      f"в сети: {online}",
                              'bots': found['bots'], 'online': found['online']})
        if path == '/api/farm/report':
            problems = manager.notify(manager.report())
            if problems:
                raise ValueError('; '.join(problems))
            return self.json({'ok': True})
        if path == '/api/password':
            if not manager.checkPassword(str(data.get('current') or '')):
                raise ValueError('текущий пароль неверен')
            manager.setPassword(str(data.get('new') or ''))
            token = makeToken(manager.sessionSecret())
            return self.json({'ok': True},
                             headers={'Set-Cookie': self.sessionCookie(token, SESSION_SECONDS)})

        found = ROUTE.match(path)
        platform = manager.platforms.get(found['key']) if found else None
        if platform is None:
            return self.error('не найдено', HTTPStatus.NOT_FOUND)
        action = found['action']
        if action == 'start':
            if not platform.configured():
                raise ValueError('сначала заполните настройки (cookie)')
            return self.json({'started': platform.start()})
        if action == 'stop':
            platform.stop()
            return self.json({'ok': True})
        if action == 'restart':
            platform.stop(wait=15)
            return self.json({'started': platform.start()})
        if action == 'run-now':
            platform.wakeUp()
            return self.json({'ok': True})
        if action == 'autostart':
            manager.setAutostart(platform.key, bool(data.get('value')))
            return self.json({'ok': True})
        if action == 'settings':
            platform.updateSettings(data.get('values') or {})
            if data.get('connect'):
                manager.platformEntry(platform.key)['connected'] = True
                manager.saveFarm()
                manager.retitle()
            if 'autostart' in data:
                manager.setAutostart(platform.key, bool(data['autostart']))
            return self.json({'ok': True, 'restarted': self.reloadSettings(platform)})
        if action == 'list':
            added = platform.addToList(str(data.get('list') or ''), data.get('value'))
            return self.json({'added': added,
                              'restarted': self.reloadSettings(platform) if added else False})
        if action == 'win':
            moment, name = data.get('time') or 0, str(data.get('name') or '')
            if 'key' in data:
                return self.json({'ok': True,
                                  'key': manager.setWinKey(platform.key, moment, name,
                                                           data['key'])})
            status = str(data.get('status') or '')
            if not manager.state.setWinStatus(platform.key, moment, name, status):
                raise ValueError("выигрыш не найден")
            win = manager.state.findWin(platform.key, moment, name)
            platform.onWinStatus(win, status)
            return self.json({'ok': True})
        if action == 'redeem':
            kind, words = manager.redeemWin(platform.key, data.get('time') or 0,
                                            str(data.get('name') or ''))
            return self.json({'ok': kind in ('ok', 'owned'), 'message': words})
        if action == 'check':
            try:
                found = manager.checkAccount(platform, data.get('values') or {})
            except (AuthError, PlatformError, RetryLater) as error:
                raise ValueError(str(error)) from error
            manager.rememberAccount(platform, found)
            return self.json({'ok': True, **found})
        if action == 'remove':
            manager.removeAccount(platform.key)
            return self.json({'ok': True})
        if action == 'label':
            return self.json({'ok': True,
                              'title': manager.renameAccount(platform.key, data.get('label'))})
        if action == 'key-bot':
            manager.setKeyBot(platform.key, data.get('bot'))
            return self.json({'ok': True})
        if action == 'preset':
            preset = platform.applyPreset(str(data.get('name') or ''))
            return self.json({'ok': True, 'title': preset['title'],
                              'restarted': self.reloadSettings(platform)})
        if action == 'disconnect':
            platform.disconnect()
            manager.retitle()
            return self.json({'ok': True})
        if action == 'preview':
            try:
                return self.json(platform.runPreview())
            except (AuthError, PlatformError, RetryLater) as error:
                raise ValueError(str(error)) from error
        return self.error('не найдено', HTTPStatus.NOT_FOUND)


    # SteamGifts reads its settings once per start; the others every pass.
    @staticmethod
    def reloadSettings(platform):
        if platform.kind == 'steamgifts' and platform.running:
            platform.stop(wait=15)
            return platform.start()
        return False


def serve(manager, host, port):
    Handler.manager = manager
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
