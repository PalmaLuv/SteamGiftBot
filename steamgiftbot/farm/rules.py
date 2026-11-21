"""Rules every site in the farm shares: ready-made word filters, working hours,
daily limits, and the Steam library used to skip games already owned."""
import logging
import re
import threading
import time

from datetime import datetime, timedelta

import requests

from steamgiftbot.logging_setup import redactSecrets

log = logging.getLogger('botfarm')

# ---- word presets ------------------------------------------------------------

# Add-ons rather than games. Whole words only, so 'Backpack Hero' stays a game.
JUNK_WORDS = ('soundtrack', 'ost', 'original sound', 'artbook', 'art book', 'wallpaper',
              'wallpapers', 'dlc', 'season pass', 'expansion pass', 'pack', 'costume',
              'costumes', 'skin', 'skins', 'outfit', 'outfits', 'upgrade', 'booster',
              'supporter edition', 'cosmetic')

ADULT_WORDS = ('hentai', 'nsfw', 'sex', 'sexy', 'erotic', 'erotica', 'lewd', 'porn', 'nude',
               'nudity', 'waifu', 'uncensored', 'adult only', 'adults only', 'xxx')


def wordPattern(words, extra=''):
    alternatives = '|'.join(re.escape(word).replace(r'\ ', r'\s+') for word in words)
    return re.compile(rf'(?<![\w])(?:{alternatives})(?![\w]){extra}', re.IGNORECASE)


JUNK  = wordPattern(JUNK_WORDS)
ADULT = wordPattern(ADULT_WORDS, r'|(?<!\d)18\+')


def containsAny(name, words):
    lowered = (name or '').lower()
    return any(word and word.lower() in lowered for word in words)


def presetReason(name, skipJunk=False, skipAdult=False):
    if skipJunk and JUNK.search(name or ''):
        return 'DLC / саундтрек / пак'
    if skipAdult and ADULT.search(name or ''):
        return '18+'
    return None


# ---- working hours -----------------------------------------------------------

WINDOW = re.compile(r'^(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?$')


def parseHours(text):
    """'08:00-23:00' or '9-13, 18:30-02:00' -> [(startMinute, endMinute)].
    Empty means round the clock. A window may run past midnight."""
    windows = []
    for part in re.split(r'[,;]', text or ''):
        part = part.strip()
        if not part:
            continue
        found = WINDOW.match(part)
        if not found:
            raise ValueError(f"не понимаю «{part}», нужно вида 08:00-23:00")
        h1, m1, h2, m2 = (int(value or 0) for value in found.groups())
        if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
            raise ValueError(f"нет такого времени: «{part}»")
        start, end = (h1 * 60 + m1) % 1440, (h2 * 60 + m2) % 1440
        if start == end:
            raise ValueError(f"окно «{part}» пустое")
        windows.append((start, end))
    return windows


def normalizeHours(text):
    windows = parseHours(text)
    return ', '.join(f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for s, e in windows)


def inWindow(minute, start, end):
    return start <= minute < end if start < end else (minute >= start or minute < end)


def secondsUntilOpen(windows, now):
    """0 inside a window (or with no windows at all), else seconds until the
    nearest one opens. now is an aware datetime in the farm's time zone."""
    if not windows:
        return 0
    minute = now.hour * 60 + now.minute
    if any(inWindow(minute, start, end) for start, end in windows):
        return 0
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    best = None
    for start, _end in windows:
        opens = midnight + timedelta(minutes=start)
        if opens <= now:
            opens += timedelta(days=1)
        wait = (opens - now).total_seconds()
        best = wait if best is None else min(best, wait)
    return max(1, int(best))


# ---- Steam library -----------------------------------------------------------

STEAM_API = 'https://api.steampowered.com'
PROFILE   = re.compile(r'steamcommunity\.com/(profiles|id)/([^/?#]+)', re.IGNORECASE)


def normalizeTitle(name):
    text = re.sub(r'[™®©]', '', (name or '').lower())
    text = re.sub(r'[^\w]+', ' ', text)
    return ' '.join(text.split())


class OwnedGames:
    def __init__(self, games):
        self.appids = {int(game['appid']) for game in games if game.get('appid')}
        self.names  = {normalizeTitle(game.get('name')) for game in games if game.get('name')}

    def __len__(self):
        return len(self.appids)

    def has(self, appid=None, name=None):
        if appid is not None and int(appid) in self.appids:
            return True
        return bool(name) and normalizeTitle(name) in self.names


class SteamLibrary:
    """The user's owned games from the Steam Web API, refreshed every few hours.
    Any trouble means 'do not filter', never 'stop entering'."""

    TTL       = 6 * 3600
    RETRY     = 30 * 60
    TIMEOUT   = 20

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.lock    = threading.Lock()
        self.cache   = {}       # (key, profile) -> (fetched at, OwnedGames | None)
        self.wishCache = {}     # profile -> (fetched at, set of app ids | None)
        self.problem = ''

    def resolve(self, key, profile):
        profile = (profile or '').strip()
        found = PROFILE.search(profile)
        if found:
            kind, value = found.groups()
            if kind.lower() == 'profiles':
                return value
            profile = value
        if re.fullmatch(r'\d{17}', profile):
            return profile
        answer = self.call('/ISteamUser/ResolveVanityURL/v1/', key=key, vanityurl=profile)
        steamid = (answer.get('response') or {}).get('steamid')
        if not steamid:
            raise ValueError(f"не нашёл профиль Steam «{profile}»")
        return steamid

    def call(self, path, **params):
        response = self.session.get(STEAM_API + path, params=params, timeout=self.TIMEOUT)
        if response.status_code in (401, 403):
            raise ValueError("Steam не принял API-ключ")
        response.raise_for_status()
        return response.json()

    def fetch(self, key, profile):
        steamid = self.resolve(key, profile)
        answer = self.call('/IPlayerService/GetOwnedGames/v1/', key=key, steamid=steamid,
                           include_appinfo=1, include_played_free_games=1)
        games = (answer.get('response') or {}).get('games')
        if games is None:
            raise ValueError("Steam не отдал список игр: откройте «Игровые данные» "
                             "в настройках приватности профиля")
        return OwnedGames(games)

    # Wishlisted app ids; the wishlist service needs no key, only a public
    # wishlist. None on any trouble, like owned().
    def wishlist(self, key, profile):
        if not profile:
            return None
        with self.lock:
            cached = self.wishCache.get(profile)
            age = time.time() - cached[0] if cached else None
            if cached and age < (self.TTL if cached[1] is not None else self.RETRY):
                return cached[1]
            try:
                steamid = self.resolve(key, profile)
                answer = self.call('/IWishlistService/GetWishlist/v1/', steamid=steamid)
                items = (answer.get('response') or {}).get('items')
                if items is None:
                    raise ValueError("список желаемого пуст или скрыт настройками приватности")
                apps = {int(item['appid']) for item in items if item.get('appid')}
                log.info(f"Список желаемого Steam: {len(apps)} игр")
            except Exception as error:
                apps = cached[1] if cached else None
                self.problem = redactSecrets(str(error))
                log.warning(f"Список желаемого не загружен: {self.problem}")
            self.wishCache[profile] = (time.time(), apps)
            return apps

    def owned(self, key, profile):
        if not key or not profile:
            return None
        with self.lock:
            cached = self.cache.get((key, profile))
            age = time.time() - cached[0] if cached else None
            if cached and age < (self.TTL if cached[1] is not None else self.RETRY):
                return cached[1]
            try:
                games = self.fetch(key, profile)
                self.problem = ''
                log.info(f"Библиотека Steam: {len(games)} игр")
            except Exception as error:
                games = cached[1] if cached else None
                # requests' error texts hold the URL, and the API key is in
                # its query string; the panel shows this as steam_status.
                self.problem = redactSecrets(str(error))
                log.warning(f"Библиотека Steam не загружена: {self.problem}")
            self.cache[(key, profile)] = (time.time(), games)
            return games


def localNow(zone):
    return datetime.now(zone)
