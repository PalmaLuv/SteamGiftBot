#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Sources that only announce games you can keep for free.

Unlike a giveaway site there is nothing to enter and no points to spend: the
bot reads the list, tells you about anything new once, and you claim the game
yourself. Claiming stays with you on purpose; stores like Epic put a captcha
in front of it, and getting past that is not something this project does.
"""
from dataclasses import dataclass
from typing import Protocol

from steamgiftbot import notify
from steamgiftbot.console import log


@dataclass
class FreeGame:
    id        : str
    title     : str
    url       : str
    worth     : str = ''
    platforms : str = ''
    # As the source printed it; empty when it did not say.
    endDate   : str = ''

    def line(self):
        details = [part for part in (self.worth, self.platforms) if part]
        text = self.title + (f" ({', '.join(details)})" if details else '')
        if self.endDate:
            text += f", until {self.endDate}"
        return f"{text}\n{self.url}"


class FeedProvider(Protocol):
    # Shown to the user and credited in every message.
    name : str

    # What is free right now. None when the source could not be asked, which
    # is reported by the feed and otherwise ignored.
    def fetch(self) -> list[FreeGame] | None: ...


class FreeGameWatcher:
    def __init__(self, feed, config, state):
        self.feed   = feed
        self.config = config
        self.state  = state

    # One message for everything new, rather than one per game: the first run
    # can find a dozen at once.
    def announce(self):
        games = self.feed.fetch()
        if games is None:
            return []

        fresh = [game for game in games if self.state.isNewFreeGame(game.id)]
        # Forget offers that ended, so the state file does not grow for ever.
        self.state.keepFreeGames({game.id for game in games})
        if not fresh:
            self.state.save()
            return []

        for game in fresh:
            log(f"Free to keep: {game.title} {game.url}", "green")
            self.state.rememberFreeGame(game.id)
        self.state.save()

        if notify.isConfigured(self.config):
            text = (f"Free to keep right now (via {self.feed.name}):\n\n"
                    + "\n\n".join(game.line() for game in fresh))
            for problem in notify.send(self.config, text):
                log(f"Could not deliver the free games notification. {problem}", "yellow")
        return fresh
