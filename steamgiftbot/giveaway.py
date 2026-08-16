#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""One row of the giveaway listing, turned into something we can reason about."""
import re

from dataclasses import dataclass
from typing import Optional

# Matched against every link in the row rather than one particular CSS class,
# so a redesign of the listing does not silently lose the app id.
STORE_APP = re.compile(r'store\.steampowered\.com/app/(\d+)')

# SteamGifts spells pinned giveaways in more than one way, and has changed the
# spelling before: the row itself may carry 'is-pinned', or the whole block may
# sit inside a 'pinned-giveaways' wrapper. Look for the word in either place.
PINNED_WORD = 'pinned'

# How far up to look for that wrapper. Enough to leave the row's own block,
# not so far that a container elsewhere on the page can claim everything.
PINNED_LOOKUP_DEPTH = 3


def classesOf(tag):
    getter = getattr(tag, 'get', None)
    return getter('class', []) or [] if getter else []


def isPinned(item, classes):
    if any(PINNED_WORD in name for name in classes):
        return True

    for depth, parent in enumerate(item.parents):
        if depth >= PINNED_LOOKUP_DEPTH:
            break
        if any(PINNED_WORD in name for name in classesOf(parent)):
            return True

    # Nothing else counts. The bot used to treat any second class as the mark of
    # a pinned row, which a check against the live listing showed to be wrong:
    # ordinary giveaways carry 'has-description', and three out of four rows on
    # a page were being thrown away because of it.
    return False


# 'Level 3+' in the column that carries the contributor requirement, and
# '1,088 entries' in the links block. Both matched by wording rather than by an
# exact class name, which has changed before.
LEVEL_TEXT   = re.compile(r'level\s*(\d+)', re.IGNORECASE)
ENTRIES_TEXT = re.compile(r'([\d,]+)\s+entries', re.IGNORECASE)

LEVEL_CLASS  = re.compile('contributor-level')
REGION_CLASS = re.compile('region-restricted')


@dataclass
class Giveaway:
    code    : str
    name    : str
    cost    : int
    entered : bool = False
    pinned  : bool = False
    appid   : Optional[int] = None
    # How many people are already in. None when the listing did not say.
    entries : Optional[int] = None
    # Contributor level the giveaway asks for; 0 when it asks for none.
    level   : int  = 0
    # Open only to certain countries.
    regionLocked : bool = False


def findEntries(item):
    found = ENTRIES_TEXT.search(item.get_text(' ', strip=True))
    if not found:
        return None
    return int(found.group(1).replace(',', ''))


def findLevel(item):
    column = item.find(class_=LEVEL_CLASS)
    if column is None:
        return 0
    found = LEVEL_TEXT.search(column.get_text(' ', strip=True))
    return int(found.group(1)) if found else 0


def isRegionLocked(item):
    return item.find(class_=REGION_CLASS) is not None


def findAppId(item):
    for link in item.find_all('a', href=True):
        found = STORE_APP.search(link['href'])
        if found:
            return int(found.group(1))
    return None


# Returns None when the row is not shaped like a giveaway at all.
def parseRow(item):
    nameTag  = item.find('a', {'class': 'giveaway__heading__name'})
    costTags = item.find_all('span', {'class': 'giveaway__heading__thin'})
    if nameTag is None or not costTags:
        return None

    try:
        cost = int(costTags[-1].get_text().strip().strip('()').replace('P', ''))
    except ValueError:
        return None

    parts = nameTag.get('href', '').split('/')
    if len(parts) < 3 or not parts[2]:
        return None

    classes = item.get('class', [])
    entered = 'is-faded' in classes

    return Giveaway(
        code    = parts[2],
        name    = nameTag.text.strip(),
        cost    = cost,
        entered = entered,
        pinned  = not entered and isPinned(item, classes),
        appid   = findAppId(item),
        entries = findEntries(item),
        level   = findLevel(item),
        regionLocked = isRegionLocked(item),
    )
