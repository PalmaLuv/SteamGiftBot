#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Failures that end a run. Shared by every giveaway site the bot talks to."""


# Raised when the bot cannot continue: bad cookie, dead session, empty filter.
# The name predates the other sites; it stands for any of them.
class SteamGiftError(Exception):
    pass


# The cookie stopped working. Told apart from the rest because it is the one
# failure the user has to act on, and the one worth a message on its own.
class SessionExpired(SteamGiftError):
    pass
