"""The project page is built from site/template.html and site/i18n; this fails
when someone edits a translation and forgets to run scripts/build-site.py, or
when one language lacks a string the others have."""
import json
import subprocess
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_site_pages_match_the_template():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build-site.py'), '--check'],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_language_page_exists_and_names_its_language():
    for folder, lang in (('', 'ru'), ('uk/', 'uk'), ('en/', 'en')):
        page = (ROOT / 'docs' / folder / 'index.html').read_text(encoding='utf-8')
        assert f'<html lang="{lang}"' in page
        assert '{{' not in page
        data = page.split('<script id="i18n" type="application/json">')[1].split('</script>')[0]
        assert json.loads(data)['lines']
