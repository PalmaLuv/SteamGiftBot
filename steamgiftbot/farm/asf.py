"""ArchiSteamFarm over its IPC API: activating won keys and claiming free
Steam licenses. ASF usually runs on the same machine, so when no IPC password
is set in the farm it is read from ASF's own config file.

  GET  /Api/Bot/ASF                         -> {Result: {botName: Bot}}
  POST /Api/Bot/{bot}/Redeem   {KeysToRedeem: [...]}
  POST /Api/Bot/{bot}/AddLicense {Apps: [...], Packages: [...]}

Every answer is {Success, Message, Result}; enums come back as numbers."""
import json
import logging

from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger('botfarm')

DEFAULT_URL    = 'http://127.0.0.1:1242'
LOCAL_CONFIG   = Path.home() / 'asf' / 'config' / 'ASF.json'
TIMEOUT        = 60

EResult_OK = 1

# EPurchaseResultDetail, in the panel's language.
DETAILS = {
    9: 'уже есть в библиотеке',
    13: 'не для вашего региона',
    19: 'не для вашего региона',
    14: 'неверный ключ',
    15: 'ключ уже кто-то активировал',
    24: 'сначала нужна основная игра',
    50: 'это не ключ игры (код кошелька или подарок)',
    53: 'Steam просит подождать: слишком много активаций',
    4: 'Steam не ответил вовремя',
}

# Outcomes: 'ok' activated, 'owned' already had it, 'retry' worth another
# go later, 'fail' will never work.
RETRY_DETAILS = {53, 4}


def localPassword(path=LOCAL_CONFIG):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8')).get('IPCPassword') or ''
    except (OSError, ValueError):
        return ''


def outcome(answer):
    """(kind, words) for one CStore_RegisterCDKey_Response."""
    if not answer:
        return 'retry', 'бот ASF не в сети'
    receipt = answer.get('purchase_receipt_info')
    detail = answer.get('purchase_result_details') or 0
    if not receipt:
        return 'retry', 'Steam не дал ответа'
    if receipt.get('purchase_status') == EResult_OK:
        items = ', '.join(item.get('line_item_description', '')
                          for item in receipt.get('line_items') or [] if item)
        return 'ok', 'активирован' + (f': {items}' if items else '')
    if detail == 9:
        return 'owned', DETAILS[9]
    words = DETAILS.get(detail, f'отказ Steam (код {detail})')
    return ('retry' if detail in RETRY_DETAILS else 'fail'), words


class ASF:
    def __init__(self, manager, session=None):
        self.manager = manager
        self.session = session or requests.Session()

    def conf(self):
        values = self.manager.farmSettings()
        return {'url': (values.get('asf_url') or DEFAULT_URL).rstrip('/'),
                'password': values.get('asf_password') or localPassword(),
                'bot': (values.get('asf_bot') or '').strip()}

    def call(self, method, path, body=None):
        conf = self.conf()
        headers = {'Authentication': conf['password']} if conf['password'] else {}
        try:
            response = self.session.request(method, conf['url'] + path, json=body,
                                            headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise ValueError(f"ASF недоступен по адресу {conf['url']}: проверьте, что он "
                             f"запущен и IPC включён") from error
        if response.status_code == 401:
            raise ValueError("ASF не принял пароль IPC (IPCPassword в ASF.json)")
        if response.status_code == 403:
            raise ValueError("ASF не пускает этот адрес: задайте IPCPassword в ASF.json")
        try:
            data = response.json()
        except ValueError as error:
            raise ValueError(f"ASF ответил не JSON (HTTP {response.status_code})") from error
        if data.get('Result') is None:
            raise ValueError(f"ASF: {data.get('Message') or 'пустой ответ'}")
        return data['Result']

    def bots(self):
        result = self.call('GET', '/Api/Bot/ASF')
        return [{'name': name, 'online': bool((bot or {}).get('IsConnectedAndLoggedOn'))}
                for name, bot in result.items()]

    # One bot for keys (a key works once); the chosen one or the first online.
    def keyBot(self):
        wanted = self.conf()['bot']
        if wanted and wanted.upper() != 'ASF':
            return wanted
        bots = self.bots()
        online = [bot['name'] for bot in bots if bot['online']]
        if not online:
            raise ValueError("в ASF нет ни одного бота в сети")
        return online[0]

    def check(self):
        bots = self.bots()
        if not bots:
            raise ValueError("в ASF нет ни одного бота")
        online = [bot['name'] for bot in bots if bot['online']]
        return {'bots': [bot['name'] for bot in bots], 'online': online}

    def redeem(self, key):
        bot = self.keyBot()
        result = self.call('POST', f'/Api/Bot/{quote(bot, safe="")}/Redeem',
                           {'KeysToRedeem': [key]})
        answer = (result.get(bot) or {}).get(key)
        kind, words = outcome(answer)
        log.info(f"ASF: ключ для {bot}: {words}")
        return kind, words

    # {('app'|'sub', id): (kind, words)} over every bot.
    def addLicenses(self, apps=(), packages=()):
        bot = self.conf()['bot'] or 'ASF'
        result = self.call('POST', f'/Api/Bot/{quote(bot, safe="")}/AddLicense',
                           {'Apps': list(apps), 'Packages': list(packages)})
        found = {}
        for perBot in result.values():
            for group, kind in (('Apps', 'app'), ('Packages', 'sub')):
                for ident, status in ((perBot or {}).get(group) or {}).items():
                    code = (status or {}).get('Result')
                    detail = (status or {}).get('PurchaseResultDetail') or 0
                    if code == EResult_OK:
                        verdict = ('ok', 'добавлено в библиотеку')
                    elif detail == 9:
                        verdict = ('owned', DETAILS[9])
                    else:
                        verdict = ('retry' if detail in RETRY_DETAILS or code in (16, 84)
                                   else 'fail', DETAILS.get(detail, f'код {code}/{detail}'))
                    # The best answer any bot got wins.
                    previous = found.get((kind, int(ident)))
                    order = ['ok', 'owned', 'retry', 'fail']
                    if previous is None or order.index(verdict[0]) < order.index(previous[0]):
                        found[(kind, int(ident))] = verdict
        return found
