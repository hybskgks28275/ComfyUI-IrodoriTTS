"""Check that untranslated backend metadata remains usable in every locale."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LocaleTests(unittest.TestCase):
    def test_backend_display_metadata_is_english(self):
        for path in (ROOT / 'src' / 'nodes').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.keyword) and node.arg in {'description', 'tooltip', 'placeholder', 'display_name'}:
                    value = ast.literal_eval(node.value)
                    with self.subTest(file=path.name, text=value):
                        self.assertIsNone(re.search('[ぁ-んァ-ヶ一-龠]', value))
