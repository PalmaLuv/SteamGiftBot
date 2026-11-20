"""Holds the farm together: its own settings file (farm.json), what it
remembers between runs (botfarm-state.json), the sites, and notifications."""
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import threading
import time

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from steamgiftbot import notify
from steamgiftbot import settings as sgSettings
from steamgiftbot.farm import rules
from steamgiftbot.farm.base import (HISTORY_LENGTH, actingFor, applySettings, field, grouped,
                                    publicValues)

FARM_FILE  = 'farm.json'
STATE_FILE = 'botfarm-state.json'
# Added accounts keep their own files (SteamGifts: config.ini and state) here.
ACCOUNTS_DIR = 'accounts'
MAIN_PROFILE = 'main'
ACCOUNT_KEY  = re.compile(r'^[a-z]+-[0-9]{1,3}$')

# Remembered giveaway ids per site; old ones fall off the end.
SEEN_LIMIT = 5000

# How far back the daily limits look.
RECENT_SECONDS = 86400

# Days of per-day counters kept for the chart.
DAILY_DAYS = 120

# What the user has done with a key they won.
WIN_STATUSES = ('', 'received', 'activated')

log = logging.getLogger('botfarm')

DEFAULT_ZONE = 'Europe/Kyiv'

# Settings that belong to the whole farm rather than to one site.
FARM_FIELDS = (
    grouped('Общее', [
        field('timezone', 'Часовой пояс', 'zone', DEFAULT_ZONE,
              'для часов работы и сводки, например Europe/Kyiv или Europe/Moscow'),
    ])
    + grouped('Библиотека Steam', [
        field('steam_api_key', 'Steam Web API key', 'secret',
              help='steamcommunity.com/dev/apikey — нужен, чтобы пропускать игры, которые '
                   'у вас уже есть'),
        field('steam_profile', 'Профиль Steam', 'text', '',
              'SteamID64 или ссылка на профиль; «Игровые данные» должны быть открыты'),
        field('wishlist_first', 'Сначала игры из списка желаемого', 'bool', False,
              'IndieGala берёт их первыми (и может тратить резерв), SteamGifts начинает '
              'каждый проход с раздела «Wishlist»; список желаемого должен быть открыт'),
    ])
    + grouped('ArchiSteamFarm', [
        field('asf_url', 'Адрес IPC', 'text', 'http://127.0.0.1:1242',
              'если ASF на этом же сервере — оставьте как есть'),
        field('asf_password', 'Пароль IPC', 'secret',
              help='IPCPassword из config/ASF.json; пусто — ферма прочитает его из '
                   '~/asf/config/ASF.json сама'),
        field('asf_bot', 'Бот для ключей', 'text', '',
              'имя бота ASF; пусто — первый бот в сети'),
        field('auto_redeem', 'Активировать выигранные ключи сразу', 'bool', False,
              'как только у выигрыша появится ключ, ASF активирует его, а в Telegram придёт '
              'результат'),
    ])
    + grouped('Telegram', [
        field('telegram_token', 'Токен бота', 'secret',
              help='создайте бота у @BotFather командой /newbot и вставьте токен, который он '
                   'пришлёт'),
        field('telegram_chat', 'ID чата', 'text', '',
              'напишите боту любое сообщение и нажмите «Найти мой чат»'),
        field('telegram_enabled', 'Присылать уведомления', 'bool', True,
              'выигрыши, ошибки, слетевшие cookie'),
        field('telegram_commands', 'Управлять фермой командами', 'bool', False,
              '/status, /pause, /start, /run, /preview, /wins, /report — отвечает только '
              'в этот чат'),
        field('daily_report', 'Присылать сводку за сутки', 'bool', False,
              'входы, траты, выигрыши и баланс по каждой площадке'),
        field('report_hour', 'Час отправки сводки', 'int', 21, '0–23, по часовому поясу фермы'),
    ])
)

# Kept in config.ini, where the command line bot reads them too.
CONFIG_FIELDS = ('telegram_token', 'telegram_chat', 'telegram_enabled')


def writePrivate(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    if os.name != 'nt':
        os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def readJSON(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return copy.deepcopy(default)


def hashPassword(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200_000)
    return {'salt': salt, 'hash': digest.hex()}


def checkPassword(password, stored):
    if not stored or not stored.get('hash'):
        return False
    attempt = hashPassword(password, stored['salt'])
    return hmac.compare_digest(attempt['hash'], stored['hash'])


class FarmState:
    """Entries, wins and seen ids per site. Saved after every change: the file
    is small and losing it only means a few repeated requests."""

    def __init__(self, path, dayOf=None):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = readJSON(self.path, {})
        self.dayOf = dayOf or (lambda moment: time.strftime('%Y-%m-%d', time.localtime(moment)))
        self.seenSets = {key: set(value.get('seen', []))
                         for key, value in self.data.items() if isinstance(value, dict)}
        for key, site in self.data.items():
            if isinstance(site, dict) and not key.startswith('_') and 'daily' not in site:
                self.backfillDaily(site)

    # The history only keeps the last few hundred entries, so the chart keeps
    # its own per-day counts; a state file from before them starts from that.
    def backfillDaily(self, site):
        daily = {}
        for entry in site.get('entries', []):
            day = daily.setdefault(self.dayOf(entry['time']), {'e': 0, 's': 0, 'w': 0})
            day['e'] += 1
            day['s'] += entry.get('cost') or 0
        for win in site.get('wins', []):
            daily.setdefault(self.dayOf(win['time']), {'e': 0, 's': 0, 'w': 0})['w'] += 1
        site['daily'] = daily

    def bump(self, site, moment, entries=0, spent=0, wins=0):
        daily = site.setdefault('daily', {})
        day = daily.setdefault(self.dayOf(moment), {'e': 0, 's': 0, 'w': 0})
        day['e'] += entries
        day['s'] += spent
        day['w'] += wins
        for old in sorted(daily)[:-DAILY_DAYS]:
            del daily[old]

    def daily(self, key, day):
        return self.site(key).get('daily', {}).get(day) or {'e': 0, 's': 0, 'w': 0}

    def site(self, key):
        return self.data.setdefault(key, {'entries': [], 'wins': [], 'seen': [], 'flags': {},
                                          'totalEntered': 0, 'totalSpent': 0})

    def save(self):
        try:
            writePrivate(self.path, self.data)
        except OSError as error:
            log.warning(f"Не удалось сохранить {self.path}: {error}")

    def addEntry(self, key, entry):
        with self.lock:
            site = self.site(key)
            # Built (from the history) before this entry joins it, or the
            # entry would be counted twice.
            recent = self.recent(site)
            site['entries'] = (site.get('entries', []) + [entry])[-HISTORY_LENGTH:]
            site['totalEntered'] = site.get('totalEntered', 0) + 1
            site['totalSpent'] = site.get('totalSpent', 0) + (entry.get('cost') or 0)
            self.bump(site, entry['time'], entries=1, spent=entry.get('cost') or 0)
            recent.append([entry['time'], entry.get('cost') or 0])
            self.trimRecent(site)
            self.save()

    def addWin(self, key, win):
        with self.lock:
            site = self.site(key)
            win = {'status': '', **win}
            site['wins'] = (site.get('wins', []) + [win])[-HISTORY_LENGTH:]
            self.bump(site, win['time'], wins=1)
            self.save()

    # Marks a win as 'received' or 'activated' ('' takes it back). The win is
    # told apart by its time and name, which the panel got from the history.
    def setWinStatus(self, key, moment, name, status):
        if status not in WIN_STATUSES:
            raise ValueError("неизвестный статус выигрыша")
        with self.lock:
            for win in self.site(key).get('wins', []):
                if abs(win['time'] - float(moment)) < 0.001 and win['name'] == name:
                    win['status'] = status
                    self.save()
                    return True
        return False

    def findWin(self, site, moment, name):
        for win in self.site(site).get('wins', []):
            if abs(win['time'] - float(moment)) < 0.001 and win['name'] == name:
                return win
        return None

    def updateWin(self, site, moment, name, **changes):
        with self.lock:
            win = self.findWin(site, moment, name)
            if win is None:
                return False
            win.update(changes)
            self.save()
            return True

    def openWins(self, key):
        return [win for win in self.site(key).get('wins', []) if not win.get('status')]

    def seen(self, key):
        return self.seenSets.setdefault(key, set(self.site(key).get('seen', [])))

    def markSeen(self, key, ident):
        with self.lock:
            site = self.site(key)
            ids = site.get('seen', [])
            if ident not in ids:
                ids.append(ident)
            site['seen'] = ids[-SEEN_LIMIT:]
            self.seen(key).add(ident)
            self.save()

    def flag(self, key, name):
        return bool(self.site(key).get('flags', {}).get(name))

    def setFlag(self, key, name, value=True):
        with self.lock:
            self.site(key).setdefault('flags', {})[name] = value
            self.save()

    def totals(self, key):
        site = self.site(key)
        return {
            'entered': site.get('totalEntered', 0),
            'spent': site.get('totalSpent', 0),
            'wins': len(site.get('wins', [])),
            'today': self.usage(key)[0],
        }

    # [time, cost] of every entry in the last day. Kept apart from the history,
    # which is cut at HISTORY_LENGTH: counting the limits from that list made
    # a daily limit above 300 entries impossible to reach.
    @staticmethod
    def recent(site):
        if 'recent' not in site:
            since = time.time() - RECENT_SECONDS
            site['recent'] = [[entry['time'], entry.get('cost') or 0]
                              for entry in site.get('entries', []) if entry['time'] > since]
        return site['recent']

    def trimRecent(self, site):
        since = time.time() - RECENT_SECONDS
        site['recent'] = [item for item in self.recent(site) if item[0] > since]

    # (entries, spent, oldest entry time) over the last `seconds` (up to a day).
    def usage(self, key, seconds=86400):
        since = time.time() - seconds
        with self.lock:
            window = [item for item in self.recent(self.site(key)) if item[0] > since]
        return (len(window), sum(cost for _time, cost in window),
                min((moment for moment, _cost in window), default=None))

    def winsSince(self, key, since):
        return [win for win in self.site(key).get('wins', []) if win['time'] > since]

    def value(self, key, name, default=None):
        return self.site(key).get('flags', {}).get(name, default)

    def history(self, key, limit=50):
        site = self.site(key)
        return {'entries': list(reversed(site.get('entries', [])))[:limit],
                'wins': list(reversed(site.get('wins', [])))[:limit]}


class FarmManager:
    def __init__(self, dataDir=None, configPath=None):
        self.dataDir    = Path(dataDir or sgSettings.BASE_DIR)
        self.configPath = Path(configPath or sgSettings.DEFAULT_CONFIG_PATH)
        self.farmPath   = self.dataDir / FARM_FILE
        self.lock       = threading.Lock()
        self.accountsLock = threading.Lock()
        self.farm       = readJSON(self.farmPath, {})
        self.farm.setdefault('web', {})
        self.farm.setdefault('platforms', {})
        self.farm.setdefault('settings', {})
        self.state      = FarmState(self.dataDir / STATE_FILE, dayOf=self.dayOf)
        self.platforms  = {}
        self.steam      = rules.SteamLibrary()
        from steamgiftbot.farm.asf import ASF
        self.asf        = ASF(self)
        self.clock      = None
        self.panelURLs  = []
        self.startedAt  = time.time()
        self.clockStop  = threading.Event()

        from steamgiftbot.farm.gog import GOGPlatform
        from steamgiftbot.farm.indiegala import IndieGalaPlatform
        from steamgiftbot.farm.itch import ItchPlatform
        from steamgiftbot.farm.opiumpulses import OpiumPulsesPlatform
        from steamgiftbot.farm.steamfree import SteamFreePlatform
        from steamgiftbot.farm.steamgifts import SteamGiftsPlatform
        self.kinds = {}
        for cls in (SteamGiftsPlatform, IndieGalaPlatform, OpiumPulsesPlatform,
                    SteamFreePlatform, GOGPlatform, ItchPlatform):
            self.kinds[cls.key] = cls
            self.platforms[cls.key] = cls(self)
        # Accounts are people (yours, a brother's): each has its own set of
        # sites. The main one holds the sites' first cards.
        self.farm.setdefault('profiles', [])
        if not any(item.get('id') == MAIN_PROFILE for item in self.farm['profiles']):
            self.farm['profiles'].insert(0, {'id': MAIN_PROFILE, 'name': 'Основная'})
        # Sites added to an account: [{'key': 'steamgifts-2', 'kind': 'steamgifts'}].
        self.farm.setdefault('accounts', [])
        for item in self.farm['accounts']:
            cls = self.kinds.get(item.get('kind'))
            if cls is not None and ACCOUNT_KEY.match(item.get('key') or '') \
                    and item['key'] not in self.platforms:
                self.platforms[item['key']] = cls(self, key=item['key'])
        self.sortPlatforms()
        self.retitle()

    @staticmethod
    def now():
        return time.time()

    # ---- farm-wide settings --------------------------------------------------

    def farmSettings(self):
        stored = self.farm['settings']
        values = {item['name']: stored.get(item['name'], item['default']) for item in FARM_FIELDS}
        config = self.loadConfig()
        if config is not None:
            for name in CONFIG_FIELDS:
                value = getattr(config, name)
                values[name] = values[name] if value is None else value
        return values

    def loadConfig(self):
        try:
            return sgSettings.load(self.configPath)
        except sgSettings.SettingsError:
            return None

    def publicFarmSettings(self):
        values = publicValues(FARM_FIELDS, self.farmSettings())
        values['steam_status'] = self.steam.problem
        return values

    def updateFarmSettings(self, incoming):
        values = applySettings(FARM_FIELDS, self.farmSettings(), incoming)
        if values['report_hour'] is not None and values['report_hour'] > 23:
            raise ValueError("Час отправки сводки: от 0 до 23")
        config = self.loadConfig()
        if config is not None and any(name in incoming for name in CONFIG_FIELDS):
            for name in CONFIG_FIELDS:
                value = values[name]
                setattr(config, name, sgSettings.CONVERTERS[name](value)
                        if name != 'telegram_enabled' else bool(value))
            sgSettings.save(config, self.configPath)
        self.farm['settings'] = {key: value for key, value in values.items()
                                 if key not in CONFIG_FIELDS}
        self.saveFarm()
        self.steam.cache.clear()
        return values

    # Everything the settings page shows besides the values themselves.
    def settingsInfo(self):
        from zoneinfo import available_timezones
        zones = sorted(name for name in available_timezones()
                       if '/' in name and not name.startswith(('Etc/', 'SystemV/', 'posix/',
                                                               'right/')))
        return {'zones': zones, 'panelURLs': self.panelURLs, 'startedAt': self.startedAt,
                'now': self.localNow().strftime('%H:%M'), 'zone': str(self.zone())}

    # Chats the bot has seen, so the chat id can be picked rather than looked up.
    def telegramChats(self, token=None):
        token = (token or '').strip() or self.farmSettings().get('telegram_token')
        if not token:
            raise ValueError("сначала вставьте токен бота")
        try:
            chats = notify.findChats(token)
        except notify.NotifyError as error:
            raise ValueError(f"Telegram: {error}") from error
        return [{'id': str(chat['id']), 'title': notify.chatName(chat) or str(chat['id']),
                 'type': chat.get('type', '')} for chat in chats]

    def steamCheck(self):
        conf = self.farmSettings()
        if not conf.get('steam_profile'):
            raise ValueError("укажите профиль Steam")
        self.steam.cache.clear()
        self.steam.wishCache.clear()
        parts = []
        if conf.get('steam_api_key'):
            owned = self.steam.owned(conf['steam_api_key'], conf['steam_profile'])
            parts.append(f"в библиотеке {len(owned)} игр" if owned is not None
                         else f"библиотека не загрузилась: {self.steam.problem}")
        else:
            parts.append("ключа API нет — пропуск своих игр не работает")
        wished = self.steam.wishlist(conf.get('steam_api_key'), conf['steam_profile'])
        parts.append(f"в списке желаемого {len(wished)}" if wished is not None
                     else f"список желаемого не загрузился: {self.steam.problem}")
        return 'Steam: ' + ', '.join(parts)

    def logoutEverywhere(self):
        self.farm['web']['secret'] = secrets.token_hex(32)
        self.saveFarm()

    def zone(self):
        try:
            return ZoneInfo(self.farmSettings()['timezone'] or DEFAULT_ZONE)
        except Exception:
            return ZoneInfo(DEFAULT_ZONE)

    def localNow(self):
        return datetime.now(self.zone())

    def dayOf(self, moment):
        return datetime.fromtimestamp(moment, self.zone()).strftime('%Y-%m-%d')

    # ---- the panel's overview ------------------------------------------------

    def summary(self, days=30):
        days = max(1, min(int(days), DAILY_DAYS))
        today = self.localNow().date()
        dates = [(today - timedelta(days=back)).isoformat() for back in range(days - 1, -1, -1)]
        week = time.time() - 7 * 86400
        sites = []
        for platform in self.platforms.values():
            totals = self.state.totals(platform.key)
            count, spent, _ = self.state.usage(platform.key)
            series = [self.state.daily(platform.key, day) for day in dates]
            sites.append({
                'key': platform.key, 'title': platform.title, 'unit': platform.unit,
                'today': count, 'spentToday': spent,
                'entered': totals['entered'], 'spent': totals['spent'], 'wins': totals['wins'],
                'winsWeek': len(self.state.winsSince(platform.key, week)),
                'entries': [day['e'] for day in series],
                'spentByDay': [day['s'] for day in series],
                'winsByDay': [day['w'] for day in series],
            })
        return {'days': dates, 'sites': sites}

    def historyRows(self, kind='entries', site='', query=''):
        rows = []
        for platform in self.platforms.values():
            if site and platform.key != site:
                continue
            for row in self.state.site(platform.key).get(kind, []):
                rows.append({**row, 'key': platform.key, 'title': platform.title,
                             'unit': platform.unit})
        words = query.lower().split()
        if words:
            rows = [row for row in rows if all(word in row['name'].lower() for word in words)]
        return sorted(rows, key=lambda row: row['time'], reverse=True)

    def historyPage(self, kind='entries', site='', query='', page=1, per=50):
        if kind not in ('entries', 'wins'):
            raise ValueError("неизвестный вид истории")
        rows = self.historyRows(kind, site, query)
        per = max(10, min(int(per), 200))
        pages = max(1, -(-len(rows) // per))
        page = max(1, min(int(page), pages))
        return {'rows': rows[(page - 1) * per:page * per], 'total': len(rows),
                'page': page, 'pages': pages}

    def historyCSV(self, kind='entries', site='', query=''):
        lines = ['Когда;Площадка;Название;Цена;Ссылка']
        zone = self.zone()
        for row in self.historyRows(kind, site, query):
            when = datetime.fromtimestamp(row['time'], zone).strftime('%Y-%m-%d %H:%M')
            cells = [when, row['title'], row['name'], str(row.get('cost') or 0),
                     row.get('url') or '']
            lines.append(';'.join('"' + cell.replace('"', '""') + '"' for cell in cells))
        # A byte order mark, so Excel opens the Cyrillic right.
        return '\ufeff' + '\r\n'.join(lines) + '\r\n'

    def openWins(self):
        found = []
        for platform in self.platforms.values():
            for win in self.state.openWins(platform.key):
                found.append({**win, 'key': platform.key, 'title': platform.title})
        return sorted(found, key=lambda win: win['time'], reverse=True)

    def ownedGames(self):
        conf = self.farmSettings()
        return self.steam.owned(conf['steam_api_key'], conf['steam_profile'])

    # Wishlisted app ids when 'wishlist first' is on, else None.
    def wishlist(self):
        conf = self.farmSettings()
        if not conf.get('wishlist_first'):
            return None
        return self.steam.wishlist(conf['steam_api_key'], conf['steam_profile'])

    # ---- won keys --------------------------------------------------------------

    def setWinKey(self, key, moment, name, value):
        value = ' '.join(str(value or '').split()).upper()
        if not self.state.updateWin(key, moment, name, cdkey=value):
            raise ValueError("выигрыш не найден")
        if value and self.farmSettings().get('auto_redeem'):
            self.redeemWin(key, moment, name)
        return value

    def redeemWin(self, key, moment, name):
        win = self.state.findWin(key, moment, name)
        if win is None:
            raise ValueError("выигрыш не найден")
        if not win.get('cdkey'):
            raise ValueError("у этого выигрыша нет ключа: вставьте его в таблице")
        kind, words = self.asf.redeem(win['cdkey'], bot=self.keyBotFor(key))
        changes = {'redeem': words}
        if kind in ('ok', 'owned'):
            changes['status'] = 'activated'
        self.state.updateWin(key, moment, name, **changes)
        title = self.platforms[key].title if key in self.platforms else key
        self.notify(f"[{title}] ключ «{name}»: {words}")
        if kind in ('ok', 'owned'):
            self.platforms[key].onWinStatus(win, 'activated')
        return kind, words

    # ---- daily report ----------------------------------------------------------

    def report(self, now=None):
        since = (now or time.time()) - 86400
        lines = ["сводка за сутки"]
        winsTotal = 0
        for platform in self.platforms.values():
            count, spent, _ = self.state.usage(platform.key)
            wins = self.state.winsSince(platform.key, since)
            winsTotal += len(wins)
            if not count and not wins and not platform.running:
                continue
            line = f"• {platform.title}: {count} вх., потрачено {spent}"
            if platform.balance is not None:
                line += f", баланс {platform.balance}"
            if wins:
                line += f", выигрыши: {', '.join(win['name'] for win in wins)}"
            if platform.lastError:
                line += f"\n  ⚠ {platform.lastError}"
            lines.append(line)
        if len(lines) == 1:
            lines.append("за сутки ни одного входа")
        lines.append(f"Выигрышей за сутки: {winsTotal}")
        waiting = self.openWins()
        if waiting:
            lines.append(f"Не отмечено, что ключ получен: {len(waiting)} "
                         f"({', '.join(win['name'] for win in waiting[:5])}). SteamGifts "
                         "требует отмечать полученные выигрыши.")
        return '\n'.join(lines)

    # Sends the report once a day at the chosen hour. True when it went out.
    def reportTick(self):
        conf = self.farmSettings()
        if not conf['daily_report'] or conf['report_hour'] is None:
            return False
        now = self.localNow()
        today = now.strftime('%Y-%m-%d')
        if now.hour != conf['report_hour'] or self.state.value('_farm', 'reportDay') == today:
            return False
        self.state.setFlag('_farm', 'reportDay', today)
        self.notify(self.report())
        return True

    def startClock(self):
        def tick():
            while not self.clockStop.wait(60):
                try:
                    self.reportTick()
                except Exception as error:
                    log.warning(f"Сводка не отправлена: {error}")
        self.clock = threading.Thread(target=tick, name='farm-clock', daemon=True)
        self.clock.start()

    def saveFarm(self):
        with self.lock:
            writePrivate(self.farmPath, self.farm)

    # ---- several accounts of one site ---------------------------------------

    # Every account of a site next to the others, the main one first.
    def sortPlatforms(self):
        order = list(self.kinds)
        self.platforms = dict(sorted(self.platforms.items(),
                                     key=lambda item: (order.index(item[1].kind), item[1].number)))

    def accountDir(self, key):
        return self.dataDir / ACCOUNTS_DIR / key

    # ---- accounts (profiles) ------------------------------------------------

    def profiles(self):
        return self.farm['profiles']

    def profile(self, ident):
        for item in self.farm['profiles']:
            if item.get('id') == ident:
                return item
        raise ValueError("нет такой учётки")

    def profileOf(self, key):
        platform = self.platforms.get(key)
        if platform is not None and platform.primary:
            return MAIN_PROFILE
        wanted = self.farm['platforms'].get(key, {}).get('profile') or MAIN_PROFILE
        return wanted if any(item.get('id') == wanted for item in self.farm['profiles']) \
            else MAIN_PROFILE

    @staticmethod
    def cleanName(name):
        name = ' '.join(str(name or '').split())[:40]
        if not name:
            raise ValueError("у учётки должно быть имя")
        return name

    def createProfile(self, name, asfBot=''):
        name = self.cleanName(name)
        with self.accountsLock:
            if any(item['name'].lower() == name.lower() for item in self.farm['profiles']):
                raise ValueError(f"учётка «{name}» уже есть")
            seq = self.farm.get('profileSeq', 1) + 1
            self.farm['profileSeq'] = seq
            item = {'id': f'p{seq}', 'name': name, 'asf_bot': str(asfBot or '').strip()}
            self.farm['profiles'].append(item)
            self.saveFarm()
        return item

    def updateProfile(self, ident, name=None, asfBot=None):
        item = self.profile(ident)
        if name is not None:
            name = self.cleanName(name)
            if any(other is not item and other['name'].lower() == name.lower()
                   for other in self.farm['profiles']):
                raise ValueError(f"учётка «{name}» уже есть")
            item['name'] = name
        if asfBot is not None:
            item['asf_bot'] = str(asfBot or '').strip()
        self.saveFarm()
        self.retitle()
        return item

    # Removes an account with every site connected in it.
    def deleteProfile(self, ident):
        if ident == MAIN_PROFILE:
            raise ValueError("основную учётку удалить нельзя")
        item = self.profile(ident)
        for key in [key for key in self.platforms if self.profileOf(key) == ident]:
            self.removeAccount(key)
        self.farm['profiles'] = [other for other in self.farm['profiles'] if other is not item]
        self.saveFarm()
        self.retitle()

    def publicProfiles(self):
        return [{'id': item['id'], 'name': item['name'], 'asfBot': item.get('asf_bot', ''),
                 'main': item['id'] == MAIN_PROFILE} for item in self.farm['profiles']]

    # Titles tell accounts apart: "IndieGala · Брат". A site that only the
    # main account has keeps its plain name.
    def retitle(self):
        names = {item['id']: item['name'] for item in self.farm['profiles']}
        # Only connected cards count: an empty catalog card is nobody's yet.
        owners = {}
        for key, platform in self.platforms.items():
            if self.isConnected(platform):
                owners.setdefault(platform.kind, set()).add(self.profileOf(key))
        for key, platform in self.platforms.items():
            profile = self.profileOf(key)
            name = self.farm['platforms'].get(key, {}).get('label') or ''
            if not name and (profile != MAIN_PROFILE or len(owners.get(platform.kind, ())) > 1):
                name = names.get(profile, '')
            platform.title = f"{platform.baseTitle} · {name}" if name else platform.baseTitle

    @staticmethod
    def isConnected(platform):
        try:
            return platform.configured()
        except Exception:
            return False

    # Asks the site who the cookie belongs to, and refuses an account that is
    # already connected here under another card.
    def checkAccount(self, platform, values):
        with actingFor(platform):
            found = platform.check(values) or {}
        account = str(found.get('account') or '').strip()
        if account:
            for other in self.platforms.values():
                if other is platform or other.kind != platform.kind:
                    continue
                known = self.farm['platforms'].get(other.key, {}).get('account') or other.account
                if known and str(known).strip().lower() == account.lower():
                    raise ValueError(f"аккаунт {account} уже подключён: {other.title}")
        return found

    def rememberAccount(self, platform, found):
        account = str((found or {}).get('account') or '').strip()
        if account:
            self.platformEntry(platform.key)['account'] = account
            self.saveFarm()
            self.retitle()

    # Checks the pasted cookie on a new instance and keeps it only if the site
    # accepted it, so a failed try leaves nothing behind.
    def addAccount(self, kind, values, profile=MAIN_PROFILE):
        cls = self.kinds.get(kind)
        if cls is None:
            raise ValueError("нет такой площадки")
        if not cls.multiAccount:
            raise ValueError(f"у {cls.title} одна карточка на все учётки")
        owner = self.profile(profile)
        # The main account's first card of a site is the site's own one.
        primary = self.platforms.get(kind)
        if profile == MAIN_PROFILE and primary is not None and not primary.configured():
            found = self.checkAccount(primary, values)
            primary.updateSettings({name: values[name] for name in primary.connectFields
                                    if name in values})
            self.platformEntry(kind)['connected'] = True
            self.rememberAccount(primary, found)
            self.saveFarm()
            self.retitle()
            return primary, found
        for key, other in self.platforms.items():
            if other.kind == kind and self.profileOf(key) == profile \
                    and (other.configured() or not other.primary):
                raise ValueError(f"в учётке «{owner['name']}» {cls.title} уже подключена")
        with self.accountsLock:
            used = [platform.number for platform in self.platforms.values()
                    if platform.kind == kind]
            number = max(used + [self.farm.setdefault('accountSeq', {}).get(kind, 1)]) + 1
            key = f"{kind}-{number}"
            platform = cls(self, key=key)
            found = self.checkAccount(platform, values)
            self.farm['accountSeq'][kind] = number
            self.farm['accounts'].append({'key': key, 'kind': kind})
            entry = self.platformEntry(key)
            entry['connected'] = True
            entry['profile'] = profile
            if found.get('account'):
                entry['account'] = str(found['account']).strip()
            self.platforms[key] = platform
            self.sortPlatforms()
            platform.updateSettings({name: values[name] for name in platform.connectFields
                                     if name in values})
            self.saveFarm()
            self.retitle()
        return platform, found

    def removeAccount(self, key):
        platform = self.platforms.get(key)
        if platform is None:
            raise ValueError("нет такой учётки")
        if platform.primary:
            raise ValueError("основную учётку можно только отключить")
        platform.stop(wait=15)
        platform.disconnect()
        platform.forget()
        with self.accountsLock:
            self.platforms.pop(key, None)
            self.farm['accounts'] = [item for item in self.farm['accounts']
                                     if item.get('key') != key]
            self.farm['platforms'].pop(key, None)
            self.saveFarm()
            self.retitle()
        shutil.rmtree(self.accountDir(key), ignore_errors=True)

    def renameAccount(self, key, label):
        label = ' '.join(str(label or '').split())[:40]
        self.platformEntry(key)['label'] = label
        self.saveFarm()
        self.retitle()
        return self.platforms[key].title

    # The ASF bot a site's keys go to: the site's own choice, else its
    # account's Steam bot, else the farm's.
    def keyBotFor(self, key):
        own = str(self.farm['platforms'].get(key, {}).get('asf_bot') or '').strip()
        if own:
            return own
        try:
            return str(self.profile(self.profileOf(key)).get('asf_bot') or '').strip()
        except ValueError:
            return ''

    def setKeyBot(self, key, bot):
        self.platformEntry(key)['asf_bot'] = str(bot or '').strip()
        self.saveFarm()

    # ---- per site settings -------------------------------------------------

    def platformEntry(self, key):
        return self.farm['platforms'].setdefault(key, {'autostart': False, 'settings': {}})

    def platformSettings(self, key):
        return dict(self.platformEntry(key).get('settings', {}))

    def savePlatformSettings(self, key, values):
        self.platformEntry(key)['settings'] = values
        self.saveFarm()

    def autostart(self, key):
        return bool(self.platformEntry(key).get('autostart'))

    def setAutostart(self, key, value):
        self.platformEntry(key)['autostart'] = bool(value)
        self.saveFarm()

    # ---- web panel password ------------------------------------------------

    def hasPassword(self):
        return bool(self.farm['web'].get('password', {}).get('hash'))

    def setPassword(self, password):
        if len(password) < 6:
            raise ValueError("пароль короче 6 символов")
        self.farm['web']['password'] = hashPassword(password)
        # New password, new sessions: everyone signed in before is signed out.
        self.farm['web']['secret'] = secrets.token_hex(32)
        self.saveFarm()

    def checkPassword(self, password):
        return checkPassword(password, self.farm['web'].get('password'))

    def sessionSecret(self):
        if not self.farm['web'].get('secret'):
            self.farm['web']['secret'] = secrets.token_hex(32)
            self.saveFarm()
        return self.farm['web']['secret']

    # ---- running -----------------------------------------------------------

    def startAutostart(self):
        for key, platform in self.platforms.items():
            if self.autostart(key) and platform.configured():
                platform.start()

    def startTelegram(self):
        from steamgiftbot.farm.telegram import TelegramControl
        self.telegram = TelegramControl(self)
        self.telegram.start()

    def stopAll(self, wait=10):
        self.clockStop.set()
        if getattr(self, 'telegram', None) is not None:
            self.telegram.stop()
        for platform in self.platforms.values():
            platform.stop()
        deadline = time.time() + wait
        for platform in self.platforms.values():
            if platform.thread is not None:
                platform.thread.join(max(0.1, deadline - time.time()))

    # Telegram / Discord settings are the ones SteamGiftBot already has.
    def notify(self, text):
        try:
            config = sgSettings.load(self.configPath)
        except sgSettings.SettingsError:
            return ['config.ini не читается']
        if not notify.isConfigured(config):
            return ['уведомления не настроены']
        problems = notify.send(config, "Bot farm " + text)
        for problem in problems:
            log.warning(f"Уведомление не доставлено: {problem}")
        return problems
