"""The real writer path exports a viewed revision without executing its source."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.engine import build as building
from cadgen.engine.export import Source, ExportRefused
from cadgen.engine.export.viewer import fingerprint
from cadgen.engine.worker import _export


class ViewerExportsTest(unittest.TestCase):
    def test_formats_version_pinning_and_live_model_never_rebuilds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            script = root / "part.py"
            script.write_text('from cadgen import xbf\nimport build123d as bd\n@xbf("part.xbf")\ndef part():\n    return bd.Box(2, 3, 4)\n', encoding="utf-8")
            reports = building.build(script, ["part"], cwd=root)
            self.assertTrue(reports[0]["ok"], reports)
            source = Source.read(root / "part.xbf")
            expected = {"version": source.structure["version"]}
            request = {"source": {"path": str(source.path)}, "expected": expected, "destinations": [], "inspect": True}
            formats = _export(request, lambda _: None)["formats"]
            allowed = {r["format"] for r in formats if not r["reason"]}
            self.assertEqual(allowed, {"step", "glb", "stl", "threemf", "original"})
            output = root / "export.stl"
            request.update(inspect=False, destinations=[str(output)])
            self.assertGreater(_export(request, lambda _: None)["files"][0]["bytes"], 84)
            with self.assertRaisesRegex(ExportRefused, "source changed"):
                _export({**request, "expected": {"version": "old"}}, lambda _: None)
            original = root / "original.xbf"
            _export({**request, "destinations": [str(original)], "original": True}, lambda _: None)
            self.assertEqual(original.read_bytes(), source.path.read_bytes())
            held = building.held(script, "part")
            script.write_text('raise RuntimeError("must not execute")', encoding="utf-8")
            with patch.object(building, "build", side_effect=AssertionError("viewer rebuilt source")):
                _export({**request, "source": {"script": str(script), "function": "part"},
                         "expected": {"digest": fingerprint(held.structure)}}, lambda _: None)
                with self.assertRaisesRegex(ExportRefused, "source changed"):
                    _export({**request, "source": {"script": str(script), "function": "part"},
                             "expected": {"digest": "old"}}, lambda _: None)

    def test_planar_dxf_and_no_xbf_of_an_xbf(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            script = root / "plate.py"
            script.write_text('from cadgen import xbf\nimport build123d as bd\n@xbf("plate.xbf")\ndef plate():\n    return bd.Rectangle(4, 3)\n', encoding="utf-8")
            reports = building.build(script, ["plate"], cwd=root)
            self.assertTrue(reports[0]["ok"], reports)
            source = Source.read(root / "plate.xbf")
            request = {"source": {"path": str(source.path)}, "expected": {"version": source.structure["version"]},
                       "destinations": [], "inspect": True}
            rows = _export(request, lambda _: None)["formats"]
            self.assertIsNone(next(r for r in rows if r["format"] == "dxf")["reason"])
            with self.assertRaisesRegex(ExportRefused, "not written from another xbf"):
                _export({**request, "inspect": False, "destinations": [str(root / "again.xbf")]}, lambda _: None)
            self.assertFalse((root / "again.xbf").exists())

class ViewerExportHttpTest(unittest.TestCase):
    def setUp(self):
        import os
        self.tmp = tempfile.TemporaryDirectory(prefix="viewer-export-http-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "models"
        self.root.mkdir()
        environment = patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(Path(self.tmp.name) / "engine")})
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(self.stop_engine)

    def stop_engine(self):
        from cadgen.engine.client import request, wait_gone
        request({"op": "stop"}, start=False)
        self.assertTrue(wait_gone(30), "test engine must release its Windows working directories")

    def test_live_model_export_through_authenticated_session_and_worker(self):
        import contextlib
        import json
        import urllib.request
        import urllib.error
        from urllib.parse import urlparse, parse_qs
        from cadgen.engine import api
        from cadgen.engine.client import request

        with contextlib.chdir(self.root):
            root = self.root
            # A bare model: its document is the worker's memory alone.
            script = root / 'export_http.py'
            script.write_text('import build123d as bd\nfrom cadgen import model\n\n\n@model\n'
                              'def export_http():\n    return bd.Box(2, 3, 4)\n', encoding='utf-8')
            built = api.build_script(script, ['export_http'])
            self.assertEqual(built.files, {})
            url = urlparse(built.models[0]['url'])
            doc = url.path.strip('/')
            session = request({'op': 'viewer', 'start': str(root), 'api_only': True})
            self.assertTrue(session.get('ok'), session)

            def http(path, body=None, *, headers=None):
                supplied = {'Authorization': 'Bearer ' + session['token'], 'x-cadgen-viewer': '1',
                            'content-type': 'application/json', **(headers or {})}
                query = urllib.request.Request(session['apiUrl'] + path,
                    data=json.dumps(body).encode() if body is not None else None, headers=supplied)
                try:
                    response = urllib.request.urlopen(query, timeout=30)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, response.headers, response.read()

            _, _, data = http('/api/doc/' + doc)
            structure = json.loads(data)
            source = {'doc': doc, 'revision': structure['version']}
            code, _, _ = http('/__cad/exports/options', source, headers={'Authorization': ''})
            self.assertEqual(code, 403)
            code, _, _ = http('/__cad/exports/options', source, headers={'x-cadgen-viewer': ''})
            self.assertEqual(code, 403)
            # Inspection is asynchronous. A real export shares its worker and completes
            # after it; long-polling the job waits for observable changes, not a sleep.
            code, _, data = http('/__cad/exports/options', source)
            self.assertIn(code, (200, 202))
            # Epoch is public only once inspection has settled. The session's job
            # capability response is bounded by the worker, which status can observe.
            while code == 202:
                code, _, data = http('/__cad/exports/options', source)
            self.assertEqual(code, 200, data)
            payload = {'requestId': 'http-export-request-0001', 'epoch': json.loads(data)['epoch'],
                       'source': source, 'format': 'stl'}
            code, _, data = http('/__cad/exports', payload)
            self.assertEqual(code, 202, data)
            job = json.loads(data)
            _, _, duplicate = http('/__cad/exports', payload)
            self.assertEqual(json.loads(duplicate)['id'], job['id'])
            while job['state'] in ('queued', 'running'):
                _, _, data = http(f"/__cad/exports/{job['id']}?after={job['sequence']}&wait=25")
                job = json.loads(data)
            self.assertEqual(job['state'], 'ready', job)
            code, headers, data = http(f"/__cad/exports/{job['id']}/file")
            self.assertEqual(code, 200)
            self.assertEqual(len(data), job['bytes'])
            self.assertGreater(len(data), 84)
            self.assertIn('attachment;', headers['content-disposition'])
            http(f"/__cad/exports/{job['id']}/release", {})
            self.assertEqual(http(f"/__cad/exports/{job['id']}/file")[0], 410)
            # Even a rebuild with identical geometry is a different displayed generation.
            api.build_script(script, ['export_http'])
            payload['requestId'] = 'http-export-request-0002'
            _, _, data = http('/__cad/exports', payload)
            job = json.loads(data)
            while job['state'] in ('queued', 'running'):
                _, _, data = http(f"/__cad/exports/{job['id']}?after={job['sequence']}&wait=25")
                job = json.loads(data)
            self.assertEqual(job['state'], 'failed', job)
            self.assertIn('source changed', job['error'])
            _, _, data = http('/api/doc/' + doc + '/version')
            self.assertIsNone(json.loads(data)['failed'], 'an export failure is not a model build failure')
            self.assertEqual(list(root.iterdir()), [script], 'no implicit source or intermediate artifact')


if __name__ == "__main__":
    unittest.main()
