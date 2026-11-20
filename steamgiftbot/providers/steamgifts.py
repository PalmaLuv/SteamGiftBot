#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""steamgifts.com: the session, its pages, its points and its wins."""
import json

import requests

from pathlib import Path

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from steamgiftbot import steam_api, wins
from steamgiftbot.console import log
from steamgiftbot.errors import SessionExpired, SteamGiftError
from steamgiftbot.giveaway import parseRow
from steamgiftbot.providers.base import EntryResult, Outcome, Unreadable

# Resolved next to the package, so the bot can be started from any directory.
INFO_PATH = Path(__file__).resolve().parent.parent / 'info.json'

with INFO_PATH.open('r', encoding='utf-8') as infoFile:
    info = json.load(infoFile)

URL             = info['URL']
TIMEOUT         = info['timeout']
# How long to hold off when SteamGifts says 429 without saying for how long.
RATE_LIMIT_WAIT = info['rateLimitWaitSeconds']

# Words that mark a Cloudflare interstitial rather than a real SteamGifts page.
CHALLENGE_MARKERS = ('just a moment', 'challenges.cloudflare.com', 'cf-browser-verification')

CHALLENGE_MESSAGE = (
    "SteamGifts answered with a Cloudflare check instead of the site. "
    "The bot cannot get past that on its own; open steamgifts.com in a browser "
    "and try again once the site lets you through.")


def isChallenge(text):
    body = (text or '').lower()
    return any(marker in body for marker in CHALLENGE_MARKERS)


# Honours Retry-After when the site sends one, falls back to our own wait.
def retryAfter(response):
    header = response.headers.get('Retry-After') if hasattr(response, 'headers') else None
    try:
        return max(1, int(header))
    except (TypeError, ValueError):
        return RATE_LIMIT_WAIT


class SteamGiftsProvider:
    name = 'SteamGifts'

    def __init__(self, config):
        self.cookie    = {'PHPSESSID': config.cookie}
        self.type      = config.gift_type
        self.baseURL   = URL
        self.filterURL = info['filterURL']

        self.points    = 0
        self.xsrfToken = None

        # Built once, up front: every request below goes through it.
        self.session = self.requestsRetrySession()

    def requestsRetrySession(self, retries=5, backoffFactor=0.3):
        session = requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoffFactor,
            # 429 included so urllib3 honours Retry-After instead of hammering.
            # POST is intentionally left out of the retried methods: replaying an
            # entry could burn points twice.
            status_forcelist=(429, 500, 502, 503, 504)
        )
        session.headers.update({'User-Agent': info['userAgent']})
        session.cookies.update(self.cookie)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount(info['http'], adapter)
        session.mount(info['https'], adapter)
        return session

    def getSoup(self, url):
        try:
            response = self.session.get(url, timeout=TIMEOUT)
        except requests.RequestException as error:
            log(f"Network error while loading the page: {error}", "red")
            return None

        if response.status_code != 200:
            if isChallenge(response.text):
                raise SteamGiftError(CHALLENGE_MESSAGE)
            log(f"SteamGifts answered with HTTP {response.status_code}", "red")
            return None

        return BeautifulSoup(response.text, 'html.parser')

    def refresh(self):
        soup = self.getSoup(self.baseURL)
        if soup is None:
            raise SteamGiftError("Could not reach SteamGifts.")

        token  = soup.find('input', {'name': 'xsrf_token'})
        points = soup.find('span', {'class': 'nav__points'})
        if token is None or points is None:
            raise SessionExpired("Cookie is not valid, or the SteamGifts layout has changed.")

        self.xsrfToken = token['value']
        self.points    = int(points.text.replace(',', '').strip())

    def listGiveaways(self, page):
        filtered = self.filterURL[self.type] % page
        soup = self.getSoup(f"{self.baseURL}/giveaways/{filtered}")
        if soup is None:
            return None

        found = []
        for row in soup.find_all('div', {'class': 'giveaway__row-inner-wrap'}):
            giveaway = parseRow(row)
            if giveaway is None:
                giveaway = Unreadable(' '.join(row.get_text(' ', strip=True).split())[:120])
            found.append(giveaway)
        return found

    def enter(self, giveaway):
        payload = {
            'xsrf_token' : self.xsrfToken,
            'do'         : 'entry_insert',
            'code'       : giveaway.code,
        }

        try:
            response = self.session.post(info['ajaxURL'], data=payload, timeout=TIMEOUT)
        except requests.RequestException as error:
            log(f"Network error while entering the giveaway: {error}", "red")
            return EntryResult(Outcome.FAILED)

        # The retry adapter deliberately leaves POST alone, so a rate limit on an
        # entry has to be handled by whoever called us. Say how long to wait.
        if response.status_code == 429:
            return EntryResult(Outcome.RATE_LIMITED, wait=retryAfter(response))

        try:
            jsonData = response.json()
        except ValueError as error:
            # An HTML body here means the session died or we are being rate limited.
            if isChallenge(response.text):
                raise SteamGiftError(CHALLENGE_MESSAGE) from error
            raise SessionExpired("SteamGifts returned an unexpected answer. "
                                 "The session has probably expired.") from error

        if jsonData.get('type') != 'success':
            return EntryResult(Outcome.REJECTED, message=jsonData.get('msg', 'unknown reason'))

        # Trust the balance reported by the server; fall back to local math.
        if 'points' in jsonData:
            self.points = int(jsonData['points'])
        else:
            self.points = max(self.points - giveaway.cost, 0)
        return EntryResult(Outcome.ENTERED)

    def fetchWins(self):
        soup = self.getSoup(self.baseURL + wins.WON_PATH)
        if soup is None:
            return [], True
        return wins.parseWonPage(soup, self.baseURL)

    def hasCards(self, appid):
        return steam_api.get_game_info(appid)
