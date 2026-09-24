#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
import requests

from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from steamgiftbot.console import log

STORE_API                   = "https://store.steampowered.com/api/appdetails"
TRADING_CARDS_CATEGORY_ID   = 29
TIMEOUT                     = 30

# The same game shows up on page after page, and the Steam store counts requests.
# Only real answers are kept: a network hiccup must not decide a game for good.
_answers = {}

# One connection pool for every lookup, built on first use.
_http = None


def clearCache():
    _answers.clear()


def session():
    global _http
    if _http is None:
        _http = requests.Session()
        # The store throttles with 429 and Retry-After; urllib3 honours both.
        retry = Retry(total=3, backoff_factor=0.5,
                      status_forcelist=(429, 500, 502, 503, 504))
        _http.mount('https://', HTTPAdapter(max_retries=retry))
    return _http


# True when the Steam app has trading cards, False when the store says it has
# none (or does not know the app), None when the store could not be asked.
# None is never cached, so the next page gets another go at it.
def get_game_info(appid):
    if appid in _answers:
        return _answers[appid]
    answer = _lookUp(appid)
    if answer is not None:
        _answers[appid] = answer
    return answer


def _lookUp(appid):
    try:
        response = session().get(STORE_API, params={'appids': appid}, timeout=TIMEOUT)
    except requests.RequestException as error:
        log(f"Could not ask the Steam store about app {appid}: {error}", "yellow")
        return None

    if response.status_code != 200:
        log(f"The Steam store answered HTTP {response.status_code} for app {appid}", "yellow")
        return None

    try:
        data = response.json()
    except ValueError:
        log(f"The Steam store sent something that was not JSON for app {appid}", "yellow")
        return None

    entry = data.get(str(appid)) or {}
    if not entry.get('success'):
        return False

    categories = entry.get('data', {}).get('categories', [])
    return any(category.get('id') == TRADING_CARDS_CATEGORY_ID for category in categories)
