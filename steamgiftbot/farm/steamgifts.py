"""SteamGifts inside the farm. The bot that already exists does the work; this
only runs it in a thread, lets the panel stop or wake it, and keeps its
settings in config.ini where the command line version expects them."""
import logging
import re
import threading

from steamgiftbot import filters
from steamgiftbot import settings as sgSettings
from steamgiftbot.bot import URL, SessionExpired, SteamGift, SteamGiftError
from steamgiftbot.farm import rules
from steamgiftbot.farm.base import (AuthError, Platform, PlatformError, RetryLater, RingHandler,
                                    applySettings, coerce, cookieGuide, field, grouped,
                                    parseCookies, presetFields, scheduleFields)
from steamgiftbot.giveaway import parseRow
from steamgiftbot.logging_setup import LOGGER_NAME
from steamgiftbot.state import defaultPath
from steamgiftbot.steam_api import get_game_info

ENTERED_LINE = re.compile(r'^One more game (.+)$')

# A page of the giveaway listing, as the bot asks for it.
LISTING_PAGE  = re.compile(r'/giveaways/search\?page=(\d+)')
DEFAULT_PAGES = 10

# How far a dry run looks: SteamGifts lists 50 giveaways a page.
PREVIEW_PAGES = 3

# Marks a giveaway SteamGifts refused for good, among the seen ids.
REFUSED = 'no:'

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
        super().__init__(config, statePath=statePath)

    def waitForPoints(self):
        self.waitedForPoints = True
        self.platform.info(f"Мало поинтов: {self.points}, нужно минимум {self.min_points}. "
                           f"Жду {self.pointsWait // 60} мин.")
        self.platform.balance = self.points
        if not self.platform.wait(self.pointsWait, reason=f"Ждёт поинты: {self.points} из "
                                                          f"{self.min_points} P"):
            self.stop()

    def extraSkipReason(self, giveaway):
        return self.platform.extraReason(giveaway, self.points, self.min_points)

    # The bot walks the listing until an empty page. With a balance just over
    # the minimum only the cheapest giveaways fit, and that walk covered the
    # whole catalogue (150+ pages) every quarter hour. Stop after max_pages:
    # a missing page ends the walk, and the farm then waits for points.
    def GetSoupFromPage(self, url):
        found = LISTING_PAGE.search(url)
        limit = self.platform.extra.get('max_pages') or DEFAULT_PAGES
        if found and int(found.group(1)) > limit:
            self.platform.info(f"Просмотрено {limit} стр., дальше в этом проходе не иду.")
            return None
        return super().GetSoupFromPage(url)

    def entryGIFT(self, id, cost):
        self.lastRejection = ''
        done = super().entryGIFT(id, cost)
        if done:
            self.platform.balance = self.points
            self.platform.pendingCost[id] = cost
        elif self.lastRejection and FINAL_REFUSAL.search(self.lastRejection):
            self.platform.manager.state.markSeen(self.platform.key, REFUSED + id)
        return done


class EntryWatcher(logging.Handler):
    """The bot announces each entry by name only in its log line, so the
    history is filled from there."""

    def __init__(self, platform):
        super().__init__()
        self.platform = platform

    def emit(self, record):
        found = ENTERED_LINE.match(record.getMessage())
        if found:
            self.platform.enteredByName(found.group(1))


class SteamGiftsPlatform(Platform):
    key         = 'steamgifts'
    unit        = 'P'
    title       = 'SteamGifts'
    siteURL     = 'https://www.steamgifts.com'
    description = 'Раздачи за поинты (P), начисляются каждые ~15 минут.'

    # Settings shown in the form, all kept in config.ini.
    FIELDS = grouped('Аккаунт', [
        field('cookie', 'Cookie PHPSESSID', 'secret',
              help='steamgifts.com → DevTools → Application → Cookies → PHPSESSID'),
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
    EXTRA = presetFields() + grouped('Обход', [
        field('max_pages', 'Страниц за проход', 'int', DEFAULT_PAGES,
              'на странице 50 раздач; без предела бот листал весь каталог'),
    ]) + grouped('Выигрыши', [
        field('mark_received', 'Отмечать на сайте «получено»', 'bool', False,
              'когда в панели выигрыш отмечен «ключ получен» или «активирован», ферма '
              'нажимает то же на SteamGifts. Экспериментально: запрос сайта не '
              'задокументирован'),
    ]) + scheduleFields()

    def __init__(self, manager):
        super().__init__(manager)
        self.bot = None
        self.extra = {}
        self.pendingCost = {}
        self.configPath = manager.configPath

        self.attachLogger()

    # The bot logs through the package logger; mirror that into this site's
    # panel log and pick the entries out of it. Called again whenever
    # something (startLogFile) resets that logger's handlers.
    def attachLogger(self):
        sgLogger = logging.getLogger(LOGGER_NAME)
        for handler in list(sgLogger.handlers):
            if getattr(handler, 'platform', None) is self:
                sgLogger.removeHandler(handler)
        ring = RingHandler(self)
        ring.setFormatter(logging.Formatter('%(message)s'))
        sgLogger.addHandler(ring)
        sgLogger.addHandler(EntryWatcher(self))
        sgLogger.setLevel(logging.INFO)
        sgLogger.propagate = False

    def schema(self):
        return self.FIELDS + self.EXTRA

    def limitSettings(self):
        return self.extraSettings()

    def extraSettings(self):
        stored = self.manager.platformSettings(self.key)
        return {item['name']: stored.get(item['name'], item['default']) for item in self.EXTRA}

    def loadConfig(self):
        try:
            return sgSettings.load(self.configPath)
        except sgSettings.SettingsError as error:
            raise PlatformError(str(error)) from error

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
        session = self.sessionFrom((values or {}).get('cookie'))
        if not session:
            raise ValueError("в тексте нет cookie PHPSESSID: скопируйте запрос как cURL целиком")
        config = self.loadConfig()
        config.cookie = session
        bot = SteamGift(config, statePath=defaultPath(self.configPath))
        try:
            bot.updateInfo()
        except SessionExpired as error:
            raise AuthError("SteamGifts не узнаёт этот cookie: войдите на сайт и скопируйте "
                            "запрос заново.") from error
        except SteamGiftError as error:
            raise RetryLater(str(error)) from error
        return {'account': '', 'balance': bot.points}

    def disconnect(self):
        self.stop(wait=15)
        config = self.loadConfig()
        config.cookie = ''
        sgSettings.save(config, self.configPath)
        self.manager.setAutostart(self.key, False)

    def updateSettings(self, incoming):
        incoming = dict(incoming)
        if incoming.get('cookie') and not isinstance(incoming['cookie'], bool):
            incoming['cookie'] = self.sessionFrom(incoming['cookie']) or incoming['cookie']
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
        sgSettings.save(config, self.configPath)
        self.manager.savePlatformSettings(self.key, extra)
        return self.settings()

    def configured(self):
        try:
            return not self.loadConfig().missing()
        except PlatformError:
            return False

    def enteredByName(self, name):
        cost = 0
        if self.pendingCost:
            # Entries are made one at a time, so the newest pending one is it.
            _code, cost = self.pendingCost.popitem()
        self.recordEntry(name, cost, self.siteURL)

    # The bot sends the Telegram message itself; the farm only keeps a record.
    def announce(self, bot):
        for win in bot.announceWins():
            self.recordWin(win.name, win.url)

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
        if spendLeft is not None and giveaway.cost > spendLeft:
            return 'дневной лимит трат'
        return None

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
        bot = SteamGift(config, statePath=defaultPath(self.configPath))
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
        for page in range(1, PREVIEW_PAGES + 1):
            soup = bot.GetSoupFromPage(f"{bot.baseURL}/giveaways/"
                                       f"{bot.filterURL[bot.type] % page}")
            rows = soup.find_all('div', {'class': 'giveaway__row-inner-wrap'}) if soup else []
            if not rows:
                break
            for row in rows:
                giveaway = parseRow(row)
                if giveaway is None:
                    continue
                if points <= 0 or points < bot.min_points:
                    reason = f"баланс ниже минимума ({bot.min_points} P)"
                else:
                    reason = filters.reasonToSkip(giveaway, config, points,
                                                  hasCards=get_game_info)
                    reason = REASONS.get(reason, reason)
                if reason is None and entriesLeft == 0:
                    reason = 'дневной лимит входов'
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
            bot = SteamGift(self.loadConfig(), statePath=defaultPath(self.configPath))
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
                bot.waitedForPoints = False
                try:
                    self.wishlistPass(bot, config)
                    bot.getGameContent()
                except FarmPause as pause:
                    self.info(f"{pause} Пауза {max(1, pause.seconds // 60)} мин.")
                    if not self.wait(pause.seconds, reason=str(pause).rstrip('.')):
                        break
                else:
                    # The walk reached the end of the listing with points to
                    # spare: nothing suits right now. Without this pause the
                    # bot would start over from page one at once, for ever.
                    if not bot.waitedForPoints and not self.stopped and bot.running:
                        minutes = max(1, bot.pointsWait // 60)
                        self.info(f"Подходящих раздач нет, баланс {bot.points}P. "
                                  f"Следующий проход через {minutes} мин.")
                        if not self.wait(bot.pointsWait,
                                         reason=f"Подходящих раздач нет, {bot.points} P"):
                            break
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
