#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
import json

import requests

from pathlib import Path
from random import randint as rand

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from time import sleep
from urllib3.util import Retry

from steamgiftbot import filters, notify, wins
from steamgiftbot.console import log
from steamgiftbot.giveaway import parseRow
from steamgiftbot.settings import DEFAULT_CONFIG_PATH
from steamgiftbot.state import State, defaultPath
from steamgiftbot.stats import RunStats
from steamgiftbot.steam_api import get_game_info

# Resolved next to this module, so the bot can be started from any directory.
INFO_PATH = Path(__file__).resolve().parent / 'info.json'

with INFO_PATH.open('r', encoding='utf-8') as infoFile:
    info = json.load(infoFile)

URL         = info['URL']
TIMEOUT     = info['timeout']
POINTS_WAIT = info['pointsWaitSeconds']

# Pacing between entries, and how long to hold off when SteamGifts says 429.
ENTRY_DELAY      = tuple(info['entryDelaySeconds'])
RATE_LIMIT_WAIT  = info['rateLimitWaitSeconds']

# Words that mark a Cloudflare interstitial rather than a real SteamGifts page.
CHALLENGE_MARKERS = ('just a moment', 'challenges.cloudflare.com', 'cf-browser-verification')

CHALLENGE_MESSAGE = (
    "SteamGifts answered with a Cloudflare check instead of the site. "
    "The bot cannot get past that on its own; open steamgifts.com in a browser "
    "and try again once the site lets you through.")


# Raised when the bot cannot continue: bad cookie, dead session, empty filter.
class SteamGiftError(Exception):
    pass


# The cookie stopped working. Told apart from the rest because it is the one
# failure the user has to act on, and the one worth a message on its own.
class SessionExpired(SteamGiftError):
    pass


SESSION_ADVICE = (
    "Your SteamGifts session has expired, so the bot stopped.\n"
    "Sign in at steamgifts.com, copy the new PHPSESSID cookie and run "
    "'python main.py --setup'.")


class SteamGift :
    def __init__(self, config, statePath=None):
        self.config     = config
        self.cookie     = { 'PHPSESSID' : config.cookie }
        self.type       = config.gift_type
        self.pinned     = config.pinned
        self.min_points = int(config.min_points)
        # One pass and out, for cron or Task Scheduler. Never sleeps for points.
        self.once       = bool(config.once)
        # Walk and report, but never spend a point.
        self.dryRun     = bool(config.dry_run)
        self.pointsWait = POINTS_WAIT if config.points_wait is None else config.points_wait

        self.baseURL   = URL
        self.filterURL = info['filterURL']

        self.points     = 0
        self.xsrfToken  = None
        self.running    = True
        self.stats      = RunStats()

        # Watching the won page is on unless it was turned off.
        self.checkWins = config.check_wins is not False
        self.state     = State(statePath or defaultPath(DEFAULT_CONFIG_PATH)).load()

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

    def stop(self):
        self.running = False

    def GetSoupFromPage(self, url):
        try:
            res_soup = self.session.get(url, timeout=TIMEOUT)
        except requests.RequestException as error:
            log(f"Network error while loading the page: {error}", "red")
            return None

        if res_soup.status_code != 200:
            body = (res_soup.text or '').lower()
            if any(marker in body for marker in CHALLENGE_MARKERS):
                raise SteamGiftError(CHALLENGE_MESSAGE)
            log(f"SteamGifts answered with HTTP {res_soup.status_code}", "red")
            return None

        return BeautifulSoup(res_soup.text, 'html.parser')

    def updateInfo(self):
        soup = self.GetSoupFromPage(self.baseURL)
        if soup is None:
            raise SteamGiftError("Could not reach SteamGifts.")

        token  = soup.find('input', {'name': 'xsrf_token'})
        points = soup.find('span', {'class': 'nav__points'})
        if token is None or points is None:
            raise SessionExpired("Cookie is not valid, or the SteamGifts layout has changed.")

        self.xsrfToken = token['value']
        self.points    = int(points.text.replace(',', '').strip())

    def entryGIFT(self, id, cost):
        payload = {
        'xsrf_token' : self.xsrfToken,
        'do'        : 'entry_insert',
        'code'      : id
        }

        try:
            response = self.session.post(info['ajaxURL'], data=payload, timeout=TIMEOUT)
        except requests.RequestException as error:
            log(f"Network error while entering the giveaway: {error}", "red")
            return False

        # The retry adapter deliberately leaves POST alone, so a rate limit on an
        # entry has to be handled here. Wait as long as the site asks.
        if response.status_code == 429:
            wait = self.retryAfter(response)
            log(f"SteamGifts asked us to slow down. Waiting {wait} seconds.", "yellow")
            self.stats.rateLimit()
            sleep(wait)
            return False

        try:
            jsonData = response.json()
        except ValueError as error:
            # An HTML body here means the session died or we are being rate limited.
            body = (response.text or '').lower()
            if any(marker in body for marker in CHALLENGE_MARKERS):
                raise SteamGiftError(CHALLENGE_MESSAGE) from error
            raise SessionExpired("SteamGifts returned an unexpected answer. "
                                 "The session has probably expired.") from error

        if jsonData.get('type') != 'success':
            log(f"Entry rejected: {jsonData.get('msg', 'unknown reason')}", "yellow")
            self.stats.rejection()
            return False

        # Trust the balance reported by the server; fall back to local math.
        if 'points' in jsonData:
            self.points = int(jsonData['points'])
        else:
            self.points = max(self.points - cost, 0)
        self.stats.entry(cost)
        return True

    # Honours Retry-After when the site sends one, falls back to our own wait.
    def retryAfter(self, response):
        header = response.headers.get('Retry-After') if hasattr(response, 'headers') else None
        try:
            return max(1, int(header))
        except (TypeError, ValueError):
            return RATE_LIMIT_WAIT

    # Counts down until the balance is worth checking again. Returns early on stop().
    def waitForPoints(self):
        log(f"Sleeping to get more points. We have {self.points} points."
            + f"\nTo continue, you need at least {self.min_points}", "magenta")
        for remaining in range(self.pointsWait, 0, -1):
            if not self.running:
                return
            print(f"The are {remaining} seconds left.\t\r", end='')
            sleep(1)
        print()

    # Walks the giveaway pages. Returns as soon as the balance runs out or the
    # listing is exhausted; start() decides whether to go round again.
    def getGameContent(self, page=1):
        _page = page
        while self.running:
            log(f"Getting games from page {_page}", "magenta")

            filtered_url = self.filterURL[self.type] % _page
            paginated_url = f"{self.baseURL}/giveaways/{filtered_url}"
            soup = self.GetSoupFromPage(paginated_url)
            if soup is None:
                return

            game_list = soup.find_all('div', {'class': 'giveaway__row-inner-wrap'})
            if not len(game_list):
                if _page == 1:
                    raise SteamGiftError("Page is empty. Please, choose another type.")
                log("No giveaways left on this page, starting over.", "magenta")
                return

            for item in game_list:
                if not self.running:
                    return

                if self.points == 0 or self.points < self.min_points:
                    if self.once:
                        log(f"Out of points: {self.points} left, {self.min_points} required. "
                            "Finishing because a single run was requested.", "magenta")
                        self.stop()
                        return
                    self.waitForPoints()
                    return

                giveaway = parseRow(item)
                if giveaway is None:
                    continue

                reason = filters.reasonToSkip(giveaway, self.config, self.points,
                                              hasCards=get_game_info)
                if reason is not None:
                    self.stats.skip(reason)
                    if reason in (filters.NOT_ENOUGH, filters.NO_CARDS):
                        log(f"Skipping {giveaway.name}: {reason}", "red")
                    continue

                if self.dryRun:
                    # Spend the points on paper, so the rest of the walk behaves
                    # the way a real run would.
                    log(f"Would enter {giveaway.name} for {giveaway.cost}P", "cyan")
                    self.points -= giveaway.cost
                    self.stats.entry(giveaway.cost)
                    continue

                if self.entryGIFT(giveaway.code, giveaway.cost):
                    log(f"One more game {giveaway.name}", "green")
                    sleep(rand(*ENTRY_DELAY))
            _page  += 1

    # Looks at the won page and announces anything that was not announced
    # before. Never raises: missing a win is bad, failing the run over it is
    # worse.
    def announceWins(self):
        if not self.checkWins:
            return []

        try:
            soup = self.GetSoupFromPage(self.baseURL + wins.WON_PATH)
        except SteamGiftError as error:
            log(f"Could not check for wins: {error}", "yellow")
            return []
        if soup is None:
            return []

        found, recognised = wins.parseWonPage(soup)
        if not recognised:
            log("The won giveaways page did not look the way the bot expects, "
                "so wins cannot be checked. Everything else keeps working.", "yellow")
            return []

        fresh = [win for win in found if self.state.isNew(win.code)]
        if not fresh:
            return []

        for win in fresh:
            log(f"You won {win.name}! {win.url}", "green")
            self.state.remember(win.code)
            if notify.isConfigured(self.config):
                for problem in notify.send(self.config, wins.announcement(win)):
                    log(f"Could not deliver the win notification. {problem}", "yellow")

        self.state.save()
        self.stats.wins(len(fresh))
        return fresh

    def report(self, extra=None):
        summary = self.stats.summary()
        if self.dryRun:
            summary = "Dry run: nothing was actually entered.\n" + summary
        log("\n" + summary, "white")
        if not notify.isConfigured(self.config):
            return
        text = summary if extra is None else f"{extra}\n\n{summary}"
        for problem in notify.send(self.config, "SteamGiftBot\n" + text):
            log(f"Could not deliver the notification. {problem}", "yellow")

    def start(self):
        try:
            self.updateInfo()
            if self.points > 0:
                log(f"You currently have balance {self.points} points","white")
            log("Script running", "green")
            # Outer loop replaces the old recursive restart, which grew the call
            # stack every time the bot waited for points.
            self.announceWins()
            while self.running:
                self.getGameContent()
                if self.once:
                    log("Single run finished.", "green")
                    break
                if self.running:
                    # A cycle ends after a wait for points, so this is roughly a
                    # quarter hour apart: often enough not to miss a win.
                    self.announceWins()
                    self.updateInfo()
        except SessionExpired as error:
            # Checked before SteamGiftError: it is a subclass of it.
            log(str(error), "red")
            log(SESSION_ADVICE, "yellow")
            self.report(extra=SESSION_ADVICE)
            return 1
        except SteamGiftError as error:
            log(str(error), "red")
            self.report(extra=f"The run stopped: {error}")
            return 1
        except KeyboardInterrupt:
            self.stop()
            log("\nStopped by user. Bye!", "white")
        self.report()
        return 0
