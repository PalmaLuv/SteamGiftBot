#!/usr/bin/env python3
"""Builds the project page in every language from site/template.html and
site/i18n/<lang>.json:

  docs/index.html      Russian (the default)
  docs/uk/index.html   Ukrainian
  docs/en/index.html   English
  docs/sitemap.xml     all three, with hreflang links

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

REPO = 'https://github.com/PalmaLuv/SteamGiftBot'
# The released version, for search engines: the package says which it is.
VERSION = re.search(r"__version__ = '([^']+)'",
                    (ROOT / 'steamgiftbot' / '__init__.py').read_text(encoding='utf-8')).group(1)
# The same wallet as steamgiftbot/farm/support.py on the farm's branch.
TON = 'UQBhyAtIaZxHiiLsLjmJtnG8sFmNiG77k2xkWfgr0xka7X2J'

LANGS = [('ru', '', 'RU'), ('uk', 'uk/', 'UK'), ('en', 'en/', 'EN')]
PLACEHOLDER = re.compile(r'\{\{([a-zA-Z0-9_.]+)\}\}')
TAG = re.compile(r'<[^>]+>')
SHOTS = ['overview', 'preview', 'connect', 'settings', 'mobile']


def plain(text):
    return html.unescape(TAG.sub('', text)).strip()


def structured_data(lang, folder, strings):
    """schema.org for search engines and AI answers: the site, the program
    and the FAQ, all in the page's own language. Built from the same strings
    the page shows, so the two never disagree."""
    url = URL + folder
    faq = strings['faq']
    count = sum(1 for key in faq if re.fullmatch(r'q\d+', key))
    author = {'@type': 'Person', '@id': URL + '#author', 'name': 'PalmaLuv',
              'url': 'https://github.com/PalmaLuv'}
    graph = [
        {'@type': 'WebSite', '@id': URL + '#website', 'url': URL, 'name': 'SteamGiftBot',
         'inLanguage': [code for code, _, _ in LANGS], 'publisher': {'@id': URL + '#author'}},
        {'@type': 'WebPage', '@id': url + '#page', 'url': url, 'name': strings['meta']['title'],
         'description': strings['meta']['description'], 'inLanguage': lang,
         'isPartOf': {'@id': URL + '#website'}, 'about': {'@id': URL + '#app'},
         'primaryImageOfPage': f'{URL}images/og-{lang}.png'},
        {'@type': 'SoftwareApplication', '@id': URL + '#app', 'name': 'SteamGiftBot',
         'description': strings['meta']['description'], 'url': url,
         'applicationCategory': 'UtilitiesApplication',
         'applicationSubCategory': 'Game giveaway bot',
         'operatingSystem': 'Windows, Linux, macOS, Docker',
         'license': 'https://www.mozilla.org/en-US/MPL/2.0/', 'isAccessibleForFree': True,
         'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'},
         'softwareVersion': VERSION,
         'downloadUrl': REPO + '/releases/latest', 'installUrl': url + '#install',
         'softwareHelp': WIKI, 'sameAs': [REPO, WIKI.rstrip('/')],
         'featureList': [plain(strings['farm'][f's{i}t']) for i in range(1, 6)]
                        + [plain(strings['farm'][f'c{i}t']) for i in range(1, 4)],
         'screenshot': [f'{URL}images/{name}.png' for name in SHOTS],
         'author': author},
        {'@type': 'SoftwareSourceCode', '@id': URL + '#code', 'name': 'SteamGiftBot',
         'codeRepository': REPO, 'programmingLanguage': 'Python',
         'runtimePlatform': 'Python 3.10+', 'license': 'https://www.mozilla.org/en-US/MPL/2.0/',
         'targetProduct': {'@id': URL + '#app'},
         'author': author},
        {'@type': 'FAQPage', '@id': url + '#faq', 'inLanguage': lang, 'mainEntity': [
            {'@type': 'Question', 'name': plain(faq[f'q{i}']),
             'acceptedAnswer': {'@type': 'Answer', 'text': plain(faq[f'a{i}'])}}
            for i in range(1, count + 1)]},
    ]
    # </script> inside the JSON would end the tag early.
    return json.dumps({'@context': 'https://schema.org', '@graph': graph},
                      ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def sitemap():
    """One entry per language, each listing all its translations, which is
    how Google wants hreflang in a sitemap."""
    links = ''.join(f'\n    <xhtml:link rel="alternate" hreflang="{code}" href="{URL}{path}"/>'
                    for code, path, _ in LANGS)
    links += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{URL}en/"/>'
    urls = ''.join(f'\n  <url>\n    <loc>{URL}{path}</loc>{links}\n  </url>'
                   for _, path, _ in LANGS)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + urls + '\n</urlset>\n')


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
    alternates += f'\n<link rel="alternate" hreflang="x-default" href="{URL}en/">'
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
        'langLinks': ''.join(links), 'wiki': WIKI, 'version': VERSION, 'ton': TON,
        'term.static': html.escape('\n'.join(strings['term']['lines'])),
        # </script> inside the JSON would end the tag early.
        'js': json.dumps(script, ensure_ascii=False).replace('</', '<\\/'),
        'ogImage': f'{URL}images/og-{lang}.png',
        'ogLocales': '\n'.join(f'<meta property="og:locale:alternate" content="{loc}">'
                               for loc in strings['_locales'] if loc != strings['meta']['locale']),
        'jsonld': structured_data(lang, folder, strings),
    })

    def fill(found):
        name = found.group(1)
        if name not in values or isinstance(values[name], list):
            raise SystemExit(f"{lang}: no string for {{{{{name}}}}}")
        value = str(values[name])
        inAttribute = template[:found.start()].endswith('="')
        return html.escape(value, quote=True) if inAttribute and name not in (
            'base', 'canonical', 'wiki', 'ogImage') else value
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
    locales = [texts[code]['meta']['locale'] for code, _, _ in LANGS]
    outputs = [(DOCS / 'sitemap.xml', sitemap())]
    for code, folder, _ in LANGS:
        outputs.append((DOCS / folder / 'index.html',
                        page(template, code, folder, {**texts[code], '_locales': locales})))
    stale = []
    for target, built in outputs:
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
