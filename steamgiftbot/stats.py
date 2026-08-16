#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""What happened during a run, for the closing summary and the notification."""
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class RunStats:
    entered     : int = 0
    rejected    : int = 0
    rateLimited : int = 0
    pointsSpent : int = 0
    won         : int = 0
    skipped     : Counter = field(default_factory=Counter)

    def entry(self, cost):
        self.entered += 1
        self.pointsSpent += cost

    def rejection(self):
        self.rejected += 1

    def rateLimit(self):
        self.rateLimited += 1

    def wins(self, count):
        self.won += count

    def skip(self, reason):
        self.skipped[reason] += 1

    def summary(self):
        lines = [f"Entered {self.entered} giveaways for {self.pointsSpent} points."]
        if self.won:
            lines.insert(0, f"You won {self.won} giveaways!")
        if self.rejected:
            lines.append(f"SteamGifts turned down {self.rejected} entries.")
        if self.rateLimited:
            lines.append(f"Hit the rate limit {self.rateLimited} times.")
        for reason, count in self.skipped.most_common():
            lines.append(f"Skipped {count}: {reason}")
        return "\n".join(lines)
