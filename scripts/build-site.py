#!/usr/bin/env python3
"""Builds the project page in every language from site/template.html and
site/i18n/<lang>.json:

  docs/index.html      Russian (the default)
  docs/uk/index.html   Ukrainian
  docs/en/index.html   English

{{a.b}} in the template is the string at a.b; inside an attribute it is
escaped, in text it is taken as HTML (the strings carry links and <code>).
Every language must have exactly the same keys. --check exits 1 when a page
on disk differs from what the template would give."""
import html
import json
import re
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'
DOCS = ROOT / 'docs'
URL = 'https://palmaluv.github.io/SteamGiftBot/'
WIKI = 'https://github.com/PalmaLuv/SteamGiftBot/wiki/'

LANGS = [('ru', '', 'RU'), ('uk', 'uk/', 'UK'), ('en', 'en/', 'EN')]
PLACEHOLDER = re.compile(r'\{\{([a-zA-Z0-9_.]+)\}\}')


def flatten(data, prefix=''):
    out = {}
    for key, value in data.items():
        name = f'{prefix}{key}'
        if isinstance(value, dict):
            out.update(flatten(value, name + '.'))
        else:
            out[name] = value
    return out


def page(template, lang, folder, strings):
    base = '../' * folder.count('/')
    alternates = '\n'.join(f'<link rel="alternate" hreflang="{code}" href="{URL}{path}">'
                           for code, path, _ in LANGS)
    alternates += f'\n<link rel="alternate" hreflang="x-default" href="{URL}">'
    links = []
    for code, path, label in LANGS:
        href = base + path or './'
        current = ' aria-current="true"' if code == lang else ''
        links.append(f'<a href="{href}" hreflang="{code}" lang="{code}"{current}>{label}</a>')
    script = dict(strings['js'])
    script['lines'] = strings['term']['lines']
    values = flatten(strings)
    values.update({
        'lang': lang, 'base': base, 'canonical': URL + folder, 'alternates': alternates,
        'langLinks': ''.join(links), 'wiki': WIKI,
        'term.static': html.escape('\n'.join(strings['term']['lines'])),
        # </script> inside the JSON would end the tag early.
        'js': json.dumps(script, ensure_ascii=False).replace('</', '<\\/'),
    })

    def fill(found):
        name = found.group(1)
        if name not in values or isinstance(values[name], list):
            raise SystemExit(f"{lang}: no string for {{{{{name}}}}}")
        value = str(values[name])
        inAttribute = template[:found.start()].endswith('="')
        return html.escape(value, quote=True) if inAttribute and name not in (
            'base', 'canonical', 'wiki') else value
    return PLACEHOLDER.sub(fill, template)


def main():
    template = (SITE / 'template.html').read_text(encoding='utf-8')
    texts = {code: json.loads((SITE / 'i18n' / f'{code}.json').read_text(encoding='utf-8'))
             for code, _, _ in LANGS}
    reference = set(flatten(texts['ru']))
    for code, strings in texts.items():
        keys = set(flatten(strings))
        if keys != reference:
            missing, extra = sorted(reference - keys), sorted(keys - reference)
            raise SystemExit(f"{code}.json: missing {missing}, extra {extra}")
    stale = []
    for code, folder, _ in LANGS:
        target = DOCS / folder / 'index.html'
        built = page(template, code, folder, texts[code])
        if not target.exists() or target.read_text(encoding='utf-8') != built:
            stale.append(str(target.relative_to(ROOT)))
            if '--check' not in sys.argv:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(built, encoding='utf-8')
    if stale:
        print(('out of date: ' if '--check' in sys.argv else 'built: ') + ', '.join(stale))
        if '--check' in sys.argv:
            sys.exit(1)


if __name__ == '__main__':
    main()
