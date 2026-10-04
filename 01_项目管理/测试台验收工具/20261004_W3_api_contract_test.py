#!/usr/bin/env python3
"""Synthetic-only unittest for W3 static coverage auditor. No production imports."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('20261004_W3_api_contract_check.py')
spec = importlib.util.spec_from_file_location('audit_tool', MODULE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class CoverageTests(unittest.TestCase):
    def result(self, source, matrix):
        routes, count, issues = tool.extract(source, 'synthetic.py')
        entries, errors, groups = tool.parse_contract(matrix)
        return tool.compare(routes, count, entries, issues + errors, groups)

    def matrix(self, rows):
        return '## 一、契约矩阵\n| 方法 路径 | handler |\n' + rows

    def test_same_path_two_methods(self):
        result = self.result('@app.get("/p")\ndef a(): pass\n@app.post("/p")\ndef b(): pass',
                             self.matrix('| GET /p | a |\n| POST /p | b |'))
        self.assertTrue(result['ok'])
        self.assertEqual((2, 2, 1), (result['http_decorators'], result['http_operations'], result['http_unique_paths']))

    def test_prose_cannot_hide_missing_operation(self):
        result = self.result('@app.post("/p")\ndef a(): pass',
                             'POST /p mentioned in statistics\n' + self.matrix('| GET /p | a |'))
        self.assertEqual(['POST /p'], result['missing_from_matrix'])

    def test_exact_converter(self):
        result = self.result('@app.get("/asset/{path:path}")\ndef a(): pass',
                             self.matrix('| GET /asset/{path} | a |'))
        self.assertEqual(['GET /asset/{path:path}'], result['missing_from_matrix'])
        self.assertEqual(['GET /asset/{path}'], result['not_in_source'])

    def test_grouped_bold_rows_and_root(self):
        result = self.result('@app.get("/")\n@app.get("/a")\n@app.get("/b")\ndef a(): pass',
                             self.matrix('| **GET / /a /b** | a |'))
        self.assertTrue(result['ok'])
        self.assertEqual(1, len(result['grouped_rows']))

    def test_nested_registration_ws_separate(self):
        result = self.result('def register(app):\n @app.websocket("/ws")\n async def a(): pass',
                             self.matrix('') + '\n## 二、WebSocket（单列）\n| /ws | a |')
        self.assertTrue(result['ok'])
        self.assertEqual((0, 1), (result['http_decorators'], result['websocket_operations']))

    def test_multi_methods_decorator(self):
        result = self.result('@router.api_route(path="/p", methods=["GET", "POST"])\ndef a(): pass',
                             self.matrix('| GET /p | a |\n| POST /p | a |'))
        self.assertTrue(result['ok'])
        self.assertEqual((1, 2), (result['http_decorators'], result['http_operations']))

    def test_dynamic_path_flagged(self):
        result = self.result('@app.get(PREFIX + "/p")\ndef a(): pass', self.matrix('| GET /p | a |'))
        self.assertFalse(result['ok'])
        self.assertTrue(result['extraction_issues'])

    def test_prefix_manual_registration_flagged(self):
        source = 'router = APIRouter(prefix="/api")\napp.include_router(router)\napp.mount("/static", x)\napp.add_api_route("/a", a)'
        _, _, issues = tool.extract(source, 'synthetic.py')
        self.assertEqual(4, len(issues))

    def test_duplicate_operations(self):
        result = self.result('@app.get("/p")\ndef a(): pass\n@app.get("/p")\ndef b(): pass',
                             self.matrix('| GET /p | a |\n| GET /p | b |'))
        self.assertEqual(['GET /p'], result['duplicate_source_operations'])
        self.assertEqual(['GET /p'], result['duplicate_matrix_operations'])
        self.assertFalse(result['ok'])

    def test_no_source_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / 'executed'
            source = f'from pathlib import Path\nPath({str(marker)!r}).write_text("BAD")\nraise RuntimeError("must not execute")\n@app.get("/p")\ndef a(): pass'
            (root / 'source.py').write_text(source, encoding='utf-8')
            (root / 'contract.md').write_text(self.matrix('| GET /p | a |'), encoding='utf-8')
            result = tool.audit(root, ('source.py',), 'contract.md')
            self.assertTrue(result['ok'])
            self.assertFalse(marker.exists())
            self.assertEqual(2, len(result['inputs']))
            self.assertTrue(all(len(i['sha256']) == 64 for i in result['inputs']))

    def test_scope_excludes_later_prose(self):
        result = self.result('@app.get("/p")\ndef a(): pass',
                             self.matrix('| GET /p | a |') + '\n## 三、错误码\n| POST /fake | prose |')
        self.assertTrue(result['ok'])

    def test_malformed_matrix_fails_closed(self):
        result = self.result('@app.get("/p")\ndef a(): pass', self.matrix('| GET/POST /p | a |'))
        self.assertFalse(result['ok'])
        self.assertTrue(result['extraction_issues'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
