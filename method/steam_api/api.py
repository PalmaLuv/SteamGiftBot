import requests
import re

class SteamAPI:
    def __init__(self):
        self.baseURL = "https://store.steampowered.com/api/appdetails?appids="
        self.URLGamePattern = r"https://store\.steampowered\.com/app/(\d+)"

    # Check for cards in play
    def get_game_info(self, appid: int):
        response = requests.get(f"{self.baseURL}{appid}")
        if response.status_code == 200 : 
            data = response.json()
            if data[str(appid)]['success']:
                game_data = data[str(appid)]['data']
                if 'categories' in game_data: 
                    categories = game_data['categories']
                    has_trading_cards = any(category['id'] == 29 for category in categories)
                    if has_trading_cards: 
                        return True
                    else:
                        return False
                else: 
                    return False
            else: 
                return False
        else: 
            return False

    # Find game ID 
    @staticmethod
    def get_game_id(url: str) -> str:
        match = re.search(r'/app/(\d+)', url)
        return match.group(1) if match else None

