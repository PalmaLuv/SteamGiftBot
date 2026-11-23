# The bot farm with its web panel: what BotFarm.exe starts.
#
#   python botfarm.py --host 127.0.0.1 --port 8092
#
# The same as 'python -m steamgiftbot.farm'; PyInstaller needs a script.
import sys

from steamgiftbot.farm.__main__ import main

if __name__ == '__main__':
    sys.exit(main())
