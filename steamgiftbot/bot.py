#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""The run itself: walk the listing, pick giveaways, spend points, report.

Nothing in here knows which site it is talking to; that is the provider's job
(see providers/base.py). SteamGifts is the provider unless another is given.
"""
from random import randint as rand
from time import sleep

from steamgiftbot import filters, notify
from steamgiftbot.console import countdown, log
from steamgiftbot.errors import SessionExpired, SteamGiftError
from steamgiftbot.feeds import FreeGameWatcher
from steamgiftbot.feeds.gamerpower import GamerPowerFeed
from steamgiftbot.providers import steamgifts
from steamgiftbot.providers.base import Outcome, Unreadable
from steamgiftbot.settings import DEFAULT_CONFIG_PATH, hint
from steamgiftbot.state import State, defaultPath
from steamgiftbot.stats import RunStats
from steamgiftbot.winwatch import WinWatcher

# Kept importable from here: they were public before the split.
from steamgiftbot.providers.steamgifts import (  # noqa: F401
    CHALLENGE_MARKERS, CHALLENGE_MESSAGE, INFO_PATH, RATE_LIMIT_WAIT, TIMEOUT, URL, info,
    isChallenge)

POINTS_WAIT = info['pointsWaitSeconds']

# Pacing between entries.
ENTRY_DELAY = tuple(info['entryDelaySeconds'])

__all__ = ['SteamGift', 'SteamGiftError', 'SessionExpired', 'sessionAdvice']


def sessionAdvice():
    return ("Your SteamGifts session has expired, so the bot stopped.\n"
            "Sign in at steamgifts.com, copy the new PHPSESSID cookie and run "
            f"'{hint('--setup')}'.")


class SteamGift :
    def __init__(self, config, statePath=None, provider=None):
        self.config     = config
        self.pinned     = config.pinned
        self.min_points = int(config.min_points)
        # One pass and out, for cron or Task Scheduler. Never sleeps for points.
        self.once       = bool(config.once)
        # Walk and report, but never spend a point.
        self.dryRun     = bool(config.dry_run)
        self.pointsWait = POINTS_WAIT if config.points_wait is None else config.points_wait

        self.provider   = provider or steamgifts.SteamGiftsProvider(config)

        self.running    = True
        self.stats      = RunStats()
        self.warnedUnreadable = False

        # Watching the won page is on unless it was turned off.
        self.checkWins  = config.check_wins is not False
        self.state      = State(statePath or defaultPath(DEFAULT_CONFIG_PATH)).load()
        self.watcher    = WinWatcher(self.provider, config, self.state, self.stats)

        # Free games elsewhere: announced only, never claimed. Off unless asked for.
        self.freeGames  = (FreeGameWatcher(GamerPowerFeed(config.free_games), config, self.state)
                           if config.free_games else None)

    # The provider holds the session and the balance; these keep the old
    # spelling working for callers and tests written before the split.
    @property
    def points(self):
        return self.provider.points

    @points.setter
    def points(self, value):
        self.provider.points = value

    @property
    def session(self):
        return self.provider.session

    @session.setter
    def session(self, value):
        self.provider.session = value

    @property
    def xsrfToken(self):
        return self.provider.xsrfToken

    def GetSoupFromPage(self, url):
        return self.provider.getSoup(url)

    def updateInfo(self):
        self.provider.refresh()

    def stop(self):
        self.running = False

    # Counts down until the balance is worth checking again. Returns early on stop().
    def waitForPoints(self):
        log(f"Sleeping to get more points. We have {self.points} points."
            + f"\nTo continue, you need at least {self.min_points}", "magenta")
        for remaining in range(self.pointsWait, 0, -1):
            if not self.running:
                break
            countdown(f"There are {remaining} seconds left.")
            sleep(1)
        countdown(None)

    # A row the parser could not read is counted every time, and shown once per
    # run: a redesign of the listing would otherwise look like a quiet day.
    def noteUnreadable(self, row):
        self.stats.skip(filters.UNREADABLE)
        if self.warnedUnreadable:
            return
        self.warnedUnreadable = True
        log(f"Could not read a giveaway row, the {self.provider.name} layout may have "
            f"changed: {row.sample!r}", "yellow")

    def enter(self, giveaway):
        result = self.provider.enter(giveaway)
        if result.outcome is Outcome.ENTERED:
            self.stats.entry(giveaway.cost)
            return True
        if result.outcome is Outcome.RATE_LIMITED:
            log(f"{self.provider.name} asked us to slow down. "
                f"Waiting {result.wait} seconds.", "yellow")
            self.stats.rateLimit()
            sleep(result.wait)
        elif result.outcome is Outcome.REJECTED:
            log(f"Entry rejected: {result.message}", "yellow")
            self.stats.rejection()
        return False

    # Walks the giveaway pages. Returns as soon as the balance runs out or the
    # listing is exhausted; start() decides whether to go round again.
    def getGameContent(self, page=1):
        _page = page
        while self.running:
            log(f"Getting games from page {_page}", "magenta")

            listing = self.provider.listGiveaways(_page)
            if listing is None:
                return

            if not listing:
                if _page == 1:
                    raise SteamGiftError("Page is empty. Please, choose another type.")
                log("No giveaways left on this page, starting over.", "magenta")
                return

            for giveaway in listing:
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

                if isinstance(giveaway, Unreadable):
                    self.noteUnreadable(giveaway)
                    continue

                reason = filters.reasonToSkip(giveaway, self.config, self.points,
                                              hasCards=self.provider.hasCards)
                if reason is not None:
                    self.stats.skip(reason)
                    if reason in (filters.NOT_ENOUGH, filters.NO_CARDS, filters.CARDS_UNKNOWN):
                        log(f"Skipping {giveaway.name}: {reason}", "red")
                    continue

                if self.dryRun:
                    # Spend the points on paper, so the rest of the walk behaves
                    # the way a real run would.
                    log(f"Would enter {giveaway.name} for {giveaway.cost}P", "cyan")
                    self.points -= giveaway.cost
                    self.stats.entry(giveaway.cost)
                    continue

                if self.enter(giveaway):
                    log(f"One more game {giveaway.name}", "green")
                    sleep(rand(*ENTRY_DELAY))
            _page  += 1

    def announceWins(self):
        if not self.checkWins:
            return []
        return self.watcher.announce()

    def announceFreeGames(self):
        if self.freeGames is None:
            return []
        return self.freeGames.announce()

    # Everything worth telling the user that is not an entry of ours.
    def announce(self):
        self.announceWins()
        self.announceFreeGames()

    def report(self, extra=None):
        summary = self.stats.summary()
        if self.dryRun:
            summary = "Dry run: nothing was actually entered.\n" + summary
        log("\n" + summary, "white")
        if not notify.isConfigured(self.config):
            return
        if self.dryRun:
            # A trial run stays on the screen; --notify-test checks the chat.
            log("Dry run: no message was sent. Use --notify-test to check "
                "Telegram or Discord.", "cyan")
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
            self.announce()
            while self.running:
                self.getGameContent()
                if self.once:
                    log("Single run finished.", "green")
                    break
                if self.running:
                    # A cycle ends after a wait for points, so this is roughly a
                    # quarter hour apart: often enough not to miss a win.
                    self.announce()
                    self.updateInfo()
        except SessionExpired as error:
            # Checked before SteamGiftError: it is a subclass of it.
            log(str(error), "red")
            advice = sessionAdvice()
            log(advice, "yellow")
            self.report(extra=advice)
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
