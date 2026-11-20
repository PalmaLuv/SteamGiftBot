#!/usr/bin/env python3
"""Fills the generated parts of docs/wiki from the code itself, so the wiki
cannot drift from what the panel really offers:

  <!-- settings:indiegala --> ... <!-- /settings -->   one site's settings
  <!-- settings:farm --> ... <!-- /settings -->        the farm's own settings
  <!-- presets --> ... <!-- /presets -->               ready-made presets
  <!-- words:junk --> / <!-- words:adult -->           word filters

Run from the repository root: env/bin/python scripts/build-wiki.py
--check exits 1 when a page is out of date (for CI)."""
import re
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steamgiftbot.farm import base, rules  # noqa: E402
from steamgiftbot.farm.manager import FARM_FIELDS, FarmManager  # noqa: E402

WIKI = ROOT / 'docs' / 'wiki'
BLOCK = re.compile(r'(<!-- (settings:[a-z]+|presets|words:[a-z]+) -->\n)(.*?)'
                   r'(<!-- /[a-z]+ -->)', re.S)


def shown(value, kind):
    if kind == 'bool':
        return 'вкл' if value else 'выкл'
    if kind == 'secret':
        return '—'
    if value is None or value == '' or value == []:
        return 'пусто'
    if isinstance(value, list):
        return ', '.join(value)
    return f'`{value}`'


def settingsTable(schema):
    lines, group = [], None
    for item in schema:
        if item.get('group') != group:
            group = item.get('group')
            lines += ['', f'**{group}**', '', '| Настройка | По умолчанию | Что делает |',
                      '| --- | --- | --- |']
        about = (item.get('help') or '').replace('|', '\\|')
        if item['kind'] == 'select':
            options = ', '.join(f'`{option}`' for option in item['options'])
            about = (about.rstrip('.') + '. ' if about else '') + f'Варианты: {options}.'
        lines.append(f"| {item['label']} | {shown(item['default'], item['kind'])} | {about} |")
    return '\n'.join(lines).lstrip('\n') + '\n'


def presetsTable():
    names = {'skip_junk': 'без DLC и паков', 'skip_adult': 'без 18+', 'skip_owned': 'без своих игр',
             'sort': 'порядок IndieGala', 'max_entries': 'макс. участников',
             'reserve': 'резерв IndieGala/OP', 'min_points': 'минимум поинтов SteamGifts',
             'free_only': 'OpiumPulses только бесплатные', 'max_pages': 'страниц за проход'}
    lines = ['| Набор | Для чего | Что меняет |', '| --- | --- | --- |']
    for preset in base.PRESETS:
        values = []
        for key, value in preset['values'].items():
            if value is True or value is False or value is None:
                value = {True: 'да', False: 'нет', None: 'без предела'}[value]
            values.append(f"{names.get(key, key)}: {value}")
        lines.append(f"| {preset['title']} | {preset['description']} | {'; '.join(values)} |")
    return '\n'.join(lines) + '\n'


def fill():
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, 'config.ini').write_text(
            "[DEFAULT]\ncookie = x\ngift_type = All\npinned = yes\nmin_points = 30\n")
        manager = FarmManager(dataDir=folder, configPath=Path(folder, 'config.ini'))
        parts = {f'settings:{key}': settingsTable(platform.schema())
                 for key, platform in manager.platforms.items()}
    parts['settings:farm'] = settingsTable(FARM_FIELDS)
    parts['presets'] = presetsTable()
    parts['words:junk'] = ', '.join(f'`{word}`' for word in rules.JUNK_WORDS) + '\n'
    parts['words:adult'] = ', '.join(f'`{word}`' for word in rules.ADULT_WORDS) + ', `18+`\n'
    return parts


def main():
    parts, stale = fill(), []
    for page in sorted(WIKI.glob('*.md')):
        text = page.read_text(encoding='utf-8')

        unknown = sorted({found.group(2) for found in BLOCK.finditer(text)} - set(parts))
        if unknown:
            raise SystemExit(f"{page.name}: unknown block {', '.join(unknown)}")
        fresh = BLOCK.sub(lambda found: found.group(1) + parts[found.group(2)] + found.group(4),
                          text)
        if fresh != text:
            stale.append(page.name)
            if '--check' not in sys.argv:
                page.write_text(fresh, encoding='utf-8')
    if stale:
        print(('out of date: ' if '--check' in sys.argv else 'updated: ') + ', '.join(stale))
    if stale and '--check' in sys.argv:
        sys.exit(1)


if __name__ == '__main__':
    main()
