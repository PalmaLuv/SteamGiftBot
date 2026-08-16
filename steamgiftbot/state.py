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

STATE_NAME = 'steamgiftbot-state.json'


def defaultPath(configPath):
    return Path(configPath).resolve().parent / STATE_NAME


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.announcedWins = set()

    # A missing or damaged file is not worth failing a run over: the worst that
    # happens is one repeated notification.
    def load(self):
        try:
            raw = self.path.read_text(encoding='utf-8')
        except OSError:
            return self

        try:
            stored = json.loads(raw)
        except ValueError:
            return self

        if isinstance(stored, dict):
            wins = stored.get('announced_wins')
            if isinstance(wins, list):
                self.announcedWins = {str(code) for code in wins}
        return self

    def save(self):
        payload = {'announced_wins': sorted(self.announcedWins)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        except OSError:
            return False
        return True

    def isNew(self, code):
        return code not in self.announcedWins

    def remember(self, code):
        self.announcedWins.add(code)
