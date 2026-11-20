"""Telegram messages laid out like the project page and the panel.

Every message is a card:

    🎉 ВЫИГРЫШ · SG SteamGifts          <- icon, title in capitals, site code
    Hollow Knight                        <- the point, bold, linked when it can be
    some lines of detail                 <- plain text
    ┌ a monospace block ┐                <- figures, like the page's log window
    [ Забрать ключ ] [ Выигрыши ]        <- buttons that open the panel or the site

Telegram gets HTML (parse_mode HTML) and an inline keyboard; Discord and the
command line get the same card as plain text. Everything that comes from a
site or a user is escaped here, so callers pass plain strings.
"""
import html

from dataclasses import dataclass, field

# The project page's short names for the sites.
SITE_CODES = {'steamgifts': 'SG', 'indiegala': 'IG', 'opiumpulses': 'OP', 'gog': 'GOG',
              'itch': 'ITCH', 'steamfree': 'STEAM'}

# A title for each kind of message, keyed by its icon.
TITLES = {
    '🎉': 'ВЫИГРЫШ', '🔑': 'НУЖЕН ВХОД', '⛔': 'ПЛОЩАДКА ОСТАНОВЛЕНА', '⚠️': 'ВНИМАНИЕ',
    '✅': 'ГОТОВО', '🎁': 'БЕСПЛАТНО', '⏳': 'ПОВТОРИМ ПОЗЖЕ', '📊': 'СВОДКА ЗА СУТКИ',
    'ℹ️': 'ФЕРМА', '💙': 'ПОДДЕРЖАТЬ ПРОЕКТ',
}

MAX_LINES = 30


def esc(text):
    return html.escape(str(text), quote=False)


def code(key):
    """'SG' for 'steamgifts', 'IG' for a second IndieGala account 'indiegala-2'."""
    return SITE_CODES.get((key or '').rsplit('-', 1)[0], (key or '').upper()[:5])


@dataclass
class Card:
    icon: str = 'ℹ️'
    title: str = ''
    site: str = ''              # the site's title, e.g. 'IndieGala · Брат'
    key: str = ''               # the site's key, for its short code
    headline: str = ''          # the point of the message, bold
    link: str = ''              # makes the headline a link
    lines: list = field(default_factory=list)       # plain lines, under the block
    block: list = field(default_factory=list)       # monospace lines, under the headline
    note: str = ''              # a quiet last line, in italics
    buttons: list = field(default_factory=list)     # [(text, url)]

    def heading(self):
        return self.title or TITLES.get(self.icon, TITLES['ℹ️'])

    def html(self):
        head = f"{self.icon} <b>{esc(self.heading())}</b>"
        if self.site:
            head += f" · <code>{esc(code(self.key))}</code> {esc(self.site)}"
        out = [head]
        if self.headline:
            text = f"<b>{esc(self.headline)}</b>"
            if safe(self.link):
                text = f'<a href="{html.escape(self.link)}">{text}</a>'
            out.append(text)
        if self.block:
            out.append('<pre>' + '\n'.join(esc(line) for line in self.block[:MAX_LINES]) + '</pre>')
        out += [esc(line) for line in self.lines[:MAX_LINES] if line]
        if self.note:
            out.append(f"<i>{esc(self.note)}</i>")
        return '\n'.join(out)

    def plain(self):
        head = f"{self.icon} {self.heading()}"
        if self.site:
            head += f" · {self.site}"
        out = [head]
        if self.headline:
            out.append(self.headline + (f" — {self.link}" if safe(self.link) else ''))
        out += self.block[:MAX_LINES]
        out += [line for line in self.lines[:MAX_LINES] if line]
        if self.note:
            out.append(self.note)
        out += [f"{text}: {url}" for text, url in self.buttons if safe(url)]
        return '\n'.join(out)

    def keyboard(self):
        row = [{'text': text, 'url': url} for text, url in self.buttons if safe(url)]
        return {'inline_keyboard': [row[i:i + 2] for i in range(0, len(row), 2)]} if row else None

    # The same card with the buttons spelled out as links, for when Telegram
    # refuses a button (it may not accept a LAN address in one).
    def withoutButtons(self):
        lines = self.lines + [f"{text}: {url}" for text, url in self.buttons if safe(url)]
        return Card(self.icon, self.title, self.site, self.key, self.headline, self.link,
                    lines, self.block, self.note, [])


def safe(url):
    return isinstance(url, str) and url.startswith(('https://', 'http://'))


# A table for a monospace block: columns padded to the widest cell.
def table(rows):
    rows = [[str(cell) for cell in row] for row in rows]
    if not rows:
        return []
    widths = [max(len(row[i]) for row in rows if i < len(row)) for i in range(max(map(len, rows)))]
    return ['  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]
