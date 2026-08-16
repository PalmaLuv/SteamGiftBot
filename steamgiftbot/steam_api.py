#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
import requests

STORE_API                   = "https://store.steampowered.com/api/appdetails"
TRADING_CARDS_CATEGORY_ID   = 29
TIMEOUT                     = 30

# The same game shows up on page after page, and the Steam store counts requests.
_answers = {}


def clearCache():
    _answers.clear()


# Returns True when the Steam app has trading cards, False in every other case
# (unknown appid, region lock, network trouble).
def get_game_info(appid):
    if appid in _answers:
        return _answers[appid]
    answer = _lookUp(appid)
    _answers[appid] = answer
    return answer


def _lookUp(appid):
    try:
        response = requests.get(STORE_API, params={'appids': appid}, timeout=TIMEOUT)
    except requests.RequestException:
        return False

    if response.status_code != 200:
        return False

    try:
        data = response.json()
    except ValueError:
        return False

    entry = data.get(str(appid)) or {}
    if not entry.get('success'):
        return False

    categories = entry.get('data', {}).get('categories', [])
    return any(category.get('id') == TRADING_CARDS_CATEGORY_ID for category in categories)
