#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License GPL-3.0 license

# from method.method import SteamGift
import configparser
import _logs as _l

# from PyInstaller import (Token, Error, JsonPrint, prompt)
config = configparser.ConfigParser()

def run(): 
    from method.method import SteamGift as steamGif
    for i in range(4): 
        _l.log(_l.array_logo[i], "green")
    _l.log("\nEnjoy using our product!","white")
    _l.log("Created by: github.com/PalmaLuv\nStay tuned for further app updates","red")

    config.read('config.ini')
    if not config['DEFAULT'].get('cookie'):
        cookie = _l.askCookie()
    else: 
        InputCookie = _l.ask('confirm', 'reenter',
        'Do you want to enter new cookie?')['reenter']
        if InputCookie:
            cookie = _l.askCookie()
        else:
            cookie = config['DEFAULT'].get('cookie')
    pinnedGames = _l.ask('confirm', 'pinned', 
    'Should the bot enter pinned games?')['pinned']
    
    giftTYPE = _l.ask('list', 'gift_type', 'Select type:',
    choices=[
        'All',
        'Wishlist',
        'Recommended',
        'Copies',
        'DLC',
        'New'
    ])['gift_type']
    minPoin = _l.ask('input', 'min_points',
    'What is the minimum number of points to remain?', _l.PointValidator)['min_points']
    sg = steamGif(cookie, giftTYPE, pinnedGames, minPoin)
    sg.start()


if __name__ == '__main__':
    run()