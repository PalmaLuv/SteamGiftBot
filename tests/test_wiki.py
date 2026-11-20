"""The wiki's settings tables are generated from the code; this fails when
someone changes a setting and forgets to run scripts/build-wiki.py."""
import subprocess
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wiki_tables_match_the_code():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build-wiki.py'), '--check'],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_wiki_links_point_to_pages_that_exist():
    import re
    wiki = ROOT / 'docs' / 'wiki'
    pages = {page.name for page in wiki.glob('*.md')}
    for page in wiki.glob('*.md'):
        text = page.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)#]+\.md)(?:#[^)]*)?\)', text):
            if target.startswith('../'):
                assert (wiki / target).exists(), f"{page.name} -> {target}"
            else:
                assert target in pages, f"{page.name} -> {target}"
