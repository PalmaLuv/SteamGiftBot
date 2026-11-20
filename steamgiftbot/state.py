#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""What the bot remembers between runs.

Only one thing so far: which wins have already been announced, so a scheduled
run does not send the same 'you won' message every twelve hours.
"""
import json

from pathlib import Path

from steamgiftbot.console import log

STATE_NAME = 'steamgiftbot-state.json'


def defaultPath(configPath):
    return Path(configPath).resolve().parent / STATE_NAME


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.announcedWins = set()
        # Free game offers already announced, by their id at the source.
        self.announcedFreeGames = set()
        # True until a state file has actually been read: the bot remembers
        # nothing, so whatever is already on the won page is history, not news.
        self.fresh = True

    # A missing or damaged file is not worth failing a run over. Damage is still
    # said out loud, or a file that breaks every time would go unexplained.
    def load(self):
        try:
            raw = self.path.read_text(encoding='utf-8')
        except FileNotFoundError:
            # The first run: nothing announced yet.
            return self
        except OSError as error:
            log(f"Could not read {self.path}: {error}. Wins already on the page will be "
                "remembered again rather than announced.", "yellow")
            return self

        try:
            stored = json.loads(raw)
        except ValueError:
            log(f"{self.path} is damaged and was ignored. Wins already on the page will be "
                "remembered again rather than announced.", "yellow")
            return self

        if isinstance(stored, dict):
            self.fresh = False
            wins = stored.get('announced_wins')
            if isinstance(wins, list):
                self.announcedWins = {str(code) for code in wins}
            freeGames = stored.get('announced_free_games')
            if isinstance(freeGames, list):
                self.announcedFreeGames = {str(code) for code in freeGames}
        return self

    def save(self):
        payload = {'announced_wins': sorted(self.announcedWins)}
        # Left out until used, so a file written by an older version reads the same.
        if self.announcedFreeGames:
            payload['announced_free_games'] = sorted(self.announcedFreeGames)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        except OSError as error:
            log(f"Could not save {self.path}: {error}. "
                "These wins may be announced again next run.", "yellow")
            return False
        return True

    def isNew(self, code):
        return code not in self.announcedWins

    def remember(self, code):
        self.announcedWins.add(code)

    def isNewFreeGame(self, code):
        return code not in self.announcedFreeGames

    def rememberFreeGame(self, code):
        self.announcedFreeGames.add(code)

    # An offer that is no longer listed has ended and will not come back.
    def keepFreeGames(self, activeCodes):
        self.announcedFreeGames &= set(activeCodes)
