"""Running the farm from Telegram: the same bot that sends the notifications
also answers a few commands, and only in the chat it was set up with.

Long polling (getUpdates) needs no open port, so this works behind the LAN
firewall. Commands that were waiting while the farm was off are dropped on
start rather than run late: a /pause from yesterday should not stop today."""
import logging
import threading

import requests

log = logging.getLogger('botfarm')

API     = 'https://api.telegram.org/bot{token}/{method}'
POLL    = 25
RETRY   = 30

COMMANDS = [
    ('status', 'что делает каждая площадка'),
    ('start', 'запустить площадку: /start indiegala или /start all'),
    ('pause', 'остановить площадку: /pause steamgifts или /pause all'),
    ('run', 'пройти сейчас, не дожидаясь паузы: /run indiegala'),
    ('preview', 'что ферма взяла бы сейчас: /preview indiegala'),
    ('wins', 'выигрыши без отметки'),
    ('report', 'сводка за сутки'),
    ('help', 'список команд'),
]

STATE_ICON = {'running': '▶️', 'sleeping': '⏳', 'stopped': '⏹', 'error': '⚠️', 'auth': '🔑'}


class TelegramControl:
    def __init__(self, manager, session=None):
        self.manager = manager
        self.session = session or requests.Session()
        self.stopFlag = threading.Event()
        self.thread = None
        self.offset = None
        self.token = None

    # ---- the commands --------------------------------------------------------

    def findSites(self, word):
        word = (word or '').strip().lower()
        platforms = list(self.manager.platforms.values())
        if word in ('', 'all', 'все', 'всё'):
            return platforms
        return [platform for platform in platforms
                if platform.key.startswith(word) or platform.title.lower().startswith(word)]

    def statusText(self):
        lines = []
        for platform in self.manager.platforms.values():
            if not platform.configured():
                continue
            snap = platform.snapshot()
            balance = ('' if snap['balance'] is None
                       else f", баланс {snap['balance']} {platform.unit}")
            line = (f"{STATE_ICON.get(snap['state'], '•')} {platform.title}: "
                    f"{snap['totals']['today']} вх. за сутки{balance}")
            if snap['reason']:
                line += f"\n    {snap['reason']}"
            if snap['error']:
                line += f"\n    ⚠ {snap['error']}"
            lines.append(line)
        return '\n'.join(lines) or "Ни одна площадка не подключена."

    def handle(self, text):
        parts = (text or '').strip().split()
        if not parts or not parts[0].startswith('/'):
            return None
        command = parts[0][1:].split('@')[0].lower()
        argument = parts[1] if len(parts) > 1 else ''
        manager = self.manager
        if command in ('help', 'commands'):
            return '\n'.join(f"/{name} — {about}" for name, about in COMMANDS)
        if command == 'status':
            return self.statusText()
        if command == 'report':
            return manager.report()
        if command == 'wins':
            wins = manager.openWins()
            if not wins:
                return "Неотмеченных выигрышей нет."
            return '\n'.join(f"🎉 {win['name']} ({win['title']})" for win in wins[:15])
        if command in ('start', 'pause', 'stop', 'run', 'preview'):
            sites = self.findSites(argument)
            if not sites:
                return f"Не знаю площадку «{argument}». Есть: " + ', '.join(
                    platform.key for platform in manager.platforms.values())
            if command == 'preview':
                if len(sites) != 1:
                    return "Укажите одну площадку: /preview indiegala"
                return self.previewText(sites[0])
            done = []
            for platform in sites:
                if command == 'start' and platform.configured() and platform.start():
                    done.append(platform.title)
                elif command in ('pause', 'stop') and platform.running:
                    platform.stop()
                    done.append(platform.title)
                elif command == 'run' and platform.running:
                    platform.wakeUp()
                    done.append(platform.title)
            verb = {'start': 'Запущено', 'pause': 'Остановлено', 'stop': 'Остановлено',
                    'run': 'Новый проход начат'}[command]
            if not done:
                return "Нечего делать: площадки уже в этом состоянии."
            return f"{verb}: {', '.join(done)}"
        return "Не знаю такой команды. /help — список."

    def previewText(self, platform):
        try:
            result = platform.runPreview()
        except Exception as error:
            return f"{platform.title}: не получилось — {error}"
        take = [item for item in result['items'] if item['enter']]
        cost = sum(item.get('cost') or 0 for item in take)
        lines = [f"{platform.title}: войдёт в {len(take)} из {len(result['items'])} "
                 f"на {cost} {platform.unit}"]
        lines += [f"• {item['name']} ({item.get('cost') or 0} {platform.unit})"
                  for item in take[:15]]
        if len(take) > 15:
            lines.append(f"…и ещё {len(take) - 15}")
        if result.get('note'):
            lines.append(result['note'])
        return '\n'.join(lines)

    # ---- talking to Telegram ---------------------------------------------------

    # wait is the HTTP timeout; params may carry Telegram's own 'timeout'.
    def call(self, token, method, wait=15, **params):
        response = self.session.post(API.format(token=token, method=method), json=params,
                                     timeout=wait)
        data = response.json()
        if not data.get('ok'):
            raise RuntimeError(data.get('description') or f"HTTP {response.status_code}")
        return data.get('result')

    def settings(self):
        conf = self.manager.farmSettings()
        ready = (conf.get('telegram_commands') and conf.get('telegram_token')
                 and conf.get('telegram_chat'))
        return (conf['telegram_token'], str(conf['telegram_chat'])) if ready else (None, None)

    def process(self, token, chat, update):
        message = update.get('message') or update.get('edited_message') or {}
        if str((message.get('chat') or {}).get('id')) != chat:
            return None
        reply = self.handle(message.get('text'))
        if reply:
            self.call(token, 'sendMessage', chat_id=chat, text=reply[:4000])
        return reply

    # Skips whatever piled up while the farm was off and announces the commands.
    def prepare(self, token):
        pending = self.call(token, 'getUpdates', offset=-1, timeout=0) or []
        self.offset = pending[-1]['update_id'] + 1 if pending else None
        self.call(token, 'setMyCommands', commands=[{'command': name, 'description': about}
                                                    for name, about in COMMANDS])
        self.token = token

    def pollOnce(self):
        token, chat = self.settings()
        if not token:
            self.token = None
            return False
        if token != self.token:
            self.prepare(token)
        updates = self.call(token, 'getUpdates', wait=POLL + 10, offset=self.offset,
                            allowed_updates=['message'], timeout=POLL) or []
        for update in updates:
            self.offset = update['update_id'] + 1
            try:
                self.process(token, chat, update)
            except Exception as error:
                log.warning(f"Telegram: команда не выполнена: {error}")
        return True

    def loop(self):
        while not self.stopFlag.is_set():
            try:
                if not self.pollOnce():
                    self.stopFlag.wait(RETRY)
            except Exception as error:
                log.warning(f"Telegram-команды: {error}")
                self.token = None
                self.stopFlag.wait(RETRY)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name='farm-telegram', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopFlag.set()
