#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Deciding which giveaways are worth points."""

# Short, stable phrases: they are counted in the end of run summary, so they
# must not carry numbers that would split one reason into many.
ALREADY_ENTERED = "already entered"
PINNED          = "pinned"
LEVEL_TOO_HIGH  = "asks for a higher contributor level"
REGION_LOCKED   = "restricted to another region"
TOO_CROWDED     = "too many entries already"
TOO_EXPENSIVE   = "above the cost limit"
BLACKLISTED     = "on the blacklist"
NOT_WHITELISTED = "not on the whitelist"
NOT_ENOUGH      = "not enough points"
NO_CARDS        = "no trading cards"
UNKNOWN_APP     = "no Steam app id to check for cards"


def nameMatches(name, patterns):
    lowered = name.lower()
    return any(pattern and pattern.lower() in lowered for pattern in patterns)


# Returns the reason to leave this giveaway alone, or None to enter it.
# hasCards is called at most once, and only when the setting asks for it: it
# costs a request to the Steam store.
def reasonToSkip(giveaway, config, points, hasCards=None):
    if giveaway.entered:
        return ALREADY_ENTERED

    if giveaway.pinned and not config.pinned:
        return PINNED

    # Checked before anything that costs a request: entering a giveaway above
    # your level, or locked to another region, is refused by the site anyway.
    # Three out of five giveaways on a page ask for a level, so this is the
    # difference between most requests landing and most being wasted.
    if config.contributor_level is not None and giveaway.level > config.contributor_level:
        return LEVEL_TOO_HIGH

    if config.skip_region_locked and giveaway.regionLocked:
        return REGION_LOCKED

    # Unknown entry counts are let through: the listing not saying is no reason
    # to skip a giveaway that might be quiet.
    if (config.max_entries is not None and giveaway.entries is not None
            and giveaway.entries > config.max_entries):
        return TOO_CROWDED

    if config.max_cost is not None and giveaway.cost > config.max_cost:
        return TOO_EXPENSIVE

    if config.blacklist and nameMatches(giveaway.name, config.blacklist):
        return BLACKLISTED

    if config.whitelist and not nameMatches(giveaway.name, config.whitelist):
        return NOT_WHITELISTED

    if points < giveaway.cost:
        return NOT_ENOUGH

    if config.cards_only:
        if giveaway.appid is None:
            # Bundles and packages have no app id, so 'only cards' cannot be
            # honoured for them. Skipping is the reading that matches the name.
            return UNKNOWN_APP
        if hasCards is not None and not hasCards(giveaway.appid):
            return NO_CARDS

    return None
