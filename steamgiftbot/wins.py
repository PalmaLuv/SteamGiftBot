#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Reading the 'giveaways won' page.

That page is only served to a signed in account, so the markup could not be
checked the way the listing was. The parser therefore leans on the one thing
that cannot quietly change shape - the /giveaway/<code>/<slug> link - and looks
for it inside whichever row container the page happens to use. If it recognises
no container at all it reports nothing rather than guessing, because a false
win would send you a message about a game you did not get.
"""
import re

from dataclasses import dataclass

WON_PATH = '/giveaways/won'

# Rows on SteamGifts have been spelled both ways over the years.
ROW_CLASSES = ('table__row-inner-wrap', 'giveaway__row-inner-wrap')

GIVEAWAY_LINK = re.compile(r'/giveaway/([A-Za-z0-9]+)/([^/?#]*)')


DEFAULT_BASE = 'https://www.steamgifts.com'


@dataclass
class Win:
    code : str
    name : str
    # The site the win came from; the bot passes the one in info.json.
    base : str = DEFAULT_BASE

    @property
    def url(self):
        return f"{self.base.rstrip('/')}/giveaway/{self.code}/"


def nameFromSlug(slug):
    return slug.replace('-', ' ').strip().title()


def findRows(soup):
    rows = []
    for className in ROW_CLASSES:
        rows.extend(soup.find_all(attrs={'class': className}))
    return rows


def winFromRow(row, base=DEFAULT_BASE):
    for link in row.find_all('a', href=True):
        found = GIVEAWAY_LINK.search(link['href'])
        if not found:
            continue
        code, slug = found.group(1), found.group(2)
        name = link.get_text().strip() or nameFromSlug(slug)
        return Win(code=code, name=name, base=base)
    return None


# Returns (wins, recognised). recognised is False when the page held no row
# container we know, which is worth telling the user about.
def parseWonPage(soup, base=DEFAULT_BASE):
    rows = findRows(soup)
    if not rows:
        return [], False

    wins = []
    seen = set()
    for row in rows:
        win = winFromRow(row, base)
        if win and win.code not in seen:
            seen.add(win.code)
            wins.append(win)
    return wins, True


def announcement(win):
    return f"You won {win.name}\n{win.url}"
