"""Free-to-keep Steam games, claimed through ArchiSteamFarm.

The list comes from the ASFinfo feed (the same one the FreePackages ASF plugin
reads): plain text, one 'a/<appid>' or 's/<subid>' per line, newest first.
ASF adds each to every bot's library with its AddLicense call. Nothing here
needs a cookie, only a running ASF."""
import re
import time

import requests

from steamgiftbot.farm.base import Platform, field, grouped, presetFields, scheduleFields
from steamgiftbot.farm.rules import presetReason

FEED       = ('https://gist.githubusercontent.com/C4illin/77a4bcb9a9a7a95e5f291badc93ec6cd/'
              'raw/Latest%20Steam%20Games')
APP_INFO   = 'https://store.steampowered.com/api/appdetails'
ENTRY      = re.compile(r'\b([as])/(\d+)\b')
STORE      = {'app': 'https://store.steampowered.com/app/{}/',
              'sub': 'https://store.steampowered.com/sub/{}/'}

# Steam lets an account add only so many free licenses an hour.
PER_PASS = 20


def parseFeed(text):
    found = []
    for kind, ident in ENTRY.findall(text or ''):
        item = ('app' if kind == 'a' else 'sub', int(ident))
        if item not in found:
            found.append(item)
    return found


class SteamFreePlatform(Platform):
    key         = 'steamfree'
    unit        = ''
    title       = 'Бесплатные игры Steam'
    siteURL     = 'https://store.steampowered.com/'
    description = ('Игры, которые Steam ненадолго раздаёт навсегда: ферма добавляет их в '
                   'библиотеку через ArchiSteamFarm.')
    category    = 'free'
    needs       = 'asf'
    connectFields = ()

    def schema(self):
        return grouped('Что брать', [
            field('per_pass', 'Не больше за проход', 'int', PER_PASS,
                  'Steam ограничивает число бесплатных лицензий в час'),
            field('blacklist', 'Чёрный список', 'list', [], 'слова через запятую'),
        ]) + presetFields() + grouped('Работа', [
            field('interval', 'Проверять раз в (мин)', 'int', 180),
        ]) + scheduleFields()

    def configured(self):
        return bool(self.manager.platformEntry(self.key).get('connected'))

    def guide(self):
        return [
            {'title': 'Запустите ArchiSteamFarm',
             'text': 'Ферма не входит в Steam сама: бесплатные игры добавляет ASF от имени '
                     'ваших ботов. Если ASF уже работает на этом сервере (как сейчас: '
                     'http://127.0.0.1:1242), ничего делать не нужно.',
             'link': 'https://github.com/JustArchiNET/ArchiSteamFarm/wiki/Setting-up'},
            {'title': 'Проверьте пароль IPC',
             'text': 'Ферма возьмёт IPCPassword из ~/asf/config/ASF.json сама. Если ASF на '
                     'другом компьютере, укажите его адрес и пароль в «Настройки» → '
                     '«ArchiSteamFarm».'},
            {'title': 'Проверьте подключение',
             'text': 'Нажмите «Проверить подключение»: ферма спросит у ASF список ботов. Боты '
                     'должны быть в сети, иначе Steam ничего не добавит.'},
            {'title': 'Откуда берётся список',
             'text': 'Список свежих раздач ферма берёт из открытого списка ASFinfo — его же '
                     'читает плагин FreePackages для ASF. Проверка раз в 3 часа, за проход — '
                     'не больше 20 игр: так Steam не упирается в лимит.'},
        ]

    def check(self, values):
        found = self.manager.asf.check()
        if not found['online']:
            raise ValueError("ASF отвечает, но ни один бот не в сети")
        return {'account': ', '.join(found['online']), 'balance': None}

    def disconnect(self):
        self.stop(wait=10)
        self.manager.platformEntry(self.key)['connected'] = False
        self.manager.setAutostart(self.key, False)
        self.manager.saveFarm()

    # ---- the work ---------------------------------------------------------------

    def feed(self):
        try:
            response = requests.get(FEED, timeout=30)
            response.raise_for_status()
        except requests.RequestException as error:
            raise ValueError(f"список бесплатных игр недоступен: {error}") from error
        return parseFeed(response.text)

    def appName(self, kind, ident):
        if kind != 'app':
            return f"Пакет {ident}"
        try:
            data = requests.get(APP_INFO, params={'appids': ident, 'l': 'english'},
                                timeout=20).json()
            return data[str(ident)]['data']['name']
        except Exception:
            return f"App {ident}"

    def candidates(self, conf):
        seen = self.manager.state.seen(self.key)
        fresh = [item for item in self.feed() if f"{item[0]}/{item[1]}" not in seen]
        return fresh[:max(1, conf['per_pass'] or PER_PASS)]

    def skipReason(self, conf, name):
        reason = presetReason(name, conf.get('skip_junk'), conf.get('skip_adult'))
        if reason:
            return reason
        if conf.get('blacklist') and any(word.lower() in name.lower()
                                         for word in conf['blacklist']):
            return 'в чёрном списке'
        return None

    def preview(self):
        conf = self.settings()
        items = []
        for kind, ident in self.candidates(conf):
            name = self.appName(kind, ident)
            reason = self.skipReason(conf, name)
            items.append({'name': name, 'url': STORE[kind].format(ident), 'cost': 0,
                          'entries': None, 'enter': reason is None, 'reason': reason or ''})
        note = '' if items else "Новых бесплатных игр в списке нет."
        return {'balance': None, 'account': '', 'items': items, 'note': note}

    def cycle(self, conf):
        state = self.manager.state
        wanted, names = {'app': [], 'sub': []}, {}
        for kind, ident in self.candidates(conf):
            name = self.appName(kind, ident)
            reason = self.skipReason(conf, name)
            if reason:
                state.markSeen(self.key, f"{kind}/{ident}")
                self.info(f"Пропуск {name}: {reason}")
                continue
            wanted[kind].append(ident)
            names[(kind, ident)] = name
        if not names:
            self.info("Новых бесплатных игр нет.")
            return 0
        results = self.manager.asf.addLicenses(wanted['app'], wanted['sub'])
        added = 0
        for item, name in names.items():
            verdict, words = results.get(item, ('retry', 'ASF не ответил'))
            if verdict != 'retry':
                state.markSeen(self.key, f"{item[0]}/{item[1]}")
            if verdict == 'ok':
                added += 1
                self.info(f"Вошёл: {name} — добавлено в библиотеку Steam")
                self.recordEntry(name, 0, STORE[item[0]].format(item[1]))
            else:
                self.info(f"{name}: {words}")
        return added

    def run(self):
        while not self.stopped:
            conf = self.gate()
            if conf is None:
                return
            try:
                added = self.cycle(conf)
                self.info(f"Проход окончен: добавлено {added}")
            except ValueError as error:
                self.warn(str(error))
            self.lastCycle = time.time()
            if not self.wait(max(30, conf['interval'] or 180) * 60):
                return
