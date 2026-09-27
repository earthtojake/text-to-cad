"""Snapshot clipboard endpoint: explicit POST, bounded PNG data, native delivery."""
import unittest
from unittest import mock
from cadgen.viewer.clipboard import copy_png, MAX_PNG_BYTES
from .test_http_layer import ServerFixture

PNG = b"\x89PNG\r\n\x1a\n" + b"fixture"

class ClipboardTests(unittest.TestCase):
    def test_rejects_invalid_or_oversized_images_before_native_write(self):
        with mock.patch('cadgen.viewer.clipboard.subprocess.run') as run:
            for value in (b'not png', PNG + b'0' * MAX_PNG_BYTES):
                with self.assertRaises(ValueError):
                    copy_png(value)
            run.assert_not_called()

    def test_mac_uses_static_script_and_a_temporary_png(self):
        with mock.patch('cadgen.viewer.clipboard.sys.platform', 'darwin'), mock.patch('cadgen.viewer.clipboard.subprocess.run') as run:
            copy_png(PNG)
            args = run.call_args.args[0]
            self.assertEqual(args[0], '/usr/bin/osascript')
            self.assertIn('item 1 of argv', args[2])
            self.assertTrue(args[3].endswith('/snapshot.png'))

    def test_route_requires_browser_guard_and_delivers_png(self):
        server = ServerFixture()
        self.addCleanup(server.close)
        with mock.patch('cadgen.viewer.clipboard.copy_png') as copy:
            self.assertEqual(server.request('POST', '/__cad/clipboard', body=PNG)[0], 403)
            copy.assert_not_called()
            self.assertEqual(server.request('POST', '/__cad/clipboard', headers={'x-cadgen-viewer':'1','Content-Type':'image/png'}, body=PNG)[0], 204)
            copy.assert_called_once_with(PNG)
