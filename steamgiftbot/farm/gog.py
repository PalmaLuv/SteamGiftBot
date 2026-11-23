"""GOG.com giveaways: a few times a month GOG gives a game away from the banner
on its home page. Claiming is the same request the banner button sends:

  GET /userData.json      -> {"isLoggedIn": bool, "username": ...}
  GET /giveaway/claim     -> {} claimed, {"message": "Already claimed"},
                             {"message": "Giveaway has ended"}, 401 signed out

The answer does not name the game, so the name is read off the home page."""
import re
import time

from bs4 import BeautifulSoup

from steamgiftbot.farm.base import (TIMEOUT, AuthError, Platform, PlatformError, RetryLater,
                                    buildSession, cookieGuide, field, grouped, parseCookies,
                                    scheduleFields, userAgentFrom)

BASE   = 'https://www.gog.com'
DOMAIN = '.gog.com'


def giveawayName(html):
    soup = BeautifulSoup(html or '', 'html.parser')
    header = soup.select_one('.giveaway__content-header, [class*="giveaway"] h2')
    text = ' '.join(header.get_text(' ', strip=True).split()) if header else ''
    found = re.search(r'(?:Claim|Success!)\s+(.+?)\s+(?:and don|was added|for free)', text)
    return found.group(1) if found else ''


class GOGPlatform(Platform):
    key         = 'gog'
    unit        = ''
    title       = 'GOG'
    siteURL     = BASE + '/en'
    description = 'Раздачи GOG с главной страницы: игра навсегда остаётся в библиотеке GOG.'
    category    = 'free'

    def schema(self):
        return grouped('Аккаунт', [
            field('cookie', 'Cookie', 'secret',
                  help='gog.com → F12 → Network → F5 → правый клик по первому запросу → '
                       'Copy → Copy as cURL'),
            field('user_agent', 'User-Agent браузера', 'text', '', 'из cURL берётся сам'),
        ]) + grouped('Работа', [
            field('interval', 'Проверять раз в (мин)', 'int', 240,
                  'раздача висит несколько дней, чаще проверять незачем'),
        ]) + scheduleFields()

    def configured(self):
        return bool(self.settings().get('cookie'))

    def guide(self):
        return cookieGuide('GOG', BASE + '/en', page='gog.com', signIn='войдите в аккаунт GOG',
                           extra=[
            {'title': 'Что будет дальше',
             'text': 'Когда на главной GOG появится баннер раздачи, ферма заберёт игру сама — '
                     'так же, как кнопка на баннере. При получении игры GOG может подписать '
                     'аккаунт на рассылку; отписаться можно в настройках аккаунта GOG.'},
        ])

    def connect(self, conf):
        cookies = parseCookies(conf['cookie'])
        if not cookies:
            raise PlatformError("не задан cookie")
        self.session = buildSession(userAgentFrom(conf['cookie']) or conf.get('user_agent'),
                                    cookies, DOMAIN)
        self.session.headers.update({'Referer': BASE + '/', 'Accept': 'application/json'})

    def get(self, path):
        try:
            return self.session.get(BASE + path, timeout=TIMEOUT)
        except Exception as error:
            raise RetryLater(f"GOG недоступен: {error}") from error

    def whoami(self):
        response = self.get('/userData.json')
        try:
            data = response.json()
        except ValueError as error:
            raise RetryLater(f"GOG ответил не JSON (HTTP {response.status_code})") from error
        if not data.get('isLoggedIn'):
            raise AuthError("GOG не узнаёт cookie: войдите на сайт и подключите GOG заново.")
        self.account = data.get('username') or ''
        return data

    def check(self, values):
        conf = self.trialSettings(values)
        if not parseCookies(conf['cookie']):
            raise ValueError("в тексте нет cookie: скопируйте запрос как cURL целиком")
        box = self.sandbox()
        box.connect(conf)
        box.whoami()
        return {'account': box.account, 'balance': None}

    # ('claimed' | 'already' | 'none', words)
    def claim(self):
        response = self.get('/giveaway/claim')
        if response.status_code == 401:
            raise AuthError("GOG просит войти заново: подключите GOG ещё раз.")
        if response.status_code == 404:
            return 'none', 'раздачи сейчас нет'
        try:
            data = response.json()
        except ValueError:
            return 'none', f'непонятный ответ GOG (HTTP {response.status_code})'
        message = (data or {}).get('message') or ''
        if not message and response.ok:
            return 'claimed', 'игра добавлена в библиотеку GOG'
        if 'already' in message.lower():
            return 'already', 'уже получено'
        if 'ended' in message.lower():
            return 'none', 'раздача закончилась'
        return 'none', message or 'раздачи сейчас нет'

    def giveawayTitle(self):
        try:
            return giveawayName(self.get('/en').text)
        except RetryLater:
            return ''

    def preview(self):
        conf = self.settings()
        box = self.sandbox()
        box.connect(conf)
        box.whoami()
        name = box.giveawayTitle()
        items = [{'name': name, 'url': BASE + '/en', 'cost': 0, 'entries': None,
                  'enter': True, 'reason': ''}] if name else []
        note = '' if items else ("Баннера раздачи на главной сейчас не видно. Ферма всё равно "
                                 "попробует забрать игру на каждом проходе.")
        return {'balance': None, 'account': box.account, 'items': items, 'note': note}

    def run(self):
        while not self.stopped:
            conf = self.gate()
            if conf is None:
                return
            self.connect(conf)
            self.whoami()
            kind, words = self.claim()
            if kind == 'claimed':
                name = self.giveawayTitle() or 'Раздача GOG'
                self.recordEntry(name, 0, BASE + '/account')
                self.announceClaims()
                self.finishPass(f"Вошёл: {name} — {words}")
            else:
                self.finishPass(f"GOG: {words}")
            self.lastCycle = time.time()
            if not self.wait(max(30, conf['interval'] or 240) * 60):
                return
