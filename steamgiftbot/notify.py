#    ______                   ______ _____    ___
#   / __/ /____ ___ ___ _    / ___(_) _/ /_  / _ \___ ________ ___ ____
#  _\ \/ __/ -_) _ `/  ' \  / (_ / / _/ __/ / ___/ _ `/ __(_-</ -_) __/
# /___/\__/\__/\_,_/_/_/_/  \___/_/_/ \__/ /_/   \_,_/_/ /___/\__/_/
#
# Created by: github.com/PalmaLuv
# Stay tuned for further app updates
# License : MPL-2.0
"""Optional end of run messages to Discord or Telegram.

A scheduled run finishes with nobody watching the terminal, so this is how the
bot says what it did. Delivery problems are reported and then dropped: a failed
notification must never turn a good run into a failed one.
"""
import requests

TELEGRAM_API     = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"
TIMEOUT          = 15

# Every kind of update that carries a chat, so a group or a channel is found as
# readily as a private conversation.
UPDATE_KINDS = ('message', 'edited_message', 'channel_post', 'edited_channel_post',
                'my_chat_member', 'callback_query')


# Neither service raises on a refusal: a wrong token comes back as a tidy 401
# with a JSON body. Without this check --notify-test would report success while
# nothing was delivered.
class NotifyError(Exception):
    pass


def describe(response):
    try:
        body = response.json()
    except Exception:
        text = (getattr(response, 'text', '') or '').strip()
        return text[:200]
    if isinstance(body, dict):
        return str(body.get('description') or body.get('message') or body)[:200]
    return str(body)[:200]


def checkAnswer(response, service):
    status = getattr(response, 'status_code', None)
    if status is None:
        return
    if not 200 <= status < 300:
        raise NotifyError(f"{service} refused the request (HTTP {status}): "
                          f"{describe(response)}")
    # Telegram can also answer 200 with ok=false.
    try:
        body = response.json()
    except Exception:
        return
    if isinstance(body, dict) and body.get('ok') is False:
        raise NotifyError(f"{service} refused the request: {describe(response)}")


# Telegram is on as soon as a token and a chat exist, unless it was switched
# off on purpose. That way a filled in config.ini just works.
def telegramReady(config):
    return bool(config.telegram_token and config.telegram_chat
                and config.telegram_enabled is not False)


def isConfigured(config):
    return bool(config.discord_webhook) or telegramReady(config)


def chatName(chat):
    parts = [chat.get('first_name'), chat.get('last_name')]
    name = chat.get('title') or ' '.join(p for p in parts if p) or chat.get('username')
    return name or ''


def describeChat(chat):
    return f"{chat.get('id')}  {chat.get('type', 'chat'):10} {chatName(chat)}".rstrip()


# Asks Telegram who has written to the bot lately. This is how you learn your
# own chat id: there is no way to look it up, the bot has to be spoken to first.
# Telegram only keeps updates for about a day.
def findChats(token, session=None):
    getter = session.get if session else requests.get
    try:
        response = getter(TELEGRAM_UPDATES.format(token=token), timeout=TIMEOUT)
    except requests.RequestException as error:
        raise NotifyError(f"Could not reach Telegram: {error}") from error

    checkAnswer(response, 'Telegram')

    try:
        body = response.json()
    except ValueError as error:
        raise NotifyError("Telegram sent something that was not JSON.") from error

    found = {}
    for update in body.get('result') or []:
        for kind in UPDATE_KINDS:
            carrier = update.get(kind)
            if not isinstance(carrier, dict):
                continue
            chat = carrier.get('chat') or (carrier.get('message') or {}).get('chat')
            if isinstance(chat, dict) and 'id' in chat:
                found[chat['id']] = chat
    return list(found.values())


def sendDiscord(webhook, text, session=None):
    poster = session.post if session else requests.post
    checkAnswer(poster(webhook, json={'content': text}, timeout=TIMEOUT), 'Discord')


def sendTelegram(token, chat, text, session=None):
    poster = session.post if session else requests.post
    checkAnswer(poster(TELEGRAM_API.format(token=token),
                       json={'chat_id': chat, 'text': text}, timeout=TIMEOUT), 'Telegram')


# Returns the list of problems met while delivering, empty when all went well.
# A NotifyError already names the service it came from; a network error does not.
def describeProblem(service, error):
    return str(error) if isinstance(error, NotifyError) else f"{service}: {error}"


def send(config, text, session=None):
    problems = []

    if config.discord_webhook:
        try:
            sendDiscord(config.discord_webhook, text, session)
        except (requests.RequestException, NotifyError) as error:
            problems.append(describeProblem('Discord', error))

    if telegramReady(config):
        try:
            sendTelegram(config.telegram_token, config.telegram_chat, text, session)
        except (requests.RequestException, NotifyError) as error:
            problems.append(describeProblem('Telegram', error))

    return problems
