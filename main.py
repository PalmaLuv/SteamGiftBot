#    ______                   ______ _____    ___                      
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/   
#                                                                    
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0

# from method.method import SteamGift
import configparser
import client as clientLog

# from PyInstaller import (Token, Error, JsonPrint, prompt)
config      = configparser.ConfigParser()

# Storing parameters.  
class valProject:
    def __init__(self):
        self._valLogs = False
        self._cookie = ""

    @property
    def valLogs(self):
        return self._valLogs

    @valLogs.setter
    def valLogs(self, value):
        self._valLogs = value

    @property
    def cookie(self):
        return self._cookie

    @cookie.setter
    def cookie(self, value):
        self._cookie = value
thisConfig = valProject()

# Creation and processing of previously created parameters or, if not created, their creation 
def workingWithConfig(): 
    config.read('config.ini')
    if not config['DEFAULT'].get('cookie'): 
        thisConfig.cookie = clientLog.askCookie()
    else:
        thisConfig.cookie = config['DEFAULT'].get('cookie')
    if not config['DEFAULT'].get('log_info'): 
        thisConfig.valLogs = clientLog.askLog()
    else:
        thisConfig.valLogs = bool(config['DEFAULT'].get('log_info'))
    if not config['DEFAULT'].get('cookie') or not config['DEFAULT'].get('log_info'):
        clientLog.askReadConfig(thisConfig.cookie, thisConfig.valLogs)

# Editing the script settings *.ini file
def editConfig():
    while(True):
        editCfg = startCfg = clientLog.ask('list', 'config_edit', 'Choice of Action :', choices= [
            'Cookie', 'log info', 'exit' 
        ])['config_edit']
        if editCfg == 'Cookie' :
            thisConfig.cookie = clientLog.askCookie()
            clientLog.askReadConfig(thisConfig.cookie, thisConfig.valLogs)
        elif editCfg == 'log info' : 
            thisConfig.valLogs = clientLog.askLog()
            clientLog.askReadConfig(thisConfig.cookie, thisConfig.valLogs)
        elif editCfg == 'exit' :
            break

# Program launch function
def run(): 
    from method.method import SteamGift as steamGif 
    for index in range(4): 
        clientLog.log(clientLog.array_logo[index], "green")
    clientLog.log("\nEnjoy using our product!", "white")
    clientLog.log("Created by: github.com/PalmaLuv | palmaluv.live\nStay tuner for further app updates","red")
    workingWithConfig()
    while(True):
        startCfg = clientLog.ask('list', 'config_start', 'Choice of Action :', choices= [
            'Start', 'Edit' 
        ])['config_start']
        if startCfg == 'Start': break 
        elif startCfg == 'Edit' : editConfig()
    pinnedGames = clientLog.ask('confirm', 'pinned', 'Should the bot enter pinned games?')['pinned']
    giftTYPE = clientLog.ask('list', 'gift_type', 'Select type:', choices= [
        'All', 'WishList', 'Recommended', 'Copies', 'DLC', 'New'
    ])['gift_type']
    minPoin = clientLog.ask('input', 'min_points', 'What is the minimum number of points to remain?')['min_points']
    clientLog.createdLogs(thisConfig.valLogs)
    steamGif(thisConfig.cookie, giftTYPE, pinnedGames, minPoin).start()

if __name__ == '__main__':
    run()
