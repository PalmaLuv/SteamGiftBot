#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""GamerPower: a public, keyless list of free games across stores.

https://www.gamerpower.com/api-read asks for two things in return: credit
GamerPower wherever the data is shown, and stay under ten requests a second.
The bot asks once per cycle and names GamerPower in every message.
"""
import requests

from steamgiftbot.console import log
from steamgiftbot.feeds import FreeGame

API     = "https://www.gamerpower.com/api/filter"
TIMEOUT = 15

# GamerPower answers 201 with a status object, not an empty list, when
# nothing matches.
NOTHING_ACTIVE = 201


class GamerPowerFeed:
    name = 'GamerPower'

    def __init__(self, platforms, session=None):
        self.platforms = tuple(platforms)
        self.session   = session

    def fetch(self):
        getter = self.session.get if self.session else requests.get
        # Only full games: loot and beta keys are not what anyone asked for.
        params = {'platform': '.'.join(self.platforms), 'type': 'game'}
        try:
            response = getter(API, params=params, timeout=TIMEOUT)
        except requests.RequestException as error:
            log(f"Could not ask GamerPower for free games: {error}", "yellow")
            return None

        if response.status_code == NOTHING_ACTIVE:
            return []
        if response.status_code != 200:
            log(f"GamerPower answered HTTP {response.status_code}", "yellow")
            return None

        try:
            body = response.json()
        except ValueError:
            log("GamerPower sent something that was not JSON", "yellow")
            return None
        if not isinstance(body, list):
            return []

        return [game for game in map(toFreeGame, body) if game is not None]


def toFreeGame(entry):
    if not isinstance(entry, dict) or entry.get('status', 'Active') != 'Active':
        return None
    url = str(entry.get('open_giveaway_url') or entry.get('gamerpower_url') or '')
    # The link ends up in a chat message; only plain https ones are passed on.
    if entry.get('id') is None or not url.startswith('https://'):
        return None

    title = str(entry.get('title') or 'A free game').strip()
    title = title.removesuffix(' Giveaway')
    endDate = str(entry.get('end_date') or '')
    worth = str(entry.get('worth') or '')

    return FreeGame(
        id        = str(entry['id']),
        title     = title,
        url       = url,
        worth     = '' if worth == 'N/A' else worth,
        platforms = str(entry.get('platforms') or ''),
        endDate   = '' if endDate == 'N/A' else endDate,
    )
