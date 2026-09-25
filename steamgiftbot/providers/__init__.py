#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""The giveaway sites the bot knows. See base.py for what a site must offer."""
from steamgiftbot.providers.steamgifts import SteamGiftsProvider

PROVIDERS = {
    'steamgifts': SteamGiftsProvider,
}

DEFAULT = 'steamgifts'


def build(config, name=DEFAULT):
    try:
        provider = PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown giveaway site {name!r}, "
                         f"expected one of: {', '.join(PROVIDERS)}") from None
    return provider(config)
