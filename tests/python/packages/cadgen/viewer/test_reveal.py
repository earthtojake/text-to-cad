"""Native file reveal is explicit, root-scoped, and uses platform argument arrays."""
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock
from cadgen.viewer.backend import ForbiddenAssetError
from cadgen.viewer.reveal import reveal_path
from .test_http_layer import ServerFixture

class RevealTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerFixture()
        self.addCleanup(self.server.close)
        self.target = Path(self.server.root, 'part with spaces.step')
        self.target.write_text('fixture')

    def test_native_commands(self):
        with mock.patch('cadgen.viewer.reveal.subprocess.run') as run:
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'darwin'):
                reveal_path(self.server.root, self.target.name)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-R', str(self.target.resolve())])
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'linux'), mock.patch('cadgen.viewer.reveal.shutil.which', return_value=None):
                reveal_path(self.server.root, self.target.name)
                self.assertEqual(run.call_args.args[0], ['xdg-open', str(self.target.parent.resolve())])
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'linux'), mock.patch('cadgen.viewer.reveal.shutil.which', return_value='/usr/bin/dbus-send'):
                reveal_path(self.server.root, self.target.name)
                self.assertIn('array:string:' + self.target.resolve().as_uri(), run.call_args.args[0])
                run.side_effect = [subprocess.CalledProcessError(1, 'dbus-send'), None]
                reveal_path(self.server.root, self.target.name)
                self.assertEqual(run.call_args.args[0][0], 'xdg-open')
        with mock.patch('cadgen.viewer.reveal.sys.platform', 'win32'), mock.patch('cadgen.viewer.reveal.subprocess.Popen') as spawn:
            reveal_path(self.server.root, self.target.name)
            self.assertEqual(spawn.call_args.args[0], ['explorer.exe', '/select,' + str(self.target.resolve())])

    def test_rejects_escape_missing_and_invalid_paths(self):
        outside = Path(self.server.root).parent / 'outside.txt'
        outside.write_text('outside')
        Path(self.server.root, 'escape').symlink_to(outside)
        with mock.patch('cadgen.viewer.reveal.subprocess.run') as run:
            for path in ('../outside.txt', 'escape'):
                with self.assertRaises(ForbiddenAssetError):
                    reveal_path(self.server.root, path)
            for path in (str(outside.resolve()), None, 1):
                with self.assertRaises(ValueError):
                    reveal_path(self.server.root, path)
            with self.assertRaises(FileNotFoundError):
                reveal_path(self.server.root, 'missing.step')
            run.assert_not_called()

    def test_route_requires_browser_guard_and_valid_payload(self):
        headers = {'x-cadgen-viewer': '1', 'Content-Type': 'application/json'}
        body = json.dumps({'path': self.target.name}).encode()
        with mock.patch('cadgen.viewer.reveal.reveal_path') as reveal:
            self.assertEqual(self.server.request('POST', '/__cad/reveal', body=body)[0], 403)
            reveal.assert_not_called()
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=body)[0], 204)
            reveal.assert_called_once_with(self.server.root, self.target.name)
            reveal.reset_mock()
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=b'{}')[0], 400)
            self.assertEqual(self.server.request('POST', '/__cad/reveal', headers=headers, body=b'x' * 8193)[0], 413)
            reveal.assert_not_called()
