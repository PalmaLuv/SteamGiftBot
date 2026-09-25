#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Noticing wins: ask the site, remember what was said, tell the user once."""
from steamgiftbot import notify, wins
from steamgiftbot.console import log
from steamgiftbot.errors import SessionExpired, SteamGiftError


class WinWatcher:
    def __init__(self, provider, config, state, stats):
        self.provider = provider
        self.config   = config
        self.state    = state
        self.stats    = stats
        # A dry run looks but neither sends nor writes anything down.
        self.dryRun   = bool(getattr(config, 'dry_run', False))

    # Announces anything that was not announced before. Only a dead session
    # gets out of here: missing a win is bad, failing the run over it is worse,
    # but the user has to hear about the cookie.
    def announce(self):
        try:
            found, recognised = self.provider.fetchWins()
        except SessionExpired:
            raise
        except SteamGiftError as error:
            log(f"Could not check for wins: {error}", "yellow")
            return []

        if not recognised:
            log("The won giveaways page did not look the way the bot expects, "
                "so wins cannot be checked. Everything else keeps working.", "yellow")
            return []

        if self.state.fresh:
            return self.rememberHistory(found)

        fresh = [win for win in found if self.state.isNew(win.code)]
        if not fresh:
            return []

        if self.dryRun:
            for win in fresh:
                log(f"Would announce: you won {win.name}! {win.url}", "cyan")
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

    # With nothing remembered, every win on the page would look new, and a first
    # run would message the user about games won months ago. Those are written
    # down quietly instead; from here on only real news gets through.
    def rememberHistory(self, found):
        if self.dryRun:
            if found:
                log(f"First run: {len(found)} earlier wins will be remembered, "
                    "not announced.", "cyan")
            return []

        for win in found:
            self.state.remember(win.code)
        # Saved even when empty, so the next run knows it is not the first.
        self.state.save()
        self.state.fresh = False
        if found:
            log(f"First run: remembered {len(found)} earlier wins without announcing them. "
                "New wins will be announced from now on.", "white")
        return []
