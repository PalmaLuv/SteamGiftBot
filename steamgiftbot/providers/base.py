#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""What a giveaway site has to offer for the bot to work it.

The runner (bot.py) owns everything that is the same on every site: the walk
over pages, the filters, dry runs, pacing, waiting for points, the summary. A
provider owns the site: signing in, reading its pages, spending its points,
finding its wins. Adding a site means writing one class with the methods below
and registering it in providers/__init__.py.

Sites that only announce free games (GamerPower, the Epic store) have nothing
to enter and no points to spend; they belong to a separate, smaller interface
that feeds notifications, not to this one.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from steamgiftbot.giveaway import Giveaway
from steamgiftbot.wins import Win


# A listing row that could not be read. Carries a little of its text so the
# user can see what the site sent instead.
@dataclass
class Unreadable:
    sample: str


class Outcome(Enum):
    ENTERED      = 'entered'
    REJECTED     = 'rejected'
    RATE_LIMITED = 'rate limited'
    FAILED       = 'failed'


@dataclass
class EntryResult:
    outcome : Outcome
    # Why the site said no, for REJECTED.
    message : str = ''
    # Seconds the site asked us to wait, for RATE_LIMITED.
    wait    : int = 0


class GiveawayProvider(Protocol):
    # Shown to the user, e.g. 'SteamGifts'.
    name   : str
    # The balance as the site last reported it. The runner lowers it itself
    # during a dry run.
    points : int

    # Signs in (or checks the session still works) and reads the balance.
    # Raises SessionExpired when the user has to sign in again, and
    # SteamGiftError when the site cannot be reached at all.
    def refresh(self) -> None: ...

    # One page of the listing. None when the page could not be loaded, an
    # empty list once the listing is exhausted.
    def listGiveaways(self, page: int) -> list[Giveaway | Unreadable] | None: ...

    # Spends points on one giveaway. Never sleeps: a rate limit is reported
    # back with the wait, and the runner does the waiting.
    def enter(self, giveaway: Giveaway) -> EntryResult: ...

    # (wins, recognised). recognised is False when the page did not look the
    # way the provider expects. SessionExpired passes through.
    def fetchWins(self) -> tuple[list[Win], bool]: ...

    # Whether the Steam app behind a giveaway has trading cards: True, False,
    # or None when that could not be found out.
    def hasCards(self, appid: int) -> bool | None: ...
