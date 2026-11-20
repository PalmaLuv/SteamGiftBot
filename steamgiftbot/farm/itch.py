"""itch.io: games put on a 100% sale, claimed into the itch.io library.

Which games are free right now comes from the ItchClaim list (the same project
whose claim flow this follows); each one is checked on itch.io itself before
claiming, since the list can lag a sale's end:

  GET  {game}/data.json              -> {"price": "$0.00", "sale": {"rate": 100}}
  POST {game}/download_url  {csrf_token}  -> {"url": <download page>}
  GET  <download page>; POST its claim form with csrf_token

The session is the 'itchio' cookie; the CSRF token is the 'itchio_token' one."""
import time

from urllib.parse import unquote

from bs4 import BeautifulSoup

from steamgiftbot.farm.base import (TIMEOUT, AuthError, Platform, PlatformError, RetryLater,
                                    buildSession, cookieGuide, cookieValue, field, grouped,
                                    parseCookies, presetFields, scheduleFields, userAgentFrom)
from steamgiftbot.farm.rules import containsAny, presetReason

BASE    = 'https://itch.io'
DOMAIN  = '.itch.io'
ACTIVE  = 'https://itchclaim.tmbpeter.com/api/active.json'
LIBRARY = BASE + '/my-purchases'


def activeSales(data, now=None):
    """[(id, name, url)] of claimable games whose sale is on now."""
    now = now or time.time()
    found = []
    for game in data or []:
        if not game.get('claimable') or not game.get('url'):
            continue
        if any((sale.get('start') or 0) <= now < (sale.get('end') or now + 1)
               for sale in game.get('sales') or [{}]):
            found.append((str(game.get('id')), game.get('name') or game['url'], game['url']))
    return found


class ItchPlatform(Platform):
    key         = 'itch'
    unit        = ''
    title       = 'itch.io'
    siteURL     = BASE + '/games/on-sale'
    description = ('Игры, которые авторы раздают со скидкой 100%: ферма добавляет их в '
                   'библиотеку itch.io.')
    category    = 'free'

    def schema(self):
        return grouped('Аккаунт', [
            field('cookie', 'Cookie', 'secret',
                  help='itch.io → F12 → Network → F5 → правый клик по первому запросу → '
                       'Copy → Copy as cURL'),
            field('user_agent', 'User-Agent браузера', 'text', '', 'из cURL берётся сам'),
        ]) + grouped('Что брать', [
            field('per_pass', 'Не больше за проход', 'int', 15,
                  'itch.io быстро отвечает «слишком часто», лучше понемногу'),
            field('whitelist', 'Белый список', 'list', [], 'если задан — только эти'),
            field('blacklist', 'Чёрный список', 'list', [], 'слова через запятую'),
        ]) + presetFields() + grouped('Работа', [
            field('interval', 'Пауза между проходами (мин)', 'int', 120),
        ]) + scheduleFields()

    def configured(self):
        return bool(self.settings().get('cookie'))

    def guide(self):
        return cookieGuide('itch.io', BASE + '/login', page='itch.io/my-purchases',
                           signIn='войдите в аккаунт itch.io', extra=[
            {'title': 'Что будет дальше',
             'text': 'Ферма раз в пару часов берёт список игр со скидкой 100% и забирает их по '
                     'несколько штук за проход. Это в основном инди и ассеты; лишнее отсекают '
                     'чёрный список и фильтры. Игры появятся в «My library» на itch.io.'},
        ])

    def connect(self, conf):
        cookies = parseCookies(conf['cookie'])
        if not cookies.get('itchio'):
            raise PlatformError("в cookie нет itchio: войдите на itch.io и скопируйте запрос "
                                "заново")
        self.session = buildSession(userAgentFrom(conf['cookie']) or conf.get('user_agent'),
                                    cookies, DOMAIN)

    def csrf(self):
        return unquote(cookieValue(self.session.cookies, 'itchio_token') or '')

    def request(self, method, url, **kwargs):
        try:
            response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
        except Exception as error:
            raise RetryLater(f"itch.io недоступен: {error}") from error
        if response.status_code == 429:
            raise RetryLater("itch.io просит притормозить (HTTP 429).")
        return response

    def whoami(self):
        response = self.request('GET', LIBRARY + '?format=json')
        if '/login' in response.url or response.status_code in (401, 403):
            raise AuthError("itch.io не узнаёт cookie: войдите на сайт и подключите заново.")
        return True

    def check(self, values):
        conf = self.trialSettings(values)
        box = self.sandbox()
        try:
            box.connect(conf)
        except PlatformError as error:
            raise ValueError(str(error)) from error
        box.whoami()
        return {'account': '', 'balance': None}

    def active(self):
        response = self.request('GET', ACTIVE)
        try:
            return activeSales(response.json())
        except ValueError as error:
            raise RetryLater("список раздач itch.io недоступен") from error

    def skipReason(self, conf, name, seen, ident):
        if ident in seen:
            return 'уже в библиотеке'
        reason = presetReason(name, conf.get('skip_junk'), conf.get('skip_adult'))
        if reason:
            return reason
        if conf.get('blacklist') and containsAny(name, conf['blacklist']):
            return 'в чёрном списке'
        if conf.get('whitelist') and not containsAny(name, conf['whitelist']):
            return 'не в белом списке'
        return None

    def stillFree(self, url):
        response = self.request('GET', url.rstrip('/') + '/data.json')
        try:
            data = response.json()
        except ValueError:
            return False
        sale = data.get('sale') or {}
        return sale.get('rate') == 100 or str(data.get('price', '')).strip('$0.') == ''

    # True when the game ended up in the library.
    def claim(self, url):
        token = self.csrf()
        response = self.request('POST', url.rstrip('/') + '/download_url',
                                json={'csrf_token': token})
        try:
            target = response.json().get('url')
        except ValueError:
            target = None
        if not target:
            return False
        page = self.request('GET', target)
        form = BeautifulSoup(page.text, 'html.parser').select_one(
            'div.claim_to_download_box form')
        if form is None:
            # Already owned: the download page has no claim box.
            return 'download' in page.url
        done = self.request('POST', form.get('action'), data={'csrf_token': token})
        return done.url.rstrip('/') != BASE

    def plan(self, conf):
        seen = self.manager.state.seen(self.key)
        items = []
        for ident, name, url in self.active():
            items.append((ident, name, url, self.skipReason(conf, name, seen, ident)))
        return items

    def preview(self):
        conf = self.settings()
        box = self.sandbox()
        box.connect(conf)
        box.whoami()
        limit, taken, items = max(1, conf['per_pass'] or 15), 0, []
        for _ident, name, url, reason in box.plan(conf):
            if reason is None and taken >= limit:
                reason = 'в следующий проход'
            taken += reason is None
            items.append({'name': name, 'url': url, 'cost': 0, 'entries': None,
                          'enter': reason is None, 'reason': reason or ''})
        items.sort(key=lambda item: not item['enter'])
        return {'balance': None, 'account': '', 'items': items, 'note': ''}

    def cycle(self, conf):
        state = self.manager.state
        limit, claimed = max(1, conf['per_pass'] or 15), 0
        for ident, name, url, reason in self.plan(conf):
            if self.stopped or claimed >= limit:
                break
            if reason:
                continue
            if not self.stillFree(url):
                state.markSeen(self.key, ident)
                continue
            if self.claim(url):
                claimed += 1
                state.markSeen(self.key, ident)
                self.info(f"Вошёл: {name} — добавлено в библиотеку itch.io")
                self.recordEntry(name, 0, url)
            else:
                self.info(f"Не получилось забрать {name}")
                state.markSeen(self.key, ident)
            if not self.pause(6, 12):
                break
        return claimed

    def run(self):
        while not self.stopped:
            conf = self.gate()
            if conf is None:
                return
            self.connect(conf)
            self.whoami()
            claimed = self.cycle(conf)
            self.lastCycle = time.time()
            self.finishPass(f"Проход окончен: забрано {claimed}")
            if not self.wait(max(30, conf['interval'] or 120) * 60):
                return

