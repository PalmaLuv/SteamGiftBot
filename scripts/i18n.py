#!/usr/bin/env python3
"""The panel's translations.

The panel is written in Russian. When another language is chosen, the page
swaps every Russian phrase it shows for the one in
steamgiftbot/farm/static/i18n/<lang>.json, including the messages the farm
itself sends (log lines, reasons, setting labels).

  python scripts/i18n.py extract   # list every phrase -> static/i18n/phrases.json
  python scripts/i18n.py check     # fail if a language misses a phrase
  python scripts/i18n.py missing en  # print the phrases en.json still lacks

Phrases are collected from the page's markup and string literals and from the
farm's Python string literals, cut at ${...} / {...} placeholders and HTML
tags, so a sentence built from parts is translated part by part.
"""
import ast
import json
import re
import sys

from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
FARM   = ROOT / 'steamgiftbot' / 'farm'
PAGE   = FARM / 'static' / 'index.html'
I18N   = FARM / 'static' / 'i18n'
LANGUAGES = ('en', 'uk')
# Server-side text the panel shows: the farm package and the bot's settings.
PYTHON = sorted(FARM.glob('*.py')) + [ROOT / 'steamgiftbot' / 'settings.py']

CYRILLIC = re.compile(r'[А-Яа-яЁёІіЇїЄєҐґ]')
TAG      = re.compile(r'<[^<>]*>')
PLACE_JS = re.compile(r'\$\{(?:[^{}]|\{[^{}]*\})*\}')
PLACE_PY = re.compile(r'\{[^{}]*\}')
ENTITY   = {'&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&nbsp;': ' '}


LABEL_ATTR = re.compile(r'(?:title|placeholder|aria-label|alt|label)="([^"]*)"')
ANY_ATTR   = re.compile(r'[\w:-]+="[^"]*"')


def pieces(text):
    """The Russian runs of a string once tags and placeholders are cut out.
    A template cut at ${...} can leave half a tag behind; its visible
    attributes are kept, the rest of it is dropped."""
    for entity, char in ENTITY.items():
        text = text.replace(entity, char)
    out = []
    for value in LABEL_ATTR.findall(text):
        out += pieces(value)
    text = ANY_ATTR.sub(' ', text)
    text = re.sub(r'<[^<>]*$', ' ', text)
    text = re.sub(r'^[^<>]*?(?=>)>', ' ', text) if re.match(r'^[^<>]*>', text) and \
        re.match(r'^\s*[\w-]', text) and not CYRILLIC.search(text.split('>', 1)[0]) else text
    for part in TAG.split(text):
        for line in part.split('\n'):
            line = re.sub(r'\s+', ' ', line)
            # Ends of a tag cut by ${...}: 'aria-label="Text', '>Text', 'Text">'.
            line = re.sub(r'^[^А-Яа-яЁёІіЇїЄєҐґ]*?[\w:-]+="', '', line)
            line = re.sub(r'^[^А-Яа-яЁёІіЇїЄєҐґ<]*>', '', line)
            line = re.sub(r'"?\s*/?>\s*$', '', line)
            line = line.strip(' \t·—–:,;.()|/"\'`')
            # «Quotes» stay with their words, but a quote left alone at the
            # edge by a cut belongs to the text around it.
            if line.startswith('»') or line.startswith('«') and '»' not in line:
                line = line[1:]
            if line.endswith('«') or line.endswith('»') and '«' not in line:
                line = line[:-1]
            line = line.strip(' \t·—–:,;.()|/"\'`')
            if line and CYRILLIC.search(line):
                out.append(line)
    return out


REGEX_BEFORE = set('(,=:[!&|?{};+-*%<>~^')


def jsLiterals(src):
    """The text of every string and template part in a script. A small
    scanner rather than a regex: templates nest (`a ${b ? `c` : 'd'} e`),
    and regex literals such as /[&<>"']/ hold quotes."""
    out, i, n = [], 0, len(src)
    braces = []          # one counter per open ${ … } of a template

    def template(i):
        part = []
        while i < n:
            c = src[i]
            if c == '\\':
                part.append(src[i:i + 2])
                i += 2
            elif c == '`':
                out.append(''.join(part))
                return i + 1, False
            elif src.startswith('${', i):
                out.append(''.join(part))
                braces.append(0)
                return i + 2, True
            else:
                part.append(c)
                i += 1
        return i, False

    last = ''
    while i < n:
        c = src[i]
        if c in '\'"':
            j, part = i + 1, []
            while j < n and src[j] != c and src[j] != '\n':
                part.append(src[j:j + 2] if src[j] == '\\' else src[j])
                j += 2 if src[j] == '\\' else 1
            out.append(''.join(part))
            i, last = j + 1, 'x'
        elif c == '`':
            i, _ = template(i + 1)
            last = 'x'
        elif src.startswith('//', i):
            i = src.find('\n', i)
            i = n if i < 0 else i
        elif src.startswith('/*', i):
            i = src.find('*/', i + 2)
            i = n if i < 0 else i + 2
        elif c == '/' and (last in REGEX_BEFORE or last == ''):
            j, inClass = i + 1, False
            while j < n and src[j] != '\n':
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '[':
                    inClass = True
                elif src[j] == ']':
                    inClass = False
                elif src[j] == '/' and not inClass:
                    break
                j += 1
            i, last = j + 1, 'x'
        elif c == '{' and braces:
            braces[-1] += 1
            i, last = i + 1, c
        elif c == '}' and braces:
            if braces[-1] == 0:
                braces.pop()
                i, _ = template(i + 1)
                last = 'x'
            else:
                braces[-1] -= 1
                i, last = i + 1, c
        else:
            if not c.isspace():
                last = c if c in REGEX_BEFORE else 'x'
            i += 1
    return out


def jsStrings(source):
    """Phrases in the page: its scripts' literals and its static markup."""
    found = []
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', source, re.S)
    for script in scripts:
        for literal in jsLiterals(script):
            found += pieces(literal)
    markup = re.sub(r'<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<!--.*?-->', '', source,
                    flags=re.S)
    found += pieces(markup)
    for match in re.finditer(r'(?:title|placeholder|aria-label|alt|content)="([^"]*)"', markup):
        found += pieces(match.group(1))
    return found


def pyStrings(path):
    found = []
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(('\n', ' ')) and len(node.value) > 300:
                continue   # long docstrings are for developers
            found += [piece for part in PLACE_PY.split(node.value) for piece in pieces(part)]
    # Docstrings and comments are not shown, but a docstring is a Constant too:
    # drop the ones that open a module, class or function.
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docs.update(pieces(doc))
    return [item for item in found if item not in docs]


def extract():
    phrases = set(jsStrings(PAGE.read_text(encoding='utf-8')))
    for path in PYTHON:
        phrases.update(pyStrings(path))
    return sorted(phrases, key=lambda item: (-len(item), item))


def load(lang):
    path = I18N / f'{lang}.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def main(argv):
    command = argv[1] if len(argv) > 1 else 'extract'
    if command in ('-h', '--help', 'help') or any(arg in ('-h', '--help') for arg in argv[2:]):
        print(__doc__)
        return 0
    phrases = extract()
    if command == 'extract':
        I18N.mkdir(parents=True, exist_ok=True)
        (I18N / 'phrases.json').write_text(json.dumps(phrases, ensure_ascii=False, indent=0),
                                           encoding='utf-8')
        print(f"{len(phrases)} phrases -> {I18N / 'phrases.json'}")
        return 0
    if command == 'missing':
        table = load(argv[2])
        lacking = [item for item in phrases if item not in table]
        print(json.dumps(lacking, ensure_ascii=False, indent=0))
        return 0
    if command == 'check':
        bad = 0
        for lang in LANGUAGES:
            table = load(lang)
            lacking = [item for item in phrases if item not in table]
            if lacking:
                bad += 1
                print(f"{lang}: {len(lacking)} phrases without a translation, e.g. {lacking[:5]}")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
