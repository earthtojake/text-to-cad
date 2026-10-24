"""A viewer page opens in the browser through an owner-only redirect file in the engine's folder:
the opener (and so any command line) is given the file, never the tokened URL, and the file is
gone soon after."""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit

from cadgen.viewer import browser_open, main as viewer_main

URL = 'http://127.0.0.1:4321/abc?token=secret-token'
DISPLAY_REFUSAL = browser_open.display_refusal  # the module's own, which the tests below patch out


class BrowserOpenTest(unittest.TestCase):
    def setUp(self):
        self.engine = Path(tempfile.mkdtemp(prefix='eng-')).resolve()
        os.chmod(self.engine, 0o700)
        self.addCleanup(shutil.rmtree, self.engine, True)
        for patch in (mock.patch.dict(os.environ, {'CADGEN_ENGINE_DIR': str(self.engine)}),
                      mock.patch.object(browser_open, 'display_refusal', return_value=None)):  # CI has no display
            patch.start()
            self.addCleanup(patch.stop)

    def await_gone(self, path, within=5.0):
        deadline = time.monotonic() + within
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        return not path.exists()

    def test_the_opener_gets_an_owner_only_file_that_holds_the_url_and_is_removed_after(self):
        given = []
        with mock.patch.object(browser_open, 'KEEP_SECONDS', 0.2):
            path = browser_open.open_page(URL, opener=lambda target: given.append(target) or True)
            self.assertEqual(len(given), 1)
            self.assertNotIn('secret-token', given[0])
            self.assertEqual(Path(unquote(urlsplit(given[0]).path)), path)
            self.assertEqual(path.parent, self.engine)
            if os.name != 'nt':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            page = path.read_text(encoding='utf-8')
            self.assertIn('url=http://127.0.0.1:4321/abc?token=secret-token', page)
            self.assertIn('location.replace("http://127.0.0.1:4321/abc?token=secret-token")', page)
            self.assertTrue(self.await_gone(path), 'the redirect file was removed')

    def test_a_file_an_exited_process_left_is_removed_by_the_next_open(self):
        left = self.engine / 'open-0000000000000000.html'
        left.write_text('old', encoding='utf-8')
        os.utime(left, (time.time() - 60, time.time() - 60))
        browser_open.open_page(URL, opener=lambda _target: True)
        self.assertFalse(left.exists())

    def test_no_browser_is_said_in_words_and_leaves_no_file(self):
        with self.assertRaisesRegex(browser_open.CannotOpen, 'no browser'):
            browser_open.open_page(URL, opener=lambda _target: False)
        self.assertEqual(list(self.engine.glob('open-*.html')), [])

    @unittest.skipIf(os.name == 'nt', "a folder's mode is POSIX's")
    def test_a_folder_others_can_write_is_refused(self):
        os.chmod(self.engine, 0o777)
        with self.assertRaisesRegex(browser_open.CannotOpen, 'can be written by others'):
            browser_open.open_page(URL, opener=lambda _target: self.fail('opened'))

    def test_no_display_is_said_before_anything_is_written(self):
        refusal = mock.patch.object(browser_open, 'display_refusal', return_value='there is no display to open a browser on')
        with refusal, self.assertRaisesRegex(browser_open.CannotOpen, 'no display'):
            browser_open.open_page(URL, opener=lambda _target: self.fail('opened'))
        self.assertEqual(list(self.engine.iterdir()), [])

    @unittest.skipIf(os.name == 'nt', 'Windows always has its desktop')
    def test_a_remote_shell_or_a_session_with_no_display_has_no_browser(self):
        real = DISPLAY_REFUSAL
        self.assertIn('remote session', real({'SSH_CONNECTION': '10.0.0.1 1 10.0.0.2 22'}))
        self.assertIsNone(real({'SSH_CONNECTION': '10.0.0.1 1 10.0.0.2 22', 'DISPLAY': 'localhost:10.0'}))
        self.assertIsNone(real({'WAYLAND_DISPLAY': 'wayland-0'}))
        with mock.patch.object(browser_open.sys, 'platform', 'linux'):
            self.assertIn('no display', real({}))
        with mock.patch.object(browser_open.sys, 'platform', 'darwin'):
            self.assertIsNone(real({}))

    def test_the_launcher_opens_the_file_not_the_url(self):
        given = []
        answer = {'url': URL, 'documents': []}
        with mock.patch('cadgen.engine.client.request', return_value=answer), \
                mock.patch.object(viewer_main, 'resolve_dist_dir', return_value='/dist'), \
                mock.patch.object(viewer_main.webbrowser, 'open', side_effect=lambda target: given.append(target) or True), \
                mock.patch('builtins.print'):
            self.assertEqual(viewer_main.main([]), 0)
        self.assertEqual(len(given), 1)
        self.assertTrue(given[0].startswith('file:'), given[0])
        self.assertNotIn('secret-token', given[0])


if __name__ == '__main__':
    unittest.main()
