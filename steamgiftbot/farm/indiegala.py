"""IndieGala giveaways: single-ticket raffles for Steam keys, paid for with
Galasilver (iS). Read from the same JSON endpoints the site's own page uses:

  POST /ajax/user/get-data                 -> who is signed in, silver balance
  GET  /giveaways/ajax/<page>/<sort>/<order>/level/<level>
                                           -> {"status": "ok", "html": "..."}
  POST /giveaways/join  {"id": .., "token": ..}
                                           -> {"status": "ok", "silver_tot": N}
                                              or status = silver | level | ...

Wins are not told: a finished giveaway waits in the library under 'Completed
to check' until someone presses 'Check if you won'. The farm presses 'Check
all' and then reads 'Completed won', where the key is:

  POST /library/giveaways/check-if-winner-all
                                           -> {"won": N, "checked": N}
  GET  /library/giveaways/giveaways-completed/won[/<page>]
                                           -> {"status": "ok", "html": "..."}

Every call carries the Django CSRF token from the csrftoken cookie."""
import json
import re
import statistics
import time

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from steamgiftbot.farm import rules
from steamgiftbot.farm.asf import STEAM_KEY, isSteamKey, steamKeys
from steamgiftbot.farm.base import (DEFAULT_USER_AGENT, TIMEOUT, AuthError, Platform,
                                    PlatformError, RetryLater, cookieGuide, cookieValue,
                                    dailyReason, field, grouped, parseCookies, presetFields,
                                    scheduleFields)
from steamgiftbot.farm.sessions import KeptSession
from steamgiftbot.logging_setup import writePrivate

BASE    = 'https://www.indiegala.com'
DOMAIN  = '.indiegala.com'
LISTING = BASE + '/giveaways/ajax/{page}/{sort}/{order}/level/{level}'

JOIN_CALL = re.compile(r"joinGiveawayOrAuction\(\s*this\s*,\s*event\s*,\s*'([^']+)'\s*,"
                       r"\s*(\d+)\s*,\s*'([^']*)'\s*\)")
NUMBER    = re.compile(r'\d[\d,]*')
STEAM_APP = re.compile(r'/steam/apps/(\d+)/')
CARD_ID   = re.compile(r'/giveaways/card/[^/]+/(\d+)')
TIME_LEFT = re.compile(r'(\d+)\s*(second|minute|hour|day|week)', re.IGNORECASE)
MINUTES   = {'second': 1 / 60, 'minute': 1, 'hour': 60, 'day': 1440, 'week': 10080}

# Answers to a join that mean 'do not try this one again'.
FINAL_REFUSALS = {
    'duplicate': 'уже участвуете',
    'level': 'уровень слишком низкий',
    'not_available': 'раздача закончилась',
    'limit_reached': 'лимит участников',
    'owner': 'это ваша раздача',
}

# Marks a giveaway the site refused, as opposed to one we are in.
REFUSED = 'no:'

# What the listing itself can sort by; 'smart' is ours and reads it by expiry.
SITE_SORTS = ['expiry', 'price', 'participants', 'level']
SMART      = 'smart'

# However many pages are full of giveaways already entered, stop here.
MAX_PAGES = 40
SORTS      = [SMART] + SITE_SORTS

# A giveaway's own pace counts once it has been watched this long; before
# that, the typical pace of the others stands in.
PACE_AFTER  = 20 * 60
PACE_KEPT   = 3 * 86400
# Tickets for the same game are counted over this window: one key is enough.
PER_GAME_DAYS = 7

LIBRARY   = BASE + '/library'
WON_LIST  = BASE + '/library/giveaways/giveaways-completed/won'
CHECK_ALL = BASE + '/library/giveaways/check-if-winner-all'
WON_PAGE  = re.compile(r"switchGivSectionPage\([^)]*'giveaways-completed-won'\s*,\s*'(\d+)'")
NO_RESULTS = 'profile-private-page-library-no-results'

# Finished giveaways are checked this often; each check is one 'Check all'.
WIN_CHECK_EVERY = 3 * 3600
# 'Check all' may take one page of the backlog at a time: pressed again while
# it still finds something, up to this many times.
CHECK_ROUNDS = 10
WON_PAGES    = 10


@dataclass
class Ticket:
    id      : str
    token   : str
    name    : str
    price   : int
    entries : int | None
    extraOdds : bool
    url     : str
    appid   : int | None = None
    minutesLeft : float | None = None
    guaranteed  : bool = False
    # Entrants expected by the end (see forecast()); None when unknown.
    expected    : float | None = None

    # Chance of winning per iS spent: fewer people and a cheaper ticket win.
    # People still to come count too, when the farm has seen how fast this
    # giveaway, or a typical one, fills up.
    @property
    def value(self):
        people = self.expected if self.expected is not None else (self.entries or 0)
        return 1 / ((people + 1) * max(1, self.price))


def minutesLeft(text):
    found = TIME_LEFT.search(text or '')
    if not found:
        return None
    return int(found.group(1)) * MINUTES[found.group(2).lower()]


def parseListing(html):
    soup = BeautifulSoup(html, 'html.parser')
    tickets = []
    for item in soup.find_all('div', class_='items-list-item'):
        click = item.find('a', class_='items-list-item-ticket-click')
        call  = JOIN_CALL.search(click.get('onclick', '')) if click else None
        if not call:
            continue
        title  = item.find(class_='items-list-item-title')
        link   = title.find('a', href=True) if title else None
        button = item.find(class_='items-list-item-data-button')
        priceTag = button.find('a') if button else None
        price = priceTag.get('data-price') if priceTag else None
        if price is None and priceTag is not None:
            found = NUMBER.search(priceTag.get_text())
            price = found.group(0) if found else None
        try:
            price = int(str(price).replace(',', ''))
        except (TypeError, ValueError):
            continue
        sold = item.find(class_='items-list-item-data-right-bottom')
        found = NUMBER.search(sold.get_text()) if sold else None
        image = item.find('img', attrs={'data-img-src': True}) or item.find('img', src=True)
        source = (image.get('data-img-src') or image.get('src') or '') if image else ''
        app = STEAM_APP.search(source)
        left = item.find(class_='items-list-item-data-left-bottom')
        kind = item.find(class_='items-list-item-type')
        kindClasses = kind.get('class', []) if kind is not None else []
        tickets.append(Ticket(
            id      = call.group(1),
            token   = call.group(3),
            name    = (link.get_text(strip=True) if link else call.group(1)),
            price   = price,
            entries = int(found.group(0).replace(',', '')) if found else None,
            extraOdds = call.group(2) != '0',
            url     = BASE + link['href'] if link else BASE + '/giveaways',
            appid   = int(app.group(1)) if app else None,
            minutesLeft = minutesLeft(left.get_text(' ', strip=True)) if left else None,
            guaranteed  = kind is not None and 'items-list-item-type-not-guaranteed'
                          not in kindClasses,
        ))
    return tickets


@dataclass
class Won:
    id     : str
    name   : str
    url    : str
    serial : str = ''      # a Steam key, a gift link or another code, as given


# Rows of 'Completed won'. The key sits in the row's text box, the same one
# 'Check if you won' fills in; failing that, a key or a gift link in the row.
def parseWon(html):
    soup = BeautifulSoup(html, 'html.parser')
    found = {}
    for row in soup.select('li.profile-private-sub-section-body'):
        link = row.find('a', href=CARD_ID)
        if link is None:
            continue
        ident = CARD_ID.search(link['href']).group(1)
        url = link['href'] if link['href'].startswith('http') else BASE + link['href']
        serial = ''
        for box in row.find_all(['input', 'textarea']):
            value = (box.get('value') or box.get_text() or '').strip()
            if value:
                serial = value
                break
        if not serial:
            serial = ' '.join(dict.fromkeys(
                m.group(0) for m in STEAM_KEY.finditer(row.get_text(' ', strip=True))
                if isSteamKey(m.group(0))))
        if not serial:
            gifts = [a['href'] for a in row.find_all('a', href=True)
                     if a is not link and a['href'].startswith('http')
                     and re.search(r'gift|key|serial', a['href'], re.IGNORECASE)]
            serial = gifts[0] if gifts else ''
        found.setdefault(ident, Won(ident, link.get_text(strip=True) or ident, url, serial))
    return list(found.values())


def wonPages(html):
    return max([int(number) for number in WON_PAGE.findall(html)] or [1])


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def lastPage(html):
    pages = [int(number) for number in re.findall(r'/giveaways/ajax/(\d+)/', html)]
    return max(pages) if pages else 1


class IndieGalaPlatform(KeptSession, Platform):
    key         = 'indiegala'
    unit        = 'iS'
    title       = 'IndieGala'
    siteURL     = BASE + '/giveaways'
    description = 'Раздачи ключей за Galasilver (iS).'
    sessionDomain = DOMAIN
    # IndieGala's own sign-in cookie and Django's session.
    signInCookie  = re.compile(r'auth|sessionid', re.IGNORECASE)

    def schema(self):
        return grouped('Аккаунт', [
            field('cookie', 'Cookie', 'secret',
                  help='indiegala.com/giveaways → F12 → Network → F5 → правый клик по первому '
                       'запросу → Copy → Copy as cURL, вставить целиком. Подойдёт и экспорт '
                       'Cookie-Editor или строка Cookie'),
            field('user_agent', 'User-Agent браузера', 'text', DEFAULT_USER_AGENT,
                  'из cURL берётся сам; иначе — того же браузера, откуда cookie'),
            field('level', 'Ваш уровень на IndieGala', 'int', 0,
                  'показываются только раздачи этого уровня'),
            field('check_wins', 'Проверять выигрыши', 'bool', True,
                  'раз в 3 часа ферма жмёт «Check all» в библиотеке IndieGala и '
                  'сохраняет ключи выигрышей'),
        ]) + grouped('Баланс и приоритеты', [
            field('reserve', 'Не опускать баланс ниже (iS)', 'int', 0),
            field('priority', 'Приоритетные игры', 'list', [],
                  'слова через запятую: в эти раздачи ферма входит первой'),
            field('priority_reserve', 'На приоритетные можно тратить резерв', 'bool', True),
        ]) + grouped('Что брать', [
            field('min_price', 'Мин. цена билета (iS)', 'int', None,
                  'дешёвые билеты — обычно дешёвые игры; пусто — любые'),
            field('max_price', 'Макс. цена билета (iS)', 'int', None, 'пусто — любая'),
            field('max_entries', 'Макс. участников', 'int', None,
                  'пропускать раздачи с большим числом участников'),
            field('max_hours_left', 'Только кончающиеся в ближайшие N часов', 'int', None,
                  'к концу раздачи понятно, сколько будет соперников; пусто — любые'),
            # Off by default: a ticket rarely wins, so one more for the same game
            # is worth almost as much as one for another game, and a limit sent
            # the iS to crowded giveaways instead (16 iS on 2141 entrants).
            field('max_per_game', 'Билетов на одну игру', 'int', None,
                  'сколько раздач одной и той же игры брать за 7 дней, если важнее '
                  'разнообразие. Билет выигрывает редко, так что лимит обычно уводит iS в '
                  'раздачи похуже. Пусто — без лимита; приоритетных игр не касается'),
            field('extra_odds', 'Брать доп. билеты (extra odds)', 'bool', False,
                  'повторные билеты в ту же раздачу'),
            field('whitelist', 'Белый список', 'list', [], 'если задан — только эти игры'),
            field('blacklist', 'Чёрный список', 'list', [], 'слова через запятую'),
        ]) + presetFields() + grouped('Порядок обхода', [
            field('sort', 'Порядок', 'select', SMART, options=SORTS,
                  help='smart — сначала лучший шанс за iS (мало участников, дешёвый '
                       'билет); expiry — сначала заканчивающиеся; price, participants, '
                       'level — как на сайте'),
            field('max_pages', 'Страниц за проход', 'int', 5,
                  'считаются только страницы с новыми раздачами'),
            field('interval', 'Пауза между проходами (мин)', 'int', 60),
        ]) + scheduleFields()

    def configured(self):
        return bool(self.settings().get('cookie'))

    def guide(self):
        return cookieGuide('IndieGala', self.siteURL, page='indiegala.com/giveaways',
                           signIn='войдите в аккаунт (Login справа вверху)', extra=[
            {'title': 'Укажите уровень',
             'text': 'Уровень аккаунта IndieGala виден в профиле. Раздачи выше вашего уровня '
                     'сайт не даёт, поэтому после подключения поставьте его в настройках '
                     '(«Ваш уровень на IndieGala»). У нового аккаунта уровень 0.'},
            {'title': 'Откуда берутся iS',
             'text': 'Galasilver (iS) начисляется за покупки и ежедневные награды на IndieGala. '
                     'Когда iS закончатся, ферма подождёт и продолжит сама.'},
        ])

    def check(self, values):
        conf = self.trialSettings(values)
        if not parseCookies(conf['cookie']):
            raise ValueError("в тексте нет cookie: скопируйте запрос как cURL целиком")
        box = self.sandbox()
        box.connect(conf)
        box.userData()
        return {'account': box.account, 'balance': box.balance}

    # ---- talking to the site ---------------------------------------------

    # The session of the last pass while the paste is the same (see sessions.py).
    def connect(self, conf):
        if self.openSession(conf):
            self.session.headers.update({'Referer': BASE + '/giveaways', 'Origin': BASE})

    def csrfHeaders(self):
        token = cookieValue(self.session.cookies, 'csrftoken') or ''
        return {'X-CSRFToken': token, 'X-CSRF-Token': token,
                'X-Requested-With': 'XMLHttpRequest'}

    def request(self, method, url, **kwargs):
        try:
            response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
        except Exception as error:
            raise RetryLater(f"IndieGala недоступна: {error}") from error
        if response.status_code in (403, 503) and 'incapsula' in response.text.lower():
            raise RetryLater("IndieGala показала проверку Incapsula. Обновите cookie из "
                             "браузера и укажите его User-Agent.")
        if response.status_code == 429:
            raise RetryLater("IndieGala просит притормозить (HTTP 429).")
        if response.status_code >= 500:
            raise RetryLater(f"IndieGala ответила HTTP {response.status_code}.")
        return response

    def readJSON(self, response, what):
        try:
            return response.json()
        except ValueError as error:
            raise RetryLater(f"IndieGala вернула не JSON на {what} "
                             f"(HTTP {response.status_code}).") from error

    def userData(self):
        # The page itself hands out a fresh csrftoken when the cookie lacks one.
        if not cookieValue(self.session.cookies, 'csrftoken'):
            self.request('GET', BASE + '/giveaways')
        response = self.request('POST', BASE + '/ajax/user/get-data',
                                headers={**self.csrfHeaders(),
                                         'Content-Type': 'application/json'})
        data = self.readJSON(response, 'данные пользователя')
        if not data.get('user_is_logged'):
            raise AuthError("IndieGala не узнаёт cookie: войдите на сайт и вставьте cookie заново.")
        user = data.get('current_user') or {}
        self.account = user.get('username') or ''
        try:
            self.balance = int(data.get('silver_coins_tot'))
        except (TypeError, ValueError):
            self.balance = None
        return data

    def listing(self, conf, page):
        sort = conf['sort'] if conf['sort'] in SITE_SORTS else 'expiry'
        url = LISTING.format(page=page, sort=sort, order='asc',
                             level=conf['level'] if conf['level'] is not None else 'all')
        response = self.request('GET', url, headers=self.csrfHeaders())
        data = self.readJSON(response, 'список раздач')
        if data.get('status') != 'ok':
            raise RetryLater("IndieGala не отдала список раздач (высокая нагрузка), "
                             "попробую позже.")
        html = data.get('html') or ''
        # Giveaways already entered have no join button and do not parse, so a
        # page can be full and still give no tickets: only a page with no
        # giveaways at all is the end of the list.
        return parseListing(html), lastPage(html), html.count('items-list-item"')

    def join(self, ticket):
        response = self.request('POST', BASE + '/giveaways/join',
                                data=json.dumps({'id': ticket.id, 'token': ticket.token}),
                                headers={**self.csrfHeaders(),
                                         'Content-Type': 'application/json'})
        data = self.readJSON(response, 'вход в раздачу')
        return data.get('status'), data

    # ---- wins ----------------------------------------------------------------

    def libraryCall(self, method, url, what):
        headers = self.csrfHeaders()
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
        data = self.readJSON(self.request(method, url, headers=headers), what)
        if not isinstance(data, dict):
            raise RetryLater(f"IndieGala ответила непонятно на {what}.")
        if data.get('status') == 'login':
            raise AuthError("IndieGala просит войти заново.")
        if data.get('status') == 'banned':
            raise PlatformError("аккаунт IndieGala заблокирован для раздач.")
        return data

    def wonPage(self, page=1):
        url = WON_LIST if page == 1 else f"{WON_LIST}/{page}"
        data = self.libraryCall('GET', url, 'список выигрышей')
        if data.get('status') != 'ok':
            raise RetryLater("IndieGala не отдала список выигрышей, попробую позже.")
        return data.get('html') or ''

    def wonList(self):
        html = self.wonPage()
        found = {win.id: win for win in parseWon(html)}
        for page in range(2, min(wonPages(html), WON_PAGES) + 1):
            if self.stopped:
                break
            for win in parseWon(self.wonPage(page)):
                found.setdefault(win.id, win)
        if not found and NO_RESULTS not in html:
            self.keepForDebugging('won', html)
            self.debug("Список выигрышей IndieGala не разобран: копия сохранена в debug/")
        return list(found.values())

    def keepForDebugging(self, name, html):
        try:
            folder = Path(self.manager.dataDir) / 'debug'
            folder.mkdir(parents=True, exist_ok=True)
            # A signed-in page: it may hold won keys.
            writePrivate(folder / f'{self.key}-{name}.html', html)
        except OSError:
            pass

    def winsDue(self):
        last = self.manager.state.value(self.key, 'wins_checked_at') or 0
        return time.time() - last >= WIN_CHECK_EVERY

    # 'Check all', then whatever is new on 'Completed won'. The first look
    # only learns what was won before, so old keys are not announced.
    def checkWins(self):
        state = self.manager.state
        known = set(state.value(self.key, 'won_ids', []) or [])
        if not state.flag(self.key, 'wins_seeded'):
            known |= {win.id for win in self.wonList()}
            state.setFlag(self.key, 'won_ids', sorted(known))
            state.setFlag(self.key, 'wins_seeded')
        checked = won = 0
        for _round in range(CHECK_ROUNDS):
            data = self.libraryCall('POST', CHECK_ALL, 'проверку выигрышей')
            if not number(data.get('checked')):
                break
            checked += number(data.get('checked'))
            won += number(data.get('won'))
            if self.stopped or not self.pause(1, 2):
                break
        if checked:
            self.info(f"Проверено законченных раздач: {checked}, выигрышей: {won}")
        fresh = [win for win in self.wonList() if win.id not in known]
        for win in fresh:
            known.add(win.id)
            state.setFlag(self.key, 'won_ids', sorted(known))
            self.tellWin(win)
        state.setFlag(self.key, 'wins_checked_at', time.time())
        return fresh

    # The card never shows the key itself: it goes to the panel's 'Выигрыши'.
    def tellWin(self, win):
        self.info(f"Выигрыш на IndieGala: {win.name}")
        moment = self.recordWin(win.name, win.url)
        if not win.serial:
            note = "Ключ — в библиотеке IndieGala: Giveaways → Completed won."
        elif steamKeys(win.serial) and self.manager.farmSettings().get('auto_redeem'):
            note = "Ключ сохранён в разделе «Выигрыши», ферма отправит его в ASF."
        else:
            note = "Ключ сохранён в разделе «Выигрыши» панели."
        # The key is saved after the card (with auto_redeem that sends it to
        # ASF, whose answer should come second), so say whether there is one.
        self.notify('', '🎉', headline=win.name, link=win.url, note=note,
                    buttons=[("Выигрыши", self.manager.panelLink('/wins')),
                             ("Библиотека IndieGala", LIBRARY)],
                    actions=self.manager.winActions(self.key, moment, win.name,
                                                    steamKey=bool(steamKeys(win.serial or ''))))
        if win.serial:
            try:
                self.manager.setWinKey(self.key, moment, win.name, win.serial)
            except Exception as error:
                self.warn(f"Ключ к «{win.name}» не сохранён: {error}")

    # ---- one pass ----------------------------------------------------------

    def skipReason(self, conf, ticket, seen, owned=None):
        if REFUSED + ticket.id in seen:
            return 'сайт уже отказал'
        # Extra-odds raffles take more than one ticket; the rest only one.
        if ticket.id in seen and not (conf['extra_odds'] and ticket.extraOdds):
            return 'уже участвуете'
        if conf['min_price'] is not None and ticket.price < conf['min_price']:
            return 'дешевле минимума'
        if conf['max_price'] is not None and ticket.price > conf['max_price']:
            return 'дороже лимита'
        if (conf['max_entries'] is not None and ticket.entries is not None
                and ticket.entries > conf['max_entries']):
            return 'слишком много участников'
        if (conf['max_hours_left'] is not None and ticket.minutesLeft is not None
                and ticket.minutesLeft > conf['max_hours_left'] * 60):
            return 'кончается не скоро'
        if (conf.get('max_per_game') and not self.isPriority(conf, ticket)
                and self.ticketsFor(ticket) >= conf['max_per_game']):
            return 'хватит билетов на эту игру'
        return self.ruleReason(conf, ticket.name, ticket.appid, owned)

    # ---- tickets per game ----------------------------------------------------

    @staticmethod
    def gameOf(ticket_or_name):
        name = getattr(ticket_or_name, 'name', ticket_or_name)
        return rules.normalizeTitle(name)

    # Tickets bought for each game over PER_GAME_DAYS, from the history.
    def countTickets(self):
        since = time.time() - PER_GAME_DAYS * 86400
        entries = self.manager.state.history(self.key, limit=100000)['entries']
        self.perGame = Counter(self.gameOf(entry['name']) for entry in entries
                               if entry['time'] > since)

    def ticketsFor(self, ticket):
        return getattr(self, 'perGame', Counter())[self.gameOf(ticket)]

    def boughtFor(self, ticket):
        self.perGame = getattr(self, 'perGame', Counter())
        self.perGame[self.gameOf(ticket)] += 1

    # ---- forecast ------------------------------------------------------------

    # Entrants a giveaway will have by its end: its own pace (people per
    # minute since the farm first saw it) or, until that is known, the
    # median pace of the giveaways that are, times the minutes left.
    def forecast(self, tickets, now=None):
        now = now or time.time()
        sightings = {ident: seen for ident, seen in getattr(self, 'sightings', {}).items()
                     if now - seen[0] < PACE_KEPT}
        paces = {}
        for ticket in tickets:
            if ticket.entries is None:
                continue
            first = sightings.setdefault(ticket.id, (now, ticket.entries))
            if now - first[0] >= PACE_AFTER:
                paces[ticket.id] = max(0, ticket.entries - first[1]) / ((now - first[0]) / 60)
        typical = statistics.median(paces.values()) if paces else None
        for ticket in tickets:
            pace = paces.get(ticket.id, typical)
            if ticket.entries is not None and ticket.minutesLeft is not None and pace is not None:
                ticket.expected = ticket.entries + pace * ticket.minutesLeft
        self.sightings = sightings

    def isPriority(self, conf, ticket):
        wished = getattr(self, 'wished', None)
        if wished and ticket.appid in wished:
            return True
        return bool(conf['priority']) and rules.containsAny(ticket.name, conf['priority'])

    # Every page first, then the order the settings ask for: priority games at
    # the front, and in 'smart' mode the best chance per iS next. Only pages
    # with something new count towards 'pages per pass': the ones already
    # entered pile up at the front of the list.
    def collect(self, conf, seen=frozenset()):
        self.wished = self.manager.wishlist()
        found, page, pages, useful = {}, 1, 1, 0
        wanted = max(1, conf['max_pages'] or 1)
        while page <= min(pages, MAX_PAGES) and useful < wanted and not self.stopped:
            tickets, pages, items = self.listing(conf, page)
            if not items:
                break
            fresh = [ticket for ticket in tickets if ticket.id not in seen
                     or (conf['extra_odds'] and ticket.extraOdds)]
            if fresh:
                useful += 1
            for ticket in tickets:
                found.setdefault(ticket.id, ticket)
            page += 1
        tickets = list(found.values())
        if conf['sort'] == SMART:
            self.forecast(tickets)
            tickets.sort(key=lambda t: (-t.value, t.minutesLeft if t.minutesLeft is not None
                                        else float('inf')))
        return sorted(tickets, key=lambda t: not self.isPriority(conf, t))

    def cycle(self, conf):
        self.userData()
        self.info(f"Аккаунт {self.account or '?'}, баланс {self.balance} iS")
        seen = self.manager.state.seen(self.key)
        owned = self.ownedGames(conf)
        self.countTickets()
        skipped = Counter()
        entered = 0
        for ticket in self.collect(conf, seen):
            if self.stopped:
                break
            facts = {'cost': f"{ticket.price} iS", 'entries': ticket.entries, 'url': ticket.url}
            reason = self.skipReason(conf, ticket, seen, owned)
            if reason:
                self.skip(skipped, reason, ticket.name, **facts)
                continue
            entriesLeft, spendLeft = self.dailyLeft(conf)
            if entriesLeft == 0:
                self.info("Дневной лимит входов исчерпан.")
                break
            if spendLeft is not None and ticket.price > spendLeft:
                self.skip(skipped, 'дневной лимит трат', ticket.name, **facts)
                continue
            if self.closedFor(conf):
                self.info("Часы работы закончились.")
                break
            priority = self.isPriority(conf, ticket)
            reserve = 0 if priority and conf['priority_reserve'] else (conf['reserve'] or 0)
            if self.balance is not None:
                if self.balance <= 0:
                    break
                if self.balance - ticket.price < reserve:
                    self.skip(skipped, 'не хватает iS', ticket.name, **facts)
                    continue
            status, data = self.join(ticket)
            if status == 'ok':
                entered += 1
                try:
                    self.balance = int(data.get('silver_tot'))
                except (TypeError, ValueError):
                    self.balance = (self.balance or ticket.price) - ticket.price
                seen.add(ticket.id)
                self.manager.state.markSeen(self.key, ticket.id)
                self.info(f"Вошёл: {'★ ' if priority else ''}{ticket.name} за {ticket.price} iS "
                          f"(участников {ticket.entries if ticket.entries is not None else '?'}, "
                          f"осталось {self.balance})")
                self.boughtFor(ticket)
                self.recordEntry(ticket.name, ticket.price, ticket.url, entries=ticket.entries,
                                 expected=(round(ticket.expected) if ticket.expected is not None
                                           else None),
                                 priority='да' if priority else None)
                if not self.pause():
                    break
            elif status == 'silver':
                self.info("Сайт говорит, что silver не хватает. Проход окончен.")
                break
            elif status == 'too_fast':
                self.warn("Слишком частые запросы, пауза 2 минуты.")
                if not self.wait(120, sleeping=False):
                    break
            elif status == 'login':
                raise AuthError("IndieGala просит войти заново.")
            elif status == 'banned':
                raise PlatformError("аккаунт IndieGala заблокирован для раздач.")
            elif status in FINAL_REFUSALS:
                seen.add(REFUSED + ticket.id)
                self.manager.state.markSeen(self.key, REFUSED + ticket.id)
                self.info(f"Пропуск {ticket.name}: {FINAL_REFUSALS[status]}")
                self.pause(1, 2)
            else:
                self.warn(f"Неожиданный ответ на {ticket.name}: {data}")
                self.pause(1, 2)
        self.logSkips(skipped)
        if self.balance is not None and self.balance <= (conf['reserve'] or 0):
            self.info(f"Silver закончился ({self.balance} iS).")
        return entered

    # Balance and the daily limits, for a ticket that passed every filter.
    @staticmethod
    def budgetReason(conf, ticket, priority, balance, entriesLeft, spendLeft):
        reason = dailyReason(ticket.price, entriesLeft, spendLeft)
        if reason:
            return reason
        reserve = 0 if priority and conf['priority_reserve'] else (conf['reserve'] or 0)
        if balance is not None and (balance <= 0 or balance - ticket.price < reserve):
            return 'не хватает iS'
        return None

    def preview(self):
        conf = self.settings()
        if not conf.get('cookie'):
            raise ValueError("сначала вставьте cookie в настройках")
        box = self.sandbox()
        box.connect(conf)
        box.userData()
        seen = self.manager.state.seen(self.key)
        owned = self.ownedGames(conf)
        balance = box.balance
        entriesLeft, spendLeft = self.dailyLeft(conf)
        box.countTickets()
        items = []
        for ticket in box.collect(conf, seen):
            priority = box.isPriority(conf, ticket)
            reason = (box.skipReason(conf, ticket, seen, owned)
                      or self.budgetReason(conf, ticket, priority, balance,
                                           entriesLeft, spendLeft))
            if reason is None:
                box.boughtFor(ticket)
                if balance is not None:
                    balance -= ticket.price
                if entriesLeft is not None:
                    entriesLeft -= 1
                if spendLeft is not None:
                    spendLeft -= ticket.price
            items.append({'name': ticket.name, 'url': ticket.url, 'cost': ticket.price,
                          'entries': ticket.entries, 'priority': priority,
                          'minutesLeft': ticket.minutesLeft,
                          'expected': (round(ticket.expected) if ticket.expected is not None
                                       else None),
                          'enter': reason is None, 'reason': reason or ''})
        return {'balance': box.balance, 'account': box.account, 'items': items,
                'note': self.previewNote(conf)}

    def run(self):
        while not self.stopped:
            conf = self.gate()
            if conf is None:
                return
            self.connect(conf)
            with self.keptPass():
                entered = self.cycle(conf)
                if conf['check_wins'] and not self.stopped and self.winsDue():
                    try:
                        self.checkWins()
                    except RetryLater as error:
                        self.warn(f"Выигрыши не проверены: {error}")
            self.remindExpiry()
            self.lastCycle = time.time()
            self.finishPass(f"Проход окончен: вошёл в {entered}, баланс {self.balance} iS")
            reason = ''
            if self.balance is not None and self.balance <= (conf['reserve'] or 0):
                reason = f"Закончился iS ({self.balance}), ждёт пополнения"
            if not self.wait(max(5, conf['interval'] or 60) * 60, reason=reason):
                return
