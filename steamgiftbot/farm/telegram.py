"""Running the farm from Telegram: the same bot that sends the notifications
also answers a few commands, and only in the chat it was set up with.

Long polling (getUpdates) needs no open port, so this works behind the LAN
firewall. Commands that were waiting while the farm was off are dropped on
start rather than run late: a /pause from yesterday should not stop today."""
import logging
import threading

import requests

from steamgiftbot.farm import cards, support

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
    ('donate', 'поддержать проект'),
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
        self.lang = None

    # ---- the commands --------------------------------------------------------

    def findSites(self, word):
        word = (word or '').strip().lower()
        platforms = list(self.manager.platforms.values())
        if word in ('', 'all', 'все', 'всё'):
            return platforms
        return [platform for platform in platforms
                if platform.key.startswith(word) or platform.title.lower().startswith(word)]

    def statusCard(self):
        rows, notes = [], []
        for platform in self.manager.platforms.values():
            if not platform.configured():
                continue
            snap = platform.snapshot()
            unit = f" {platform.unit}" if platform.unit else ''
            # The state icon goes last: emoji differ in width and would push
            # the columns of a monospace table out of line.
            rows.append([platform.title[:18], f"{snap['totals']['today']} вх./24 ч",
                         '—' if snap['balance'] is None else f"{snap['balance']}{unit}",
                         STATE_ICON.get(snap['state'], '•')])
            if snap['error']:
                notes.append(f"⚠️ {platform.title}: {snap['error']}")
            elif snap['reason']:
                notes.append(f"{cards.code(platform.key)}: {snap['reason']}")
        if not rows:
            return cards.Card('ℹ️', 'СТАТУС', headline="Ни одна площадка не подключена.",
                              buttons=[("Подключить", self.manager.panelLink('/sites'))])
        return cards.Card('ℹ️', 'СТАТУС', block=cards.table(rows), lines=notes,
                          note="▶️ работает · ⏳ ждёт · ⏹ стоит · ⚠️ ошибка · 🔑 нужен вход",
                          buttons=[("Открыть панель", self.manager.panelLink('/overview'))])

    def statusText(self):
        return self.statusCard().plain()

    # The answer to one message as a card, or None for anything not a command.
    def reply(self, text):
        parts = (text or '').strip().split()
        if not parts or not parts[0].startswith('/'):
            return None
        command = parts[0][1:].split('@')[0].lower()
        argument = parts[1] if len(parts) > 1 else ''
        manager = self.manager
        if command in ('help', 'commands'):
            return cards.Card('ℹ️', 'КОМАНДЫ',
                              lines=[f"/{name} — {about}" for name, about in COMMANDS])
        if command == 'status':
            return self.statusCard()
        if command == 'report':
            return manager.reportCard()
        if command == 'donate':
            return self.donateCard()
        if command == 'wins':
            wins = manager.openWins()
            if not wins:
                return cards.Card('✅', 'ВЫИГРЫШИ', headline="Неотмеченных выигрышей нет.")
            return cards.Card('🎉', 'ВЫИГРЫШИ БЕЗ ОТМЕТКИ',
                              lines=[f"• {win['name']} — {win['title']}" for win in wins[:15]],
                              buttons=[("Выигрыши", manager.panelLink('/wins'))])
        if command in ('start', 'pause', 'stop', 'run', 'preview'):
            sites = self.findSites(argument)
            if not sites:
                return cards.Card('⚠️', 'ВНИМАНИЕ', headline=f"Не знаю площадку «{argument}».",
                                  lines=["Есть: " + ', '.join(platform.key for platform
                                                             in manager.platforms.values())])
            if command == 'preview':
                if len(sites) != 1:
                    return cards.Card('⚠️', 'ВНИМАНИЕ',
                                      headline="Укажите одну площадку: /preview indiegala")
                return self.previewCard(sites[0])
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
                return cards.Card('ℹ️', 'ФЕРМА',
                                  headline="Нечего делать: площадки уже в этом состоянии.")
            return cards.Card('✅', 'ГОТОВО', headline=f"{verb}: {', '.join(done)}")
        return cards.Card('⚠️', 'ВНИМАНИЕ', headline="Не знаю такой команды. /help — список.")

    # TON goes in a monospace block, which Telegram copies with one tap.
    def donateCard(self):
        lang = self.manager.uiSettings()['lang']
        return cards.Card('💙', headline="SteamGiftBot бесплатный и останется бесплатным.",
                          block=[support.TON],
                          lines=["Ферму развивает один человек в свободное время. "
                                 "Если она приносит вам игры, разработку можно поддержать.",
                                 "Выше адрес TON: нажмите на него, чтобы скопировать. "
                                 "Остальные способы — кнопками."],
                          buttons=[(title, url) for title, url in support.LINKS]
                                  + [("Все способы", support.page(lang))])

    def handle(self, text):
        card = self.reply(text)
        return card.plain() if card else None

    def previewCard(self, platform):
        try:
            result = platform.runPreview()
        except Exception as error:
            return cards.Card('⚠️', 'ЧТО ВОЗЬМЁТ', platform.title, platform.key,
                              headline=f"не получилось — {error}")
        take = [item for item in result['items'] if item['enter']]
        cost = sum(item.get('cost') or 0 for item in take)
        lines = [f"• {item['name']} ({item.get('cost') or 0} {platform.unit})"
                 for item in take[:15]]
        if len(take) > 15:
            lines.append(f"…и ещё {len(take) - 15}")
        return cards.Card('🔍', 'ЧТО ВОЗЬМЁТ', platform.title, platform.key,
                          headline=f"войдёт в {len(take)} из {len(result['items'])} "
                                   f"на {cost} {platform.unit}",
                          lines=lines, note=result.get('note') or '',
                          buttons=[("Пробный проход в панели",
                                    self.manager.panelLink(f'/site/{platform.key}/preview'))])

    def previewText(self, platform):
        return self.previewCard(platform).plain()

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
        card = self.reply(message.get('text'))
        if card is None:
            return None
        card = self.manager.translateCard(card)
        try:
            self.send(token, chat, card)
        except RuntimeError:
            if not card.buttons:
                raise
            # A button Telegram will not take: the links written out instead.
            self.send(token, chat, card.withoutButtons())
        return card.plain()

    def send(self, token, chat, card):
        params = {'chat_id': chat, 'text': card.html()[:4000], 'parse_mode': 'HTML',
                  'disable_web_page_preview': True}
        if card.keyboard():
            params['reply_markup'] = card.keyboard()
        self.call(token, 'sendMessage', **params)

    # Skips whatever piled up while the farm was off and announces the commands.
    def prepare(self, token):
        pending = self.call(token, 'getUpdates', offset=-1, timeout=0) or []
        self.offset = pending[-1]['update_id'] + 1 if pending else None
        self.call(token, 'setMyCommands',
                  commands=[{'command': name, 'description': self.manager.translate(about)}
                            for name, about in COMMANDS])
        self.token = token
        self.lang = self.manager.uiSettings().get('lang')

    def pollOnce(self):
        token, chat = self.settings()
        if not token:
            self.token = None
            return False
        # Again when the panel's language changed: the command menu follows it.
        if token != self.token or self.manager.uiSettings().get('lang') != self.lang:
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
