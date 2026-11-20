"""Every phrase the panel shows has an English and a Ukrainian translation.

When this fails, a Russian phrase was added or changed in the panel or in a
farm message: run `python scripts/i18n.py missing en` (and `uk`), add the
translations to steamgiftbot/farm/static/i18n/<lang>.json and run
`python scripts/i18n.py extract`."""
import importlib.util
import json
import re

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('i18n', ROOT / 'scripts' / 'i18n.py')
i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n)


def test_every_phrase_is_translated():
    phrases = i18n.extract()
    for lang in i18n.LANGUAGES:
        table = i18n.load(lang)
        lacking = [item for item in phrases if item not in table]
        assert not lacking, f"{lang}: {len(lacking)} untranslated, e.g. {lacking[:3]}"


def test_english_has_no_russian_left():
    table = i18n.load('en')
    russian = [value for value in table.values() if re.search('[А-Яа-яЁё]', value)]
    assert not russian, russian[:3]


def test_extractor_skips_code():
    phrases = i18n.extract()
    leaked = [item for item in phrases if re.search(r'[`{}$<>=]|=>', item)]
    assert not leaked, leaked[:3]


def test_dictionaries_are_valid_json_objects():
    for lang in i18n.LANGUAGES:
        data = json.loads((i18n.I18N / f'{lang}.json').read_text(encoding='utf-8'))
        assert isinstance(data, dict) and all(isinstance(v, str) and v for v in data.values())
