"""OpiumPulses giveaways: raffles for Steam keys, many of them free, the rest
paid for with OP points earned on the site.

The listing is only filled in for a signed-in visitor, and its markup is not
documented, so the parser looks for meaning rather than exact classes: a block
per giveaway, a link that enters it, a price in points or the word 'free'.
When a page does not look like that, it is saved under debug/ so the parser can
be adjusted to what the site really sends."""
import re
import time

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

from steamgiftbot.farm.base import (DEFAULT_USER_AGENT, TIMEOUT, AuthError, Platform,
                                    PlatformError, RetryLater, buildSession, cookieGuide, field,
                                    grouped, parseCookies, presetFields, scheduleFields,
                                    userAgentFrom)

BASE     = 'https://www.opiumpulses.com'
DOMAIN   = '.opiumpulses.com'
LISTING  = BASE + '/giveaways'
WON_KEYS = BASE + '/user/giveawaykeys'

ITEM_CLASS  = re.compile(r'giveaways-page-item(?![-\w])')
ENTER_HREF  = re.compile(r'/giveaways?/(enter|join|participate)', re.IGNORECASE)
POINTS_TEXT = re.compile(r'(\d[\d,]*)\s*(?:op\b|points?|pts)', re.IGNORECASE)
FREE_TEXT   = re.compile(r'\bfree\b', re.IGNORECASE)
ENTERED     = re.compile(r'\b(entered|joined)\b', re.IGNORECASE)
PAGE_PARAM  = 'Giveaway_page'
NO_POINTS   = 'не хватает поинтов'
ENTER_PATHS = tuple(f'/{base}/{verb}' for base in ('giveaway', 'giveaways')
                    for verb in ('enter', 'join', 'participate'))


@dataclass
class OpGiveaway:
    id      : str
    name    : str
    cost    : int
    enterURL: str | None
    entered : bool
    url     : str


def textOf(tag):
    return tag.get_text(' ', strip=True) if tag is not None else ''


def isSignedIn(html):
    # A visitor's page has no logout link anywhere; a member's always does.
    return 'logout' in html.lower()


def parseBalance(soup):
    # The header shows the balance next to the user menu; look there first.
    for tag in soup.find_all(class_=re.compile(r'points', re.IGNORECASE)):
        found = POINTS_TEXT.search(textOf(tag)) or re.search(r'(\d[\d,]*)', textOf(tag))
        if found:
            return int(found.group(1).replace(',', ''))
    header = soup.find('header') or soup
    found = POINTS_TEXT.search(textOf(header))
    return int(found.group(1).replace(',', '')) if found else None


def nameOf(item):
    for selector in (re.compile(r'name|title', re.IGNORECASE),):
        tag = item.find(class_=selector)
        if tag is not None and textOf(tag):
            return textOf(tag)
    image = item.find('img', alt=True)
    if image is not None and image['alt'].strip():
        return image['alt'].strip()
    return textOf(item)[:60] or 'giveaway'


def costOf(item):
    for tag in item.find_all(class_=re.compile(r'points|price|cost', re.IGNORECASE)):
        text = textOf(tag)
        if FREE_TEXT.search(text):
            return 0
        found = POINTS_TEXT.search(text) or re.search(r'(\d[\d,]*)', text)
        if found:
            return int(found.group(1).replace(',', ''))
    text = textOf(item)
    found = POINTS_TEXT.search(text)
    if found:
        return int(found.group(1).replace(',', ''))
    return 0 if FREE_TEXT.search(text) else None


def parseListing(html, pageURL=LISTING):
    soup = BeautifulSoup(html, 'html.parser')
    giveaways = []
    for item in soup.find_all(class_=ITEM_CLASS):
        enter = None
        for link in item.find_all('a', href=True):
            if ENTER_HREF.search(link['href']):
                enter = link
                break
        if enter is None:
            enter = item.find('a', class_=re.compile(r'enter', re.IGNORECASE), href=True)
        detail = item.find('a', href=re.compile(r'/giveaway/'))
        entered = bool(ENTERED.search(textOf(enter) if enter else '')) or \
            any(ENTERED.search(name) for name in item.get('class', []))
        cost = costOf(item)
        if cost is None:
            continue
        enterURL = urljoin(pageURL, enter['href']) if enter is not None else None
        ident = (enterURL or (urljoin(pageURL, detail['href']) if detail else nameOf(item)))
        giveaways.append(OpGiveaway(
            id=ident.rstrip('/').rsplit('/', 1)[-1].split('?')[0] or ident,
            name=nameOf(item), cost=cost, enterURL=enterURL,
            entered=entered or (enter is None and 'entered' in textOf(item).lower()),
            url=urljoin(pageURL, detail['href']) if detail else LISTING,
        ))
    return giveaways, soup


PLACEHOLDER = re.compile(r'no (results|keys|data|records|items)|nothing (found|here)|empty',
                         re.IGNORECASE)


# (id, name) of one row on 'my giveaway keys', or None for the 'No results
# found.' row an empty table carries. The id comes from a link when the row
# has one: the row's text changes once a key is revealed, the link does not.
def wonRow(row):
    cells = row.find_all(['td', 'th'])
    text = textOf(row)
    if not text or PLACEHOLDER.search(text) and len(cells) <= 1:
        return None
    if any(cell.get('colspan') for cell in cells) and len(cells) == 1:
        return None
    if 'empty' in ' '.join(row.get('class', []) + [c for cell in cells
                                                   for c in cell.get('class', [])]):
        return None
    link = row.find('a', href=True)
    name = textOf(cells[0]) if cells else text
    ident = link['href'] if link is not None else text[:120]
    return ident, (name or text)[:120]


def nextPageURL(soup, pageURL):
    link = soup.find('a', rel='next') or soup.select_one('li.next a[href], .next a[href]')
    if link is None or not link.get('href'):
        return None
    target = urljoin(pageURL, link['href'])
    return None if target == pageURL else target


class OpiumPulsesPlatform(Platform):
    key         = 'opiumpulses'
    unit        = 'OP'
    title       = 'OpiumPulses'
    siteURL     = LISTING
    description = 'Раздачи ключей: бесплатные и за OP-поинты.'

    def schema(self):
        return grouped('Аккаунт', [
            field('cookie', 'Cookie', 'secret',
                  help='opiumpulses.com/giveaways → F12 → Network → F5 → правый клик по первому '
                       'запросу → Copy → Copy as cURL, вставить целиком. Подойдёт и экспорт '
                       'Cookie-Editor или строка Cookie'),
            field('user_agent', 'User-Agent браузера', 'text', DEFAULT_USER_AGENT,
                  'из cURL берётся сам; иначе — того же браузера, откуда cookie'),
        ]) + grouped('Что брать', [
            field('free_only', 'Только бесплатные', 'bool', False),
            field('reserve', 'Не опускать баланс ниже (OP)', 'int', 0),
            field('max_cost', 'Макс. цена (OP)', 'int', None, 'пусто — любая'),
            field('whitelist', 'Белый список', 'list', [], 'если задан — только эти игры'),
            field('blacklist', 'Чёрный список', 'list', [], 'слова через запятую'),
        ]) + presetFields() + grouped('Работа', [
            field('max_pages', 'Страниц за проход', 'int', 5),
            field('check_wins', 'Следить за выигранными ключами', 'bool', True),
            field('interval', 'Пауза между проходами (мин)', 'int', 120),
        ]) + scheduleFields()

    def configured(self):
        return bool(self.settings().get('cookie'))

    def guide(self):
        return cookieGuide('OpiumPulses', LISTING, page='opiumpulses.com/giveaways',
                           signIn='войдите через Steam (Sign in через Steam справа вверху)',
                           extra=[
            {'title': 'Бесплатные и платные раздачи',
             'text': 'Часть раздач бесплатна, остальные — за OP, которые сайт начисляет за '
                     'активность. По умолчанию ферма берёт и те, и другие, пока хватает OP; '
                     'чтобы брать только бесплатные, включите «Только бесплатные» в '
                     'настройках или выберите набор «Экономно».'},
        ])

    def check(self, values):
        conf = self.trialSettings(values)
        if not parseCookies(conf['cookie']):
            raise ValueError("в тексте нет cookie: скопируйте запрос как cURL целиком")
        box = self.sandbox()
        box.connect(conf)
        response = box.get(LISTING)
        if not isSignedIn(response.text):
            raise AuthError("OpiumPulses не узнаёт эти cookie: войдите на сайт и скопируйте "
                            "запрос заново.")
        soup = BeautifulSoup(response.text, 'html.parser')
        return {'account': '', 'balance': parseBalance(soup)}

    def debugDir(self):
        return Path(self.manager.dataDir) / 'debug'

    def keepForDebugging(self, name, html):
        try:
            folder = self.debugDir()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'opiumpulses-{name}.html').write_text(html, encoding='utf-8')
        except OSError:
            pass

    def connect(self, conf):
        cookies = parseCookies(conf['cookie'])
        if not cookies:
            raise PlatformError("не задан cookie")
        self.session = buildSession(userAgentFrom(conf['cookie']) or conf['user_agent'],
                                    cookies, DOMAIN)
        self.session.headers.update({'Referer': LISTING})
        # Entering is a GET, and the shared adapter repeats GETs after a read
        # timeout: a repeat could enter twice, or come back 'already entered'
        # and hide a paid entry from the limits. No repeats for these paths.
        for path in ENTER_PATHS:
            self.session.mount(BASE + path, HTTPAdapter(max_retries=0))

    def get(self, url):
        try:
            response = self.session.get(url, timeout=TIMEOUT)
        except Exception as error:
            raise RetryLater(f"OpiumPulses недоступен: {error}") from error
        if response.status_code == 429:
            raise RetryLater("OpiumPulses просит притормозить (HTTP 429).")
        if response.status_code >= 500 or response.status_code == 403:
            raise RetryLater(f"OpiumPulses ответил HTTP {response.status_code}.")
        return response

    def skipReason(self, conf, giveaway, seen, owned=None):
        if giveaway.entered or giveaway.id in seen:
            return 'уже участвуете'
        if giveaway.enterURL is None:
            return 'нет кнопки входа'
        if conf['free_only'] and giveaway.cost > 0:
            return 'платная'
        if conf['max_cost'] is not None and giveaway.cost > conf['max_cost']:
            return 'дороже лимита'
        if giveaway.cost > 0 and self.balance is not None and \
                self.balance - giveaway.cost < (conf['reserve'] or 0):
            return 'не хватает поинтов'
        return self.ruleReason(conf, giveaway.name, owned=owned)

    # Only an answer that says so counts as an entry. The old rule (anything
    # without an error phrase is a success) logged ended giveaways and 404s
    # as entries and charged their price to the daily limits.
    def enter(self, giveaway):
        response = self.get(giveaway.enterURL)
        if 'site/login' in response.url.lower():
            raise AuthError("OpiumPulses отправил на страницу входа: обновите cookie.")
        if response.status_code != 200:
            return False, f'сайт ответил HTTP {response.status_code}'
        body = response.text.lower()
        for phrase in ('not enough points', 'insufficient', "don't have enough"):
            if phrase in body:
                return False, NO_POINTS
        for phrase in ('already entered', 'already joined'):
            if phrase in body:
                return False, 'уже участвуете'
        # Exact phrases only: the listing we are sent back to has 'ended' and
        # 'expired' in its own filter menu.
        for phrase in ('giveaway has ended', 'this giveaway ended', 'no longer available'):
            if phrase in body:
                return False, 'раздача закончилась'
        for phrase in ('successfully entered', 'you have entered', 'you entered',
                       'entry confirmed', 'good luck'):
            if phrase in body:
                return True, ''
        # The site usually sends us back to the listing: there the giveaway
        # shows up as entered.
        listed, _soup = parseListing(response.text, response.url)
        for item in listed:
            if item.id == giveaway.id:
                if item.entered:
                    return True, ''
                break
        self.keepForDebugging('enter-unconfirmed', response.text)
        return False, 'вход не подтверждён (страница сохранена в debug/)'

    def cycle(self, conf):
        response = self.get(LISTING)
        if not isSignedIn(response.text):
            raise AuthError("OpiumPulses не узнаёт cookie: войдите на сайт "
                            "и вставьте cookie заново.")
        url, html = response.url, response.text
        seen = self.manager.state.seen(self.key)
        owned = self.ownedGames(conf)
        skipped = Counter()
        entered = 0
        for page in range(1, max(1, conf['max_pages'] or 1) + 1):
            giveaways, soup = parseListing(html, url)
            balance = parseBalance(soup)
            if balance is not None:
                self.balance = balance
            if page == 1:
                self.info(f"Баланс: {self.balance if self.balance is not None else '?'} OP, "
                          f"раздач на странице: {len(giveaways)}")
                if not giveaways:
                    self.keepForDebugging('giveaways', html)
                    if soup.find(class_=re.compile('giveaways-page-items')) is None:
                        self.warn("Страница раздач выглядит не так, как ожидалось; "
                                  "копия сохранена в debug/ для разбора.")
            for giveaway in giveaways:
                if self.stopped:
                    break
                facts = {'cost': f"{giveaway.cost} OP" if giveaway.cost else 'бесплатно',
                         'url': giveaway.url}
                reason = self.skipReason(conf, giveaway, seen, owned)
                if reason:
                    self.skip(skipped, reason, giveaway.name, **facts)
                    continue
                entriesLeft, spendLeft = self.dailyLeft(conf)
                if entriesLeft == 0 or self.closedFor(conf):
                    self.info("Дневной лимит или часы работы закончились.")
                    self.logSkips(skipped)
                    return entered
                if spendLeft is not None and giveaway.cost > spendLeft:
                    self.skip(skipped, 'дневной лимит трат', giveaway.name, **facts)
                    continue
                ok, reason = self.enter(giveaway)
                # Short of points is the one refusal worth another try later.
                if ok or reason != NO_POINTS:
                    seen.add(giveaway.id)
                    self.manager.state.markSeen(self.key, giveaway.id)
                if ok:
                    entered += 1
                    if giveaway.cost and self.balance is not None:
                        self.balance -= giveaway.cost
                    self.info(f"Вошёл: {giveaway.name} "
                              f"({'бесплатно' if giveaway.cost == 0 else f'{giveaway.cost} OP'})")
                    self.recordEntry(giveaway.name, giveaway.cost, giveaway.url)
                else:
                    self.info(f"Пропуск {giveaway.name}: {reason}")
                if not self.pause():
                    break
            target = nextPageURL(soup, url)
            if target is None:
                target = f"{LISTING}?{PAGE_PARAM}={page + 1}" if len(giveaways) >= 12 else None
            if target is None or self.stopped:
                break
            response = self.get(target)
            url, html = response.url, response.text
        self.logSkips(skipped)
        return entered

    # Rows on 'my giveaway keys'. The first look only learns what is already
    # there, so turning this on does not announce every old key at once.
    def checkWins(self):
        response = self.get(WON_KEYS)
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = (soup.select('table tbody tr')
                or soup.find_all(class_=re.compile(r'key-item|keys-item')))
        found = []
        for row in rows:
            win = wonRow(row)
            if win is not None:
                found.append(win)
        state = self.manager.state
        known = set(state.value(self.key, 'won_keys', []) or [])
        # Earlier versions kept these among the seen giveaway ids.
        known |= {mark[4:] for mark in state.seen(self.key) if mark.startswith('win:')}
        first = not state.flag(self.key, 'wins_seeded')
        fresh = [(ident, name) for ident, name in found if ident not in known]
        for ident, name in fresh:
            known.add(ident)
            if not first:
                self.info(f"Новый ключ на OpiumPulses: {name}")
                self.recordWin(name, WON_KEYS)
                self.notify('', '🎉', headline=name, link=WON_KEYS,
                            note="Ключ лежит в разделе «Giveaway keys» на сайте.",
                            buttons=[("Забрать ключ", WON_KEYS),
                                     ("Выигрыши", self.manager.panelLink('/wins'))])
        if fresh or first:
            state.setFlag(self.key, 'won_keys', sorted(known))
        state.setFlag(self.key, 'wins_seeded')

    def preview(self):
        conf = self.settings()
        if not conf.get('cookie'):
            raise ValueError("сначала вставьте cookie в настройках")
        box = self.sandbox()
        box.balance = None
        box.connect(conf)
        response = box.get(LISTING)
        if not isSignedIn(response.text):
            raise AuthError("OpiumPulses не узнаёт cookie: вставьте cookie заново.")
        url, html = response.url, response.text
        seen = self.manager.state.seen(self.key)
        owned = self.ownedGames(conf)
        entriesLeft, spendLeft = self.dailyLeft(conf)
        items, balance = [], None
        for page in range(1, max(1, conf['max_pages'] or 1) + 1):
            giveaways, soup = parseListing(html, url)
            found = parseBalance(soup)
            if found is not None and box.balance is None:
                box.balance = balance = found
            for giveaway in giveaways:
                reason = box.skipReason(conf, giveaway, seen, owned)
                if reason is None and entriesLeft == 0:
                    reason = 'дневной лимит входов'
                if reason is None and spendLeft is not None and giveaway.cost > spendLeft:
                    reason = 'дневной лимит трат'
                if reason is None:
                    if giveaway.cost and box.balance is not None:
                        box.balance -= giveaway.cost
                    if entriesLeft is not None:
                        entriesLeft -= 1
                    if spendLeft is not None:
                        spendLeft -= giveaway.cost
                items.append({'name': giveaway.name, 'url': giveaway.url, 'cost': giveaway.cost,
                              'entries': None, 'enter': reason is None, 'reason': reason or ''})
            target = nextPageURL(soup, url)
            if target is None:
                target = f"{LISTING}?{PAGE_PARAM}={page + 1}" if len(giveaways) >= 12 else None
            if target is None:
                break
            response = box.get(target)
            url, html = response.url, response.text
        note = self.previewNote(conf)
        if not items:
            note = (note + ' ' if note else '') + "Сайт сейчас не показывает ни одной раздачи."
        return {'balance': balance, 'account': '', 'items': items, 'note': note}

    def run(self):
        while not self.stopped:
            conf = self.gate()
            if conf is None:
                return
            self.connect(conf)
            entered = self.cycle(conf)
            if conf['check_wins'] and not self.stopped:
                try:
                    self.checkWins()
                except RetryLater as error:
                    self.warn(f"Выигрыши не проверены: {error}")
            self.lastCycle = time.time()
            self.finishPass(f"Проход окончен: вошёл в {entered}")
            if not self.wait(max(5, conf['interval'] or 120) * 60):
                return
