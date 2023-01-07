#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
#

import sys 
import configparser 
import requests
import json
import threading 

from random import randint as rand 
emoji = ['🎮', '🎯', '🙂', '🥸', '🧐', '🤓', '🤤', '👾', '🤖', '🎃', '👽', '💀']

from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from time import sleep
from requests import RequestException
from bs4 import BeautifulSoup

from _logs import log

info    =    json.load(open('method//info.json', 'r', encoding='utf-8'))
URL     =    info['URL']

class SteamGift : 
    def __init__(self, cookie, type, pinned, min_points):
        self.cookie     = { 'PHPSESSID' : cookie }
        self.type       = type
        self.pinned     = pinned
        self.min_points = int(min_points)

        self.baseURL = URL
        self.session = requests.Session()

        self.filterURL = info['filterURL']

    def requestsRetrySession(self, retries=5, backoffFactor=0.3):
        session = self.session or requests.Session()
        retry = Retry(
            total=retries,
            read=retries, 
            connect=retries,
            backoff_factor=backoffFactor, 
            status_forcelist=(500, 502, 504)
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount(info['http'], adapter)
        session.mount(info['https'], adapter)
        return session

    def GetSoupFromPage(self, url):
        res_soup = requests.get(url, cookies=self.cookie)
        return BeautifulSoup(res_soup.text, 'html.parser')
    
    def updateInfo(self):
        soup = self.GetSoupFromPage(self.baseURL)
        try:
            self.xsrfToken = soup.find('input', {'name': 'xsrf_token'})['value']
            self.points    = int(soup.find('span', {'class': 'nav__points'}).text)
        except TypeError:
            log("🔥 cookie is not valid 🔥","red")
            exit()
    
    def entryGIFT(self, id):
        payload = {
        'xsrf_token' : self.xsrfToken, 
        'do'        : 'entry_insert',
        'code'      : id
        }

        jsonData = json.loads(
            (requests.post('https://www.steamgifts.com/ajax.php',
                          data=payload,
                          cookies=self.cookie
            )).text
        )
        if jsonData['type'] == 'success' :
            return True 

    def getGameContent(self, page=1):
        while True:
            log(f"Getting games from page {page}", "magenta")

            filtered_url = self.filterURL[self.type] % page
            paginated_url = f"{self.baseURL}/giveaways/{filtered_url}"
            soup = self.GetSoupFromPage(paginated_url)
            game_list = soup.find_all('div', {'class': 'giveaway__row-inner-wrap'})
            if not len(game_list):
                log("🔥 Page is empty. Please, choose another type. 🔥", "red")
                exit()
            for item in game_list:
                if len(item.get('class', [])) == 2 and not self.pinned:
                    continue
                if self.points == 0 or self.points < self.min_points:
                    log(f"Sleeping to get 6 points. We have {self.points} points."
                        + f"\nTo continue, you need at least {self.min_points}", "magenta")
                    for i in range(900):
                        print(f"The are {900-i} seconds left.\t\r",end='')
                        sleep(1)
                    self.start()
                    break
                game_cost = item.find_all('span', {'class': 'giveaway__heading__thin'})[-1]
                if game_cost:
                    game_cost = game_cost.getText().replace('(', '').replace(')', '').replace('P', '')
                else:
                    continue
                game_name = item.find('a', {'class': 'giveaway__heading__name'}).text
                if self.points - int(game_cost) < 0:
                    log(f"⛔ Not enough points to enter: {game_name}", "red")
                    continue

                elif self.points - int(game_cost) >= 0:
                    game_id = item.find('a', {'class': 'giveaway__heading__name'})['href'].split('/')[2]
                    res = self.entryGIFT(game_id)
                    if res:
                        self.points -= int(game_cost)
                        log(f"{emoji[rand(0,len(emoji)-1)]}One more game {game_name}", "green")
                        sleep(rand(3, 7))
            page += 1
        #log("🛋️  List of games is ended. Waiting 2 mins to update...", "yellow")
        #sleep(120)
        #self.start()

    def start(self):
        self.updateInfo()
        if self.points > 0:
            log(f"You currently have balance {self.points} points","white")
            log(f"Script running","green")
        self.getGameContent()
