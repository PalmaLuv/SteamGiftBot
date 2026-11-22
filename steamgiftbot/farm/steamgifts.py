"""SteamGifts inside the farm. The bot that already exists does the work; this
only runs it in a thread, lets the panel stop or wake it, and keeps its
settings in config.ini where the command line version expects them."""
import logging
import re
import threading

from bs4 import Comment

from steamgiftbot import filters
from steamgiftbot import settings as sgSettings
from steamgiftbot import wins as sgWins
from steamgiftbot.bot import URL, SessionExpired, SteamGift, SteamGiftError
from steamgiftbot.farm import rules
from steamgiftbot.farm.asf import LINK, STEAM_KEY, isSteamKey, steamKeys
from steamgiftbot.farm.base import (DEFAULT_USER_AGENT, AuthError, OwnLines, Platform,
                                    PlatformError, RetryLater, applySettings, coerce,
                                    cookieGuide, dailyReason, field, grouped, parseCookies,
                                    presetFields, scheduleFields, userAgentFrom)
from steamgiftbot.giveaway import parseRow
from steamgiftbot.console import log
from steamgiftbot.logging_setup import LOGGER_NAME
from steamgiftbot.state import defaultPath
from steamgiftbot.steam_api import get_game_info

# A page of the giveaway listing, as the bot asks for it.
LISTING_PAGE  = re.compile(r'/giveaways/search\?page=(\d+)')
DEFAULT_PAGES = 10

# How far a dry run looks: SteamGifts lists 50 giveaways a page.
PREVIEW_PAGES = 3

# Walks that enter nothing while the balance stands still back off: the
# 'nothing suits' pause doubles each time up to IDLE_MAX_WAIT. Growing by
# IDLE_GROWTH points may let a new giveaway fit, so it brings the usual
# pause back, as does any entry.
IDLE_MAX_WAIT = 60 * 60
IDLE_GROWTH   = 10

# Marks a giveaway SteamGifts refused for good, among the seen ids.
REFUSED = 'no:'

# The walk's order: 'odds' gathers the pass's pages first and enters the best
# chance per point first; 'site' enters page by page, as the site lists them.
ORDERS = ['odds', 'site']

# SteamGifts stops adding points at this balance.
POINTS_CAP = 400


# Filters SteamGifts applies itself, added to the listing's address: the
# giveaways above the account's level, dearer than the points to spare or
# more crowded than allowed never come back, so fewer pages are walked.
def siteQuery(config, conf, points, minPoints):
    if not conf.get('site_filters', True):
        return ''
    parts = []
    if config.contributor_level is not None:
        parts.append(f"level_max={int(config.contributor_level)}")
    if config.max_entries is not None:
        parts.append(f"entry_max={int(config.max_entries)}")
    spare = (points or 0) - (minPoints or 0)
    if config.max_cost is not None:
        spare = min(spare, int(config.max_cost))
    if spare >= 1:
        parts.append(f"point_max={spare}")
    return ''.join('&' + part for part in parts)


def listingRows(soup):
    return soup.find_all('div', {'class': 'giveaway__row-inner-wrap'}) if soup else []

# ---- keys on the won page -----------------------------------------------------

# Where a row of the won page may hold the key once the creator sent it: the
# copy button's data-clipboard-text, or an element whose class speaks of a key
# (view_key, table__column__key...). The won page is only served signed in, so
# its markup is guessed, and a row with no key read is simply left alone.
KEY_CLASS = re.compile(r'key', re.IGNORECASE)

# Links in a key box that are the site's own or the game's store page, not a gift.
NOT_A_GIFT = re.compile(r'steamgifts\.com|steampowered\.com|steamcommunity\.com',
                        re.IGNORECASE)

# A link shown in a key box counts only when it reads as a gift or redeem
# link: a shop's game page or the creator's site there is not the key, and a
# wrong key once saved is never replaced by the real one.
GIFT_LINK = re.compile(r'/gifts?(?=[/?#]|$)|/redeem|/claim|/activate|[?&](?:gift|key|code)=',
                       re.IGNORECASE)

# Outside a key box only a key as Steam prints it: capitals and digits in
# groups of five, with a digit somewhere, so a tag like 'rogue-lite-deck' or
# a shouted title is not taken for one.
PRINTED_KEY = re.compile(r'(?<![0-9A-Za-z-])[A-Z0-9]{5}(?:-[A-Z0-9]{5}){2,4}(?![0-9A-Za-z-])')


# Steam keys in some text; [] for a button label like 'View Key', so a key
# not shown yet reads as no key at all.
def keysIn(text, printed=False):
    text = LINK.sub(' ', text)
    if printed:
        return [m.group(0) for m in PRINTED_KEY.finditer(text)
                if any(c.isdigit() for c in m.group(0))]
    return [m.group(0).upper() for m in STEAM_KEY.finditer(text) if isSteamKey(m.group(0))]


def linksIn(text, giftOnly=False):
    return [link for link in LINK.findall(text)
            if not NOT_A_GIFT.search(link) and (not giftOnly or GIFT_LINK.search(link))]


def rowKey(row):
    # What a copy button or a key field holds is the key itself, link or not;
    # what the key box merely shows has to look like one.
    copied = [box['data-clipboard-text']
              for box in row.find_all(attrs={'data-clipboard-text': True})]
    shown = []
    for box in row.find_all(class_=KEY_CLASS):
        copied += [item.get('value') or '' for item in box.find_all(['input', 'textarea'])]
        shown.append(box.get_text(' ', strip=True))
        shown += [link['href'] for link in box.find_all('a', href=True)]
    found = (keysIn(' '.join(copied + shown)) + linksIn(' '.join(copied)) +
             linksIn(' '.join(shown), giftOnly=True))
    if found:
        return ' '.join(dict.fromkeys(found))
    # Failing that, a Steam key in the row's own text. Never in a link: the
    # game's name ('STAR-WARS-EPIC') or a user name could look like one.
    loose = [text for text in row.find_all(string=True)
             if not isinstance(text, Comment) and not text.find_parent(['a', 'script', 'style'])]
    return ' '.join(dict.fromkeys(keysIn(' '.join(loose), printed=True)))


# {giveaway code: key} for the rows of the won page that show one. A page the
# bot does not recognise gives nothing.
def wonKeys(soup):
    found = {}
    for row in sgWins.findRows(soup):
        win = sgWins.winFromRow(row)
        if win is None or win.code in found:
            continue
        key = rowKey(row)
        if key:
            found[win.code] = key
    return found


def giveawayCode(url):
    found = sgWins.GIVEAWAY_LINK.search(url or '')
    return found.group(1) if found else None


# Refusals that only change if the user's account does. Anything else (not
# enough points, a hiccup) is worth asking again later.
FINAL_REFUSAL = re.compile(r'missing base game|exists in account|level \d+ required|'
                           r'previously won|region|not available|ended|whitelist|group',
                           re.IGNORECASE)

# The command line bot's reasons, in the panel's language.
REASONS = {
    filters.ALREADY_ENTERED: 'уже участвуете',
    filters.PINNED: 'закреплённая',
    filters.LEVEL_TOO_HIGH: 'уровень выше вашего',
    filters.REGION_LOCKED: 'региональная',
    filters.TOO_CROWDED: 'слишком много участников',
    filters.TOO_EXPENSIVE: 'дороже лимита',
    filters.BLACKLISTED: 'в чёрном списке',
    filters.NOT_WHITELISTED: 'не в белом списке',
    filters.NOT_ENOUGH: 'не хватает поинтов',
    filters.NO_CARDS: 'без карточек',
    filters.UNKNOWN_APP: 'нельзя проверить карточки',
}


class FarmPause(Exception):
    """Raised from inside the bot's page walk when the farm wants it to stop
    entering for a while: the working hours ended or a daily limit was hit."""

    def __init__(self, message, seconds):
        super().__init__(message)
        self.seconds = seconds


class FarmSteamGift(SteamGift):
    """The command line bot, with its waits routed through the farm."""

    def __init__(self, platform, config, statePath):
        self.platform = platform
        # (code, cost) of the entry entryGIFT has just made; see tryGiveaway.
        self.justEntered = None
        super().__init__(config, statePath=statePath)
        platform.useAgent(self)

    def waitForPoints(self):
        self.waitedForPoints = True
        self.platform.endPass(self)
        seconds = self.platform.jittered(self.pointsWait)
        self.platform.info(f"Мало поинтов: {self.points}, нужно минимум {self.min_points}. "
                           f"Жду {seconds // 60} мин.")
        self.platform.balance = self.points
        if not self.platform.wait(seconds, reason=f"Ждёт поинты: {self.points} из "
                                                  f"{self.min_points} P"):
            self.stop()

    def updateInfo(self):
        super().updateInfo()
        self.platform.balance = self.points
        if getattr(self, 'username', ''):
            self.platform.account = self.username

    def extraSkipReason(self, giveaway):
        return self.platform.extraReason(giveaway, self.points, self.min_points)

    # Recorded here, before the card, so the card's buttons can name the win.
    def tellWin(self, win):
        platform = self.platform
        moment = platform.recordWin(win.name, win.url)
        platform.notify('', '🎉', headline=win.name, link=win.url,
                        note="Заберите ключ и отметьте в панели, что он получен: "
                             "SteamGifts этого требует.",
                        buttons=[("Забрать ключ", win.url),
                                 ("Выигрыши", platform.manager.panelLink('/wins'))],
                        actions=platform.manager.winActions(platform.key, moment, win.name))

    def skipped(self, giveaway, reason):
        super().skipped(giveaway, reason)
        self.platform.debug(f"Пропуск: {giveaway.name} — {REASONS.get(reason, reason)}",
                            cost=f"{giveaway.cost} P", entries=giveaway.entries,
                            url=f"{URL}/giveaway/{giveaway.code}/")

    # The bot walks the listing until an empty page. With a balance just over
    # the minimum only the cheapest giveaways fit, and that walk covered the
    # whole catalogue (150+ pages) every quarter hour. Stop after max_pages:
    # a missing page ends the walk, and the farm then waits for points.
    # The walk with the site's own filters added, in the order the settings
    # ask for. A filter that leaves nothing at all is not the error the bot
    # raises for an empty first page: nothing suits, and the farm waits.
    def getGameContent(self, page=1):
        original = self.filterURL
        query = siteQuery(self.config, self.platform.extra, self.points, self.min_points)
        self.filterURL = {kind: url + query for kind, url in original.items()}
        try:
            if self.platform.extra.get('order', 'odds') == 'odds':
                return self.walkByOdds()
            return super().getGameContent(page)
        except SteamGiftError as error:
            if not query or 'Page is empty' not in str(error):
                raise
        finally:
            self.filterURL = original

    # Every page of the pass first, then the best chance per point first:
    # copies shared among the people in, for what it costs.
    def walkByOdds(self):
        found, page = {}, 1
        while self.running:
            log(f"Getting games from page {page}", "magenta")
            soup = self.GetSoupFromPage(f"{self.baseURL}/giveaways/"
                                        f"{self.filterURL[self.type] % page}")
            new = 0
            for row in listingRows(soup):
                giveaway = parseRow(row)
                if giveaway is not None and giveaway.code not in found:
                    found[giveaway.code] = giveaway
                    new += 1
            if not new:
                break
            page += 1
        for giveaway in sorted(found.values(), key=lambda g: -g.odds):
            if not self.running or not self.tryGiveaway(giveaway):
                return

    def GetSoupFromPage(self, url):
        found = LISTING_PAGE.search(url)
        limit = self.platform.extra.get('max_pages') or DEFAULT_PAGES
        if found and int(found.group(1)) > limit:
            self.platform.info(f"Просмотрено {limit} стр., дальше в этом проходе не иду.")
            return None
        return super().GetSoupFromPage(url)

    # The entry is counted from the bot's own answer, not from its log line:
    # entryGIFT knows it went through and what it cost, tryGiveaway which
    # giveaway it was. It is recorded once the bot has written 'One more game
    # X', so the panel shows the details under that line. A dry run never
    # gets here.
    def tryGiveaway(self, giveaway):
        self.justEntered = None
        try:
            return super().tryGiveaway(giveaway)
        finally:
            done, self.justEntered = self.justEntered, None
            if done is not None and giveaway is not None and done[0] == giveaway.code:
                self.platform.entered(giveaway, done[1])

    def entryGIFT(self, id, cost):
        self.lastRejection = ''
        done = super().entryGIFT(id, cost)
        if done:
            self.platform.balance = self.points
            self.justEntered = (id, cost)
        elif self.lastRejection and FINAL_REFUSAL.search(self.lastRejection):
            self.platform.manager.state.markSeen(self.platform.key, REFUSED + id)
        return done


# The bot's per-page chatter: only in the panel's 'Подробно' view.
# 'Skipping X: not enough points' repeats the farm's own 'Пропуск' line.
NOISY = ('Getting games from page', 'Skipping ')


class ForwardHandler(logging.Handler):
    """Re-logs the command line bot's lines as this site's own."""

    def __init__(self, platform):
        super().__init__()
        self.platform = platform

    def emit(self, record):
        try:
            text = record.getMessage()
            level = logging.DEBUG if text.startswith(NOISY) else record.levelno
            self.platform.logger.log(level, text)
        except Exception:
            self.handleError(record)


class SteamGiftsPlatform(Platform):
    key         = 'steamgifts'
    unit        = 'P'
    title       = 'SteamGifts'
    siteURL     = 'https://www.steamgifts.com'
    # Both are f"{URL}/giveaway/{code}/" (wins.Win.url and entered).
    winUrlIsEntryUrl = True
    description = 'Раздачи за поинты (P), начисляются каждые ~15 минут.'
    risk = ("Правила SteamGifts не разрешают входить в раздачи скриптами и ботами, и за это "
            "аккаунт на сайте могут заблокировать (Steam это не касается). Ферма снижает риск: "
            "шлёт User-Agent вашего браузера, делает случайные паузы, не листает весь каталог "
            "и не просится туда, куда вам нельзя. Убрать риск совсем она не может: подключая "
            "SteamGifts, вы берёте его на себя. Чаще всего блокируют за неактивированные "
            "выигрыши — активируйте ключи и отмечайте «получено».")

    # Settings shown in the form, all kept in config.ini.
    FIELDS = grouped('Аккаунт', [
        field('cookie', 'Cookie PHPSESSID', 'secret',
              help='запрос steamgifts.com, скопированный как cURL, или само значение '
                   'PHPSESSID (F12 → Application → Cookies)'),
        field('contributor_level', 'Ваш contributor level', 'int', None,
              'раздачи с уровнем выше пропускаются без лишних запросов'),
    ]) + grouped('Что брать', [
        field('gift_type', 'Тип раздач', 'select', 'All', options=sgSettings.GIFT_TYPES),
        field('min_points', 'Не опускать баланс ниже', 'int', 30),
        field('max_cost', 'Макс. цена раздачи', 'int', None, 'пусто — без ограничения'),
        field('max_entries', 'Макс. участников', 'int', None,
              'пропускать раздачи, где уже больше N входов'),
        field('pinned', 'Входить в закреплённые', 'bool', True),
        field('cards_only', 'Только игры с карточками', 'bool', False),
        field('skip_region_locked', 'Пропускать региональные', 'bool', False),
        field('blacklist', 'Чёрный список', 'list', [], 'слова через запятую'),
        field('whitelist', 'Белый список', 'list', [], 'если задан — только эти'),
        field('check_wins', 'Следить за выигрышами', 'bool', True),
    ])

    # Farm-only rules, kept in farm.json: config.ini stays what the command
    # line bot understands.
    EXTRA = grouped('Аккаунт', [
        # The command line bot keeps the User-Agent from info.json; the farm
        # sends the browser's, which is what SteamGifts saw with this cookie.
        field('user_agent', 'User-Agent браузера', 'text', DEFAULT_USER_AGENT,
              'из cURL берётся сам; иначе — того же браузера, откуда cookie'),
    ]) + presetFields() + grouped('Обход', [
        field('order', 'Порядок', 'select', 'odds', options=ORDERS,
              help='odds — сначала лучший шанс на поинт (копии, участники, цена) со всех '
                   'страниц прохода; site — как на сайте, страница за страницей'),
        field('site_filters', 'Фильтры на стороне сайта', 'bool', True,
              'сайт сам убирает раздачи выше вашего уровня, дороже свободных поинтов и с '
                   'лишними участниками: меньше страниц и запросов'),
        field('save_up_to', 'Копить до (P)', 'int', None,
              'не входить, пока баланс не дорастёт до N P (сайт копит до 400), потом '
              'тратить по лучшему шансу до «Не опускать баланс ниже»: так в ход идут и '
              'дорогие раздачи. Пусто — входить сразу'),
        field('max_pages', 'Страниц за проход', 'int', DEFAULT_PAGES,
              'на странице 50 раздач; без предела бот листал весь каталог'),
    ]) + grouped('Выигрыши', [
        field('mark_received', 'Отмечать на сайте «получено»', 'bool', False,
              'когда в панели выигрыш отмечен «ключ получен» или «активирован», ферма '
              'нажимает то же на SteamGifts. Экспериментально: запрос сайта не '
              'задокументирован'),
    ]) + scheduleFields()

    def __init__(self, manager, key=None):
        super().__init__(manager, key)
        self.bot = None
        self.extra = {}
        self.passEntered = 0
        # Walks in a row that entered nothing, and the balance the run of them
        # started from; see idleWait().
        self.idlePasses = 0
        self.idleBalance = None
        # With 'save up to' set: True from reaching the target until the
        # points are spent down again.
        self.spending = False
        # The main account shares config.ini with the command line bot; an
        # added one gets its own, and its own state file next to it.
        self.configPath = (manager.configPath if self.primary
                           else manager.accountDir(self.key) / 'config.ini')

        self.attachLogger()

    # The bot logs through the package logger; mirror that into this site's
    # panel log. Called again whenever something (startLogFile) resets that
    # logger's handlers.
    def attachLogger(self):
        sgLogger = logging.getLogger(LOGGER_NAME)
        for handler in list(sgLogger.handlers):
            if getattr(handler, 'platform', None) is self:
                sgLogger.removeHandler(handler)
        # Forwarded into this site's own logger: from there a line reaches the
        # panel and log/botfarm.log, so it is still there after a restart.
        forward = ForwardHandler(self)
        forward.addFilter(OwnLines(self))
        sgLogger.addHandler(forward)
        sgLogger.setLevel(logging.INFO)
        sgLogger.propagate = False

    # The User-Agent lives with the farm's settings but belongs in the form
    # next to the cookie.
    def schema(self):
        fields = self.FIELDS + self.EXTRA
        return ([item for item in fields if item['group'] == 'Аккаунт'] +
                [item for item in fields if item['group'] != 'Аккаунт'])

    # Sends the farm's User-Agent with a bot's requests; `agent` wins when given.
    def useAgent(self, bot, agent=None):
        agent = agent or self.extraSettings().get('user_agent') or DEFAULT_USER_AGENT
        bot.session.headers['User-Agent'] = agent
        return bot

    def limitSettings(self):
        return self.extraSettings()

    def extraSettings(self):
        stored = self.manager.platformSettings(self.key)
        return {item['name']: stored.get(item['name'], item['default']) for item in self.EXTRA}

    def loadConfig(self):
        try:
            if self.primary:
                return sgSettings.load(self.configPath)
            # STEAMGIFTBOT_* variables describe the main account only.
            config = sgSettings.Settings()
            sgSettings.applyLayer(config, sgSettings.readConfigFile(self.configPath),
                                  str(self.configPath))
            # A new account starts from the form's defaults, not from nothing.
            for item in self.FIELDS:
                if item['name'] in sgSettings.REQUIRED and item['name'] != 'cookie' \
                        and getattr(config, item['name']) in (None, ''):
                    setattr(config, item['name'], item['default'])
            return config
        except sgSettings.SettingsError as error:
            raise PlatformError(str(error)) from error

    def saveConfig(self, config):
        if not self.primary:
            self.configPath.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        sgSettings.save(config, self.configPath)

    def forget(self):
        logger = logging.getLogger(LOGGER_NAME)
        for handler in list(logger.handlers):
            if getattr(handler, 'platform', None) is self:
                logger.removeHandler(handler)

    def settings(self):
        config = self.loadConfig()
        values = {}
        for item in self.FIELDS:
            value = getattr(config, item['name'])
            if item['kind'] == 'list':
                value = list(value or ())
            if value is None and item['kind'] == 'bool':
                value = item['default']
            values[item['name']] = value
        values.update(self.extraSettings())
        return values

    def guide(self):
        return cookieGuide('SteamGifts', self.siteURL, page='steamgifts.com',
                           signIn='войдите через Steam (Sign in through Steam)', extra=[
            {'title': 'Откуда берутся поинты',
             'text': 'SteamGifts начисляет поинты (P) примерно каждые 15 минут, пока вы '
                     'заходите на сайт; ферма заходит сама. Уровень аккаунта растёт, когда вы '
                     'устраиваете свои раздачи; укажите его в настройках, чтобы ферма не '
                     'тратила запросы на недоступные.'},
        ])

    @staticmethod
    def sessionFrom(text):
        return parseCookies(text, bareName='PHPSESSID').get('PHPSESSID', '').strip()

    def check(self, values):
        values = values or {}
        session = self.sessionFrom(values.get('cookie'))
        if not session:
            raise ValueError("в тексте нет cookie PHPSESSID: скопируйте запрос как cURL целиком")
        config = self.loadConfig()
        config.cookie = session
        bot = self.useAgent(SteamGift(config, statePath=defaultPath(self.configPath)),
                            userAgentFrom(str(values.get('cookie') or '')) or
                            values.get('user_agent'))
        try:
            bot.updateInfo()
        except SessionExpired as error:
            raise AuthError("SteamGifts не узнаёт этот cookie: войдите на сайт и скопируйте "
                            "запрос заново.") from error
        except SteamGiftError as error:
            raise RetryLater(str(error)) from error
        return {'account': getattr(bot, 'username', ''), 'balance': bot.points}

    def disconnect(self):
        self.stop(wait=15)
        config = self.loadConfig()
        config.cookie = ''
        self.saveConfig(config)
        self.manager.setAutostart(self.key, False)

    def updateSettings(self, incoming):
        incoming = dict(incoming)
        if incoming.get('cookie') and not isinstance(incoming['cookie'], bool):
            # Only PHPSESSID is kept, so the browser's User-Agent is taken
            # from a pasted cURL now or never. It wins over the form's field,
            # which the panel sends back unchanged with every save, the way
            # the other sites prefer the cURL's User-Agent to their field.
            agent = userAgentFrom(str(incoming['cookie']))
            if agent:
                incoming['user_agent'] = agent
            incoming['cookie'] = self.sessionFrom(incoming['cookie']) or incoming['cookie']
        # config.ini and farm.json are read, changed and written under the
        # farm's lock, so two changes at once cannot drop one another.
        with self.manager.lock:
            extra = applySettings(self.EXTRA, self.extraSettings(), incoming)
            config = self.loadConfig()
            for item in self.FIELDS:
                name = item['name']
                if name not in incoming:
                    continue
                raw = incoming[name]
                if item['kind'] == 'secret' and (raw is None or raw == '' or raw is True):
                    continue
                try:
                    value = coerce(item['kind'], raw, None)
                    if item['kind'] == 'list':
                        value = tuple(value)
                    elif item['kind'] in ('text', 'secret', 'select'):
                        value = sgSettings.CONVERTERS[name](value)
                except ValueError as error:
                    raise ValueError(f"{item['label']}: {error}") from error
                # The bot cannot start without these, so an empty box is refused
                # here rather than written to config.ini and found broken later.
                if name in sgSettings.REQUIRED and (value is None or value == ''):
                    raise ValueError(f"{item['label']}: обязательное поле")
                # Empty numbers mean 'no limit', which config.ini spells as absent.
                setattr(config, name, value)
            if config.log_info is None:
                config.log_info = True
            self.saveConfig(config)
            self.manager.savePlatformSettings(self.key, extra)
        return self.settings()

    def configured(self):
        try:
            return not self.loadConfig().missing()
        except PlatformError:
            return False

    # An entry the bot has made (see FarmSteamGift.tryGiveaway). The people in
    # and the copies: the panel's expected wins come from them. One copy, the
    # usual, is not written down.
    def entered(self, giveaway, cost):
        self.recordEntry(giveaway.name, cost, f"{URL}/giveaway/{giveaway.code}/",
                         entries=giveaway.entries,
                         copies=giveaway.copies if giveaway.copies > 1 else None)

    # 'Проход окончен' once per walk, whether it ended out of points or
    # with nothing left to enter.
    def endPass(self, bot):
        if self.passStartedAt:
            self.finishPass(f"Проход окончен: вошёл в {self.sessionEntered - self.passEntered}, "
                            f"баланс {bot.points} P")

    # The bot finds the wins; its tellWin (FarmSteamGift) records each and
    # sends the card. Then the keys the won page shows go onto the wins.
    def announce(self, bot):
        bot.announceWins()
        self.keysFromWonPage(getattr(bot, 'wonPage', None))

    # Unactivated wins are what SteamGifts bans for most. A key the creator
    # sent shows on the won page: it goes onto the win (and to ASF when
    # auto_redeem is on), and the daily report reminds until it is activated.
    # A win that has a key already keeps it; an activated one, or one imported
    # from the command line bot's logs (the user dealt with those), is left
    # alone. The first read after an upgrade stores keys quietly: no card, no
    # ASF, as the other sites' first looks only learn what is there.
    def keysFromWonPage(self, soup):
        if soup is None:
            return 0
        try:
            found = wonKeys(soup)
        except Exception as error:
            self.warn(f"SteamGifts: не удалось прочитать ключи на странице выигрышей: {error}")
            return 0
        state = self.manager.state
        first = not state.flag(self.key, 'won_keys_seeded')
        stored = 0
        for win in list(state.site(self.key).get('wins', [])):
            serial = found.get(giveawayCode(win.get('url')))
            if (not serial or win.get('cdkey') or win.get('status') == 'activated'
                    or win.get('cli')):
                continue
            try:
                self.manager.setWinKey(self.key, win['time'], win['name'], serial,
                                       redeem=not first)
            except Exception as error:
                self.warn(f"Ключ к «{win['name']}» не сохранён: {error}")
                continue
            stored += 1
            self.info(f"Ключ к «{win['name']}» взят со страницы выигрышей SteamGifts")
            if not first:
                self.tellKey(win, serial)
        state.setFlag(self.key, 'won_keys_seeded')
        return stored

    # With auto_redeem on, a Steam key goes to ASF, which tells how it went.
    def tellKey(self, win, serial):
        if steamKeys(serial) and self.manager.farmSettings().get('auto_redeem'):
            return
        self.notify('', '🔑', title='КЛЮЧ ПОЛУЧЕН', headline=win['name'],
                    link=win.get('url') or '',
                    note="Ключ сохранён в разделе «Выигрыши». Активируйте его: "
                         "SteamGifts блокирует за неактивированные выигрыши.",
                    buttons=[("Выигрыши", self.manager.panelLink('/wins'))],
                    actions=self.manager.winActions(self.key, win['time'], win['name'],
                                                    steamKey=bool(steamKeys(serial))))

    # The farm's own rules, asked by the bot for every giveaway it would enter.
    def extraReason(self, giveaway, points=None, minPoints=None):
        conf = self.extra
        if self.closedFor(conf):
            raise FarmPause("Часы работы закончились.", self.closedFor(conf))
        entriesLeft, spendLeft = self.dailyLeft(conf)
        if entriesLeft == 0 or spendLeft == 0:
            raise FarmPause("Дневной лимит исчерпан.", self.limitResetIn())
        reason = self.budgetReason(giveaway, points, minPoints, spendLeft,
                                   self.manager.state.seen(self.key))
        if reason:
            return reason
        return self.farmReason(conf, giveaway, self.ownedGames(conf),
                               ownedLabel='already in your Steam library')

    # Reasons that depend on money and memory rather than on the game: shared
    # by the real walk and the dry run so the two cannot drift apart.
    @staticmethod
    def budgetReason(giveaway, points, minPoints, spendLeft, seen):
        if REFUSED + giveaway.code in seen:
            return 'SteamGifts уже отказал'
        # 'Do not go below' means after the entry, not before it.
        if points is not None and minPoints and points - giveaway.cost < minPoints:
            return f'баланс опустится ниже {minPoints} P'
        # Over what is left of the daily spend: skip it, a cheaper one may fit.
        # The entry limit pauses the walk before this (see extraReason).
        return dailyReason(giveaway.cost, None, spendLeft)

    @staticmethod
    def farmReason(conf, giveaway, library, ownedLabel='уже есть в Steam'):
        reason = rules.presetReason(giveaway.name, conf.get('skip_junk'), conf.get('skip_adult'))
        if reason:
            return reason
        if library is not None and library.has(giveaway.appid, giveaway.name):
            return ownedLabel
        return None

    def preview(self):
        config = self.loadConfig()
        missing = config.missing()
        if missing:
            raise ValueError("не заполнены настройки: " + ', '.join(missing))
        config.once = True
        config.dry_run = True
        bot = self.useAgent(SteamGift(config, statePath=defaultPath(self.configPath)))
        try:
            bot.updateInfo()
        except SessionExpired as error:
            raise AuthError(f"{error} Вставьте новый PHPSESSID в настройках.") from error
        except SteamGiftError as error:
            raise RetryLater(str(error)) from error
        conf = self.extraSettings()
        library = self.ownedGames(conf)
        entriesLeft, spendLeft = self.dailyLeft(conf)
        seen = self.manager.state.seen(self.key)
        points, items = bot.points, []
        query = siteQuery(config, conf, bot.points, bot.min_points)
        found = {}
        for page in range(1, PREVIEW_PAGES + 1):
            rows = listingRows(bot.GetSoupFromPage(f"{bot.baseURL}/giveaways/"
                                                   f"{bot.filterURL[bot.type] % page}{query}"))
            if not rows:
                break
            for row in rows:
                giveaway = parseRow(row)
                if giveaway is not None:
                    found.setdefault(giveaway.code, giveaway)
        giveaways = list(found.values())
        if conf.get('order', 'odds') == 'odds':
            giveaways.sort(key=lambda g: -g.odds)
        target = min(int(conf['save_up_to']), POINTS_CAP) if conf.get('save_up_to') else None
        saving = target is not None and not self.spending and bot.points < target
        for giveaway in giveaways:
            if saving:
                reason = f"копит до {target} P"
            elif points <= 0 or points < bot.min_points:
                reason = f"баланс ниже минимума ({bot.min_points} P)"
            else:
                reason = filters.reasonToSkip(giveaway, config, points,
                                              hasCards=get_game_info)
                reason = REASONS.get(reason, reason)
            if reason is None:
                reason = dailyReason(giveaway.cost, entriesLeft, None)
            if reason is None:
                reason = self.budgetReason(giveaway, points, bot.min_points, spendLeft,
                                           seen)
            if reason is None:
                reason = self.farmReason(conf, giveaway, library)
            if reason is None:
                points -= giveaway.cost
                if entriesLeft is not None:
                    entriesLeft -= 1
                if spendLeft is not None:
                    spendLeft -= giveaway.cost
            items.append({'name': giveaway.name, 'url': f"{URL}/giveaway/{giveaway.code}/",
                          'cost': giveaway.cost, 'entries': giveaway.entries,
                          'enter': reason is None, 'reason': reason or ''})
        return {'balance': bot.points, 'account': '', 'items': items,
                'note': self.previewNote(conf)}

    # With 'wishlist first' on, every pass starts with SteamGifts' own
    # wishlist section, then goes on with the chosen type.
    def wishlistPass(self, bot, config):
        if not self.manager.farmSettings().get('wishlist_first') or bot.type == 'WishList':
            return
        bot.type = 'WishList'
        try:
            bot.getGameContent()
        except SteamGiftError as error:
            if 'Page is empty' not in str(error):
                raise
        finally:
            bot.type = config.gift_type

    def onWinStatus(self, win, status):
        if status not in ('received', 'activated') or not self.extraSettings().get('mark_received'):
            return
        found = re.search(r'/giveaway/([A-Za-z0-9]+)/', win.get('url') or '')
        if found:
            threading.Thread(target=self.markReceived, args=(found.group(1),),
                             name='sg-received', daemon=True).start()

    # Presses 'received' on the won page: the row's own feedback form, sent
    # as the page would send it. Returns True when the site said success.
    def markReceived(self, code, pages=5):
        try:
            bot = self.useAgent(SteamGift(self.loadConfig(),
                                          statePath=defaultPath(self.configPath)))
            bot.updateInfo()
            for page in range(1, pages + 1):
                soup = bot.GetSoupFromPage(f"{URL}/giveaways/won/search?page={page}")
                if soup is None:
                    break
                for link in soup.find_all('a', href=re.compile(rf'/giveaway/{code}/')):
                    row = link.find_parent(class_=re.compile(r'table__row-(outer|inner)-wrap'))
                    form = row.select_one('.table__column--gift-feedback form') if row else None
                    if form is None:
                        continue
                    data = {field.get('name'): field.get('value', '')
                            for field in form.find_all('input') if field.get('name')}
                    data['action'] = '1'
                    data.setdefault('xsrf_token', bot.xsrfToken)
                    response = bot.session.post(f"{URL}/ajax.php", data=data, timeout=30)
                    ok = response.ok and response.json().get('type') == 'success'
                    self.info(f"SteamGifts: «получено» для {code}: "
                              f"{'отмечено' if ok else 'сайт отказал'}")
                    return ok
            self.warn(f"SteamGifts: не нашёл на странице выигрышей кнопку «получено» для {code}")
        except Exception as error:
            self.warn(f"SteamGifts: не удалось отметить «получено»: {error}")
        return False

    # The pause after a walk that found nothing to enter. With a balance just
    # over the reserve nothing fits, and a walk of max_pages every quarter
    # hour came to ~960 requests a day for no entry at all. So walks in a row
    # that enter nothing while the balance grows by less than IDLE_GROWTH
    # wait longer each time: 15 → 30 → 60 min. The pause comes back already
    # jittered, so the log tells the wait it really is.
    def idleWait(self, points, entered, base):
        ceiling = max(base, IDLE_MAX_WAIT)
        if entered:
            self.idleReset(points, base, "Был вход")
            return self.underCeiling(self.jittered(base), ceiling)
        if self.idleBalance is not None and points - self.idleBalance >= IDLE_GROWTH:
            self.idleReset(points, base, f"Баланс вырос на {points - self.idleBalance} P")
        if self.idleBalance is None:
            self.idleBalance = points
        self.idlePasses += 1
        # The exponent is capped so a week of idle walks stays a small number.
        nominal = min(base * 2 ** min(self.idlePasses - 1, 10), ceiling)
        seconds = self.underCeiling(self.jittered(nominal), ceiling)
        if nominal > base:
            self.info(f"Проходов подряд без входов: {self.idlePasses}, баланс не вырос на "
                      f"{IDLE_GROWTH} P. Пауза увеличена до {seconds // 60} мин.")
        return seconds

    # The jitter folded back under the ceiling rather than cut at it: cut,
    # every other longest pause would come out the same to the second.
    @staticmethod
    def underCeiling(seconds, ceiling):
        return ceiling - (seconds - ceiling) if seconds > ceiling else seconds

    def idleReset(self, points, base, why):
        if self.idlePasses > 1:
            self.info(f"{why}: пауза между проходами снова {max(1, base // 60)} мин.")
        self.idlePasses = 0
        self.idleBalance = points

    # The target while the farm is saving up, None once it may enter.
    def savingFor(self, points, conf):
        target = conf.get('save_up_to')
        if not target:
            self.spending = False
            return None
        target = min(int(target), POINTS_CAP)
        if self.spending:
            return None
        if (points or 0) >= target:
            self.spending = True
            self.info(f"Накоплено {points} P: трачу на лучшие шансы.")
            return None
        return target

    def onStop(self):
        if self.bot is not None:
            self.bot.stop()

    def run(self):
        config = self.loadConfig()
        missing = config.missing()
        if missing:
            raise PlatformError("не заполнены настройки: " + ', '.join(missing))
        config.once = False
        config.dry_run = False

        bot = FarmSteamGift(self, config, defaultPath(self.configPath))
        self.bot = bot
        self.idlePasses = 0
        self.idleBalance = None
        try:
            bot.updateInfo()
            self.balance = bot.points
            self.info(f"Баланс: {bot.points}P")
            self.announce(bot)
            while not self.stopped and bot.running:
                conf = self.gate()
                if conf is None:
                    break
                self.extra = conf
                self.passEntered = self.sessionEntered
                bot.waitedForPoints = False
                target = self.savingFor(bot.points, conf)
                if target:
                    seconds = self.jittered(bot.pointsWait)
                    self.info(f"Копит поинты: {bot.points} из {target} P. "
                              f"Следующая проверка через {seconds // 60} мин.")
                    if not self.wait(seconds, reason=f"Копит поинты: {bot.points} из {target} P"):
                        break
                    self.announce(bot)
                    bot.updateInfo()
                    self.balance = bot.points
                    continue
                try:
                    self.wishlistPass(bot, config)
                    bot.getGameContent()
                except FarmPause as pause:
                    self.info(f"{pause} Пауза {max(1, pause.seconds // 60)} мин.")
                    if not self.wait(pause.seconds, reason=str(pause).rstrip('.')):
                        break
                else:
                    entered = self.sessionEntered - self.passEntered
                    # The walk reached the end of the listing with points to
                    # spare: nothing suits right now. Without this pause the
                    # bot would start over from page one at once, for ever.
                    if not bot.waitedForPoints and not self.stopped and bot.running:
                        self.endPass(bot)
                        seconds = self.idleWait(bot.points, entered, bot.pointsWait)
                        minutes = max(1, seconds // 60)
                        self.info(f"Подходящих раздач нет, баланс {bot.points}P. "
                                  f"Следующий проход через {minutes} мин.")
                        if not self.wait(seconds,
                                         reason=f"Подходящих раздач нет, {bot.points} P"):
                            break
                    elif entered:
                        # Out of points after entering: the next walk that
                        # finds nothing starts the back-off afresh.
                        self.idleReset(bot.points, bot.pointsWait, "Был вход")
                    # Spent down to the reserve, or nothing left worth it:
                    # back to saving.
                    if bot.waitedForPoints or not entered:
                        self.spending = False
                if self.stopped or not bot.running:
                    break
                self.lastCycle = self.manager.now()
                self.announce(bot)
                bot.updateInfo()
                self.balance = bot.points
        except SessionExpired as error:
            raise AuthError(f"{error} Вставьте новый PHPSESSID в настройках.") from error
        except SteamGiftError as error:
            # Cloudflare or the site being down: worth another go later.
            raise RetryLater(str(error)) from error
        finally:
            self.bot = None
