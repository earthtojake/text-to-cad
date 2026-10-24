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
        found = {'dbus-send': None, 'xdg-open': '/usr/bin/xdg-open'}
        with mock.patch('cadgen.viewer.reveal.subprocess.run') as run, \
                mock.patch('cadgen.viewer.reveal.executables.find', side_effect=lambda name: found[name]):
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'darwin'):
                reveal_path(target)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-R', str(self.target.resolve())])
            with mock.patch('cadgen.viewer.reveal.sys.platform', 'linux'):
                reveal_path(target)
                self.assertEqual(run.call_args.args[0], ['/usr/bin/xdg-open', str(self.target.parent.resolve())])
                found['dbus-send'] = '/usr/bin/dbus-send'
                reveal_path(target)
                self.assertEqual(run.call_args.args[0][0], '/usr/bin/dbus-send')
                self.assertIn('array:string:' + self.target.resolve().as_uri(), run.call_args.args[0])
                run.side_effect = [subprocess.CalledProcessError(1, 'dbus-send'), None]
                reveal_path(target)
                self.assertEqual(run.call_args.args[0][0], '/usr/bin/xdg-open')
                # A helper is run by the absolute path PATH's absolute folders give it, or not at all.
                run.side_effect, found['dbus-send'], found['xdg-open'] = None, None, None
                with self.assertRaisesRegex(FileNotFoundError, 'xdg-open'):
                    reveal_path(target)
        with mock.patch('cadgen.viewer.reveal.sys.platform', 'win32'), mock.patch('cadgen.viewer.reveal.subprocess.Popen') as spawn, \
                mock.patch.dict('os.environ', {'SystemRoot': 'C:\\Windows'}):
            reveal_path(target)
            self.assertEqual(spawn.call_args.args[0], [str(Path('C:\\Windows') / 'explorer.exe'), '/select,' + str(self.target.resolve())])

    def test_a_name_explorer_would_split_at_its_comma_opens_its_folder_through_the_shell(self):
        named = Path(self.server.root, 'part.step,other.step')
        named.write_text('fixture', encoding='utf-8')
        with mock.patch('cadgen.viewer.reveal.sys.platform', 'win32'), mock.patch('cadgen.viewer.reveal.subprocess.Popen') as spawn, \
                mock.patch('cadgen.viewer.reveal.os.startfile', create=True) as shell:
            reveal_path(str(named))
        spawn.assert_not_called()
        shell.assert_called_once_with(str(named.resolve().parent))

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
