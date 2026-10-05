"""Native file reveal is explicit, takes a file by its absolute path, and uses platform argument arrays."""
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock
from cadgen.viewer.reveal import reveal_path
from .test_http_layer import ServerFixture


class RevealTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerFixture()
        self.addCleanup(self.server.close)
        self.target = Path(self.server.root, 'part with spaces.step')
        self.target.write_text('fixture', encoding='utf-8')

    def test_native_commands(self):
        target = str(self.target)
        with mock.patch('cadgen.viewer.reveal.subprocess.run') as run:
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'darwin'):
                reveal_path(target)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-R', str(self.target.resolve())])
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'linux'), mock.patch('cadgen.viewer.reveal.shutil.which', return_value=None):
                reveal_path(target)
                self.assertEqual(run.call_args.args[0], ['xdg-open', str(self.target.parent.resolve())])
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'linux'), mock.patch('cadgen.viewer.reveal.shutil.which', return_value='/usr/bin/dbus-send'):
                reveal_path(target)
                self.assertIn('array:string:' + self.target.resolve().as_uri(), run.call_args.args[0])
                run.side_effect = [subprocess.CalledProcessError(1, 'dbus-send'), None]
                reveal_path(target)
                self.assertEqual(run.call_args.args[0][0], 'xdg-open')
        with mock.patch('cadgen.viewer.reveal.sys.platform', 'win32'), mock.patch('cadgen.viewer.reveal.subprocess.Popen') as spawn:
            reveal_path(target)
            self.assertEqual(spawn.call_args.args[0], ['explorer.exe', '/select,' + str(self.target.resolve())])

    def test_rejects_relative_missing_and_invalid_paths(self):
        with mock.patch('cadgen.viewer.reveal.subprocess.run') as run:
            for path in (self.target.name, None, 1):
                with self.assertRaises(ValueError):
                    reveal_path(path)
            with self.assertRaises(FileNotFoundError):
                reveal_path(str(self.target.with_name('missing.step')))
            run.assert_not_called()

    def test_route_requires_browser_guard_and_valid_payload(self):
        headers = {'x-cadgen-viewer': '1', 'Content-Type': 'application/json'}
        body = json.dumps({'path': str(self.target)}).encode()
        with mock.patch('cadgen.viewer.reveal.reveal_path') as reveal:
            self.assertEqual(self.server.request('POST', '/__cad/reveal', body=body)[0], 403)
            reveal.assert_not_called()
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=body)[0], 204)
            reveal.assert_called_once_with(str(self.target))
            reveal.reset_mock()
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=b'{}')[0], 400)
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=b'x' * 8193)[0], 413)
            reveal.assert_not_called()
        gone = json.dumps({'path': str(self.target.with_name('gone.step'))}).encode()
        self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=gone)[0], 404)
        relative = json.dumps({'path': self.target.name}).encode()
        self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=relative)[0], 400)
