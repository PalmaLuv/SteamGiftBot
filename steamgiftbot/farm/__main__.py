"""python -m steamgiftbot.farm [--host H] [--port P] [--set-password]"""
import argparse
import getpass
import logging
import logging.handlers
import os
import signal
import sys
import threading

from pathlib import Path

from steamgiftbot import settings as sgSettings
from steamgiftbot.console import startLogFile
from steamgiftbot.farm.manager import FarmManager
from steamgiftbot.farm.web import serve

BIND_RETRY_SECONDS = 15


def configureLogging(dataDir):
    logDir = dataDir / 'log'
    logDir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('[%(levelname)s %(asctime)s %(name)s] %(message)s')
    fileHandler = logging.handlers.RotatingFileHandler(
        logDir / 'botfarm.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    fileHandler.setFormatter(formatter)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
    # The sites log DEBUG lines for the panel's 'Подробно' view; the file and
    # the journal stay at INFO.
    fileHandler.setLevel(logging.INFO)
    console.setLevel(logging.INFO)
    farmLogger = logging.getLogger('botfarm')
    farmLogger.setLevel(logging.INFO)
    farmLogger.propagate = False
    farmLogger.addHandler(fileHandler)
    farmLogger.addHandler(console)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='botfarm', description="Ферма раздач с веб-панелью")
    parser.add_argument('--host', default=os.environ.get('BOTFARM_HOST', '127.0.0.1'),
                        help="адрес(а) через запятую, например 192.168.1.10,100.64.0.5")
    parser.add_argument('--port', type=int, default=int(os.environ.get('BOTFARM_PORT', 8092)))
    parser.add_argument('--config', default=None,
                        help="config.ini SteamGiftBot (там же cookie SteamGifts и Telegram); "
                             "по умолчанию — в папке данных")
    parser.add_argument('--data', default=os.environ.get('BOTFARM_DATA'),
                        help="папка для farm.json, истории и логов (по умолчанию — папка "
                             "проекта); удобно для Docker")
    parser.add_argument('--no-autostart', action='store_true',
                        help="не запускать площадки с автозапуском (только панель)")
    parser.add_argument('--set-password', action='store_true',
                        help="задать пароль веб-панели и выйти")
    args = parser.parse_args(argv)

    dataDir = Path(args.data) if args.data else None
    if dataDir is not None:
        dataDir.mkdir(parents=True, exist_ok=True)
    config = args.config or (dataDir / 'config.ini' if dataDir else sgSettings.DEFAULT_CONFIG_PATH)
    manager = FarmManager(dataDir=dataDir, configPath=config)

    if args.set_password:
        password = os.environ.get('BOTFARM_PASSWORD') or getpass.getpass("Новый пароль панели: ")
        manager.setPassword(password)
        print("Пароль сохранён.")
        return 0

    # Before this run writes anything: the panel's log starts with the tail of
    # the previous runs instead of empty.
    manager.restoreLogs()
    configureLogging(manager.dataDir)
    log = logging.getLogger('botfarm')

    # SteamGiftBot's own file log, as the command line version writes it.
    try:
        writeLog = sgSettings.load(config).log_info
    except sgSettings.SettingsError:
        writeLog = False
    startLogFile(bool(writeLog), manager.dataDir / 'log')
    # startLogFile resets the package logger's handlers; put the panel's back.
    for platform in manager.platforms.values():
        if platform.kind == 'steamgifts':
            platform.attachLogger()

    if not manager.hasPassword():
        log.warning("Пароль панели не задан: python -m steamgiftbot.farm --set-password")

    hosts = [host.strip() for host in args.host.split(',') if host.strip()]
    manager.panelURLs = [f"http://{host}:{args.port}/" for host in hosts]
    servers = []
    stopping = threading.Event()

    # One listener per address. An address that is not there yet (tailscale0
    # comes up after the network at boot) is retried until it appears.
    def listen(host):
        warned = False
        while not stopping.is_set():
            try:
                server = serve(manager, host, args.port)
            except OSError as error:
                if not warned:
                    log.warning(f"Не могу слушать {host}:{args.port} ({error}), "
                                f"повторяю каждые {BIND_RETRY_SECONDS} с")
                    warned = True
                stopping.wait(BIND_RETRY_SECONDS)
                continue
            servers.append(server)
            log.info(f"Веб-панель: http://{host}:{args.port}/")
            server.serve_forever(poll_interval=0.5)
            server.server_close()
            return

    threads = [threading.Thread(target=listen, args=(host,), daemon=True) for host in hosts]
    for thread in threads:
        thread.start()

    if not args.no_autostart:
        manager.startAutostart()
    manager.startClock()
    manager.startTelegram()

    def shutdown(*_):
        if stopping.is_set():
            return
        stopping.set()
        log.info("Останавливаю ферму…")

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        stopping.wait()
    finally:
        for server in list(servers):
            server.shutdown()
        manager.stopAll()
    return 0


if __name__ == '__main__':
    sys.exit(main())
