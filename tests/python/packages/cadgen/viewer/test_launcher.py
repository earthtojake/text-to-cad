"""The viewer is a short-lived launcher; one engine owns its one page, which addresses documents by
path (``/<id>``); the most recent launch's folder is the one its relative files are read from."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from cadgen.viewer.engine_app import LINK_EXPIRED_PAGE, TOKEN_NEEDED_PAGE, sign
from tests.python.support import engine_daemon


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        (self.dist / 'index.html').write_text('<html>viewer</html>', encoding='utf-8')
        (self.dist / 'assets').mkdir()
        (self.dist / 'assets' / 'app.js').write_text('export {}', encoding='utf-8')
        self.env = engine_daemon.watched({**os.environ, 'CADGEN_ENGINE_DIR': str(self.root / 'engine'),
                   'CADGEN_STATE_DIR': str(self.root / 'state'), 'CADGEN_ENGINE_MESH': 'inline'}, self.addCleanup)
        self.addCleanup(self.stop_engine)

    def stop_engine(self):
        pid = engine_daemon.engine_pid(self.env)
        done = subprocess.run([sys.executable, '-m', 'cadgen.engine', 'stop'],
                              env=self.env, capture_output=True, text=True, timeout=90)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(engine_daemon.await_exit(pid), "the stopped engine leaves the test's folder")


    def launch(self, *args, cwd=None, ok=True):
        done = subprocess.run([sys.executable, '-m', 'cadgen.viewer', '--json', '--dist', str(self.dist), *args],
                              env=self.env, cwd=cwd or self.root, capture_output=True, text=True, timeout=60)
        if not ok:
            self.assertNotEqual(done.returncode, 0)
            return done.stderr
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def get(self, launched, route, *, token=True, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', launched['port'], timeout=20)
        try:
            conn.request('GET', route, headers={**({'Authorization': 'Bearer '+launched['token']} if token else {}),
                                               **(headers or {})})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def master(self):
        """The user's token, as its file holds it: never in a printed URL."""
        return (self.root / 'state' / 'engines' / 'token').read_text(encoding='utf-8').strip()

    def session(self, headers):
        """The ``Cookie`` header that sends back the session a response set."""
        self.assertRegex(headers['set-cookie'], r'^cadgen-[\w-]{12}=\d+\.[\w-]{43}; Path=/; Max-Age=2592000; '
                                                r'HttpOnly; SameSite=Strict$')
        return {'Cookie': headers['set-cookie'].split(';')[0]}

    def test_launches_reuse_one_engine_which_keeps_the_latest_launch_s_folder(self):
        b, c = self.root / 'b', self.root / 'c'
        b.mkdir()
        c.mkdir()
        first = self.launch(cwd=b)
        again = self.launch(cwd=b)
        latest = self.launch(cwd=c)
        self.assertEqual({r['pid'] for r in (first, again, latest)}, {first['pid']})
        self.assertEqual({r['port'] for r in (first, again, latest)}, {first['port']})
        self.assertEqual([urlsplit(r['url']).path for r in (first, latest)], ['/', '/'])
        # One page: the most recent launch's folder, c, replacing b, which its relative files are read from.
        status, _, data = self.get(first, '/__cad/server')
        self.assertEqual(status, 200)
        self.assertEqual(os.path.realpath(json.loads(data)['start']), os.path.realpath(c))
        self.assertEqual(json.loads(data)['pid'], first['pid'])
        # Quick Edit's phrases are the most recent launch's too: given, kept trimmed; not given, none.
        self.assertEqual(json.loads(data)['phrases'], [])
        self.launch('--phrase', 'Repair', '--phrase', ' This is a feature ', '--phrase', ' ', cwd=c)
        self.assertEqual(json.loads(self.get(first, '/__cad/server')[2])['phrases'], ['Repair', 'This is a feature'])
        self.launch(cwd=c)
        self.assertEqual(json.loads(self.get(first, '/__cad/server')[2])['phrases'], [])
        # Both launchers have exited; the shared server still serves the page.
        self.assertEqual(self.get(first, '/')[0], 200)
        self.assertIn('already serves', self.launch('--port', str(first['port']+1), ok=False))

    def test_a_file_launched_lands_on_its_id_and_old_links_land_home(self):
        from cadgen.engine.ids import file_id

        part = self.root / 'part.stl'
        part.write_text('solid x\nendsolid x\n', encoding='utf-8')
        link = self.root / 'link.stl'
        link.symlink_to(part)
        launched = self.launch('part.stl')
        ident = file_id(part)
        self.assertEqual(urlsplit(launched['url']).path, f'/{ident}')
        self.assertEqual([row['id'] for row in launched['documents']], [ident])
        # A symlink to it is the same document: one id, one catalog row.
        self.assertEqual(urlsplit(self.launch('link.stl')['url']).path, f'/{ident}')
        self.assertEqual(self.get(launched, f'/{ident}')[0], 200)
        status, _, data = self.get(launched, f'/__cad/catalog?id={ident}')
        self.assertEqual(status, 200)
        self.assertEqual([(row['id'], os.path.realpath(row['file'])) for row in json.loads(data)['entries']],
                         [(ident, os.path.realpath(part))])
        status, _, data = self.get(launched, '/__cad/catalog?file=' + str(link))
        self.assertEqual([row['id'] for row in json.loads(data)['entries']], [ident])
        # An id nothing holds is missing, and says so; a script is no CAD file to open.
        status, _, data = self.get(launched, '/__cad/catalog?id=6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab')
        self.assertEqual((status, json.loads(data)['entries']), (200, []))
        self.assertIn('is held', json.loads(data)['missing'])
        (self.root / 'model.py').write_text('print(1)\n', encoding='utf-8')
        self.assertIn('no CAD file', self.launch('model.py', ok=False))

    def test_every_route_requires_token_and_keeps_host_and_post_gates(self):
        launch = self.launch()
        for route in ('/', '/assets/app.js', '/__cad/server', '/api/docs', '/__cad/api/docs', '/mcp'):
            self.assertEqual(self.get(launch, route, token=False)[0], 403, route)
            self.assertEqual(self.get(launch, route, headers={'Host': 'evil.example'})[0], 403, route)
        # A page load without a credential is refused with a static page (no script, no asset), never
        # the raw JSON: it needs a link. A link or a cookie the user's token never signed is none.
        status, headers, body = self.get(launch, '/', token=False, headers={'Sec-Fetch-Dest': 'document'})
        self.assertEqual((status, headers['content-type'], body), (403, 'text/html; charset=utf-8', TOKEN_NEEDED_PAGE))
        page = urlsplit(launch['url']).path
        master, link = self.master(), launch['token']
        self.assertNotIn(master, json.dumps(launch), 'a printed launch carries a link, never the token')
        self.assertEqual(launch['url'], f"{launch['apiUrl']}/?token={link}")
        # The link (or the token itself) is exchanged for a session cookie, which is neither.
        status, headers, _ = self.get(launch, f'{page}?token={link}', token=False)
        self.assertEqual((status, headers['location']), (302, page))
        cookie = self.session(headers)
        status, headers, _ = self.get(launch, f'{page}?token={master}', token=False)
        self.assertEqual(status, 302)
        for value in (master, link):
            self.assertNotIn(value, headers['set-cookie'] + cookie['Cookie'])
        name = cookie['Cookie'].split('=')[0]
        for stale in ({'Cookie': f'{name}=gone'}, {'Cookie': f'{name}={sign("x" * 43, "session", 60)}'}):
            status, _, body = self.get(launch, '/', token=False, headers={**stale, 'Sec-Fetch-Dest': 'document'})
            self.assertEqual((status, body), (403, TOKEN_NEEDED_PAGE), stale)
            # ... and never outranks the link of the URL a launch just printed.
            self.assertEqual(self.get(launch, f'{page}?token={link}', token=False, headers=stale)[0], 302)
        self.assertEqual(self.get(launch, '/?token=gone', token=False, headers={'Sec-Fetch-Dest': 'document'})[2],
                         TOKEN_NEEDED_PAGE)
        # Arrived from another origin (the browser opened on the launcher's redirect file): the
        # cookie, and a page of this origin that navigates on, so the browser sends the cookie.
        status, headers, body = self.get(launch, f'{page}?token={link}', token=False, headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 200)
        self.session(headers)
        self.assertIn(b'http-equiv="refresh" content="0;url=/"', body)
        self.assertNotIn(link.encode(), body)
        # A link past its day says so, alone; with a session it is just dropped from the address, and
        # one followed from another site is asked again from this origin, where the session is sent.
        expired = sign(master, 'link', -60)
        navigation = {'Sec-Fetch-Dest': 'document'}
        self.assertEqual(self.get(launch, f'/?token={expired}', token=False, headers=navigation)[::2],
                         (403, LINK_EXPIRED_PAGE))
        status, headers, _ = self.get(launch, f'/?token={expired}', token=False, headers={**cookie, **navigation})
        self.assertEqual((status, headers['location']), (302, '/'))
        for sent, site in ((sent, site) for sent in ({}, cookie) for site in ('cross-site', 'same-site')):
            status, headers, body = self.get(launch, f'/?token={expired}', token=False,
                                             headers={**sent, **navigation, 'Sec-Fetch-Site': site})
            self.assertEqual((status, 'set-cookie' in headers), (200, False), (sent, site))
            self.assertIn(f'url=/?token={expired}'.encode(), body)
        for body in (TOKEN_NEEDED_PAGE, LINK_EXPIRED_PAGE):
            self.assertNotIn(b'<script', body)
            self.assertNotIn(b'?token=', body)
        # Each page load the session admits renews it, 30 days from then; a read only once it is a day old.
        status, headers, _ = self.get(launch, '/', token=False, headers={**cookie, **navigation})
        self.assertEqual(status, 200)
        self.session(headers)
        self.assertNotIn('set-cookie', self.get(launch, '/__cad/server', token=False, headers=cookie)[1])
        old = {'Cookie': f'{name}={sign(master, "session", 30 * 86400, now=time.time() - 2 * 86400)}'}
        self.session(self.get(launch, '/__cad/server', token=False, headers=old)[1])
        # A sibling cookie that another page on this host set (cookies are host-scoped, not
        # port-scoped), even one a strict parser rejects, must not drop the engine's own cookie.
        for header in (f"x=y z; {cookie['Cookie']}", f"{cookie['Cookie']}; a[b]=1"):
            status, _, _ = self.get(launch, '/__cad/server', token=False, headers={'Cookie': header})
            self.assertEqual(status, 200, header)
        self.assertEqual(self.get(launch, '/__cad/server?token=%C3%A9', token=False)[0], 403)
        # The cookie reaches every port of this host, so it admits only what the browser says came
        # from this origin or from the person (or from a client that is not a browser); a token or a
        # link in the header or the URL is admitted from anywhere, and another origin with neither not.
        for site, expected in (('same-origin', 200), ('none', 200), ('same-site', 403), ('cross-site', 403)):
            status, _, body = self.get(launch, '/__cad/server', token=False,
                                       headers={**cookie, 'Sec-Fetch-Site': site})
            self.assertEqual(status, expected, site)
            self.assertEqual(self.get(launch, '/__cad/server', headers={'Sec-Fetch-Site': site})[0], 200, site)
            self.assertEqual(self.get(launch, '/__cad/server', token=False, headers={'Sec-Fetch-Site': site})[0], 403)
        self.assertIn(b'cross-origin request refused', self.get(
            launch, '/', token=False, headers={**cookie, 'Sec-Fetch-Site': 'same-site'})[2])
        # Every page may be framed by its own origin alone: the client's, and the link-gone page.
        for route in ('/', urlsplit(launch['url']).path):
            self.assertEqual(self.get(launch, route)[1].get('content-security-policy'), "frame-ancestors 'self'")
        self.assertIn("frame-ancestors 'self'", self.get(launch, '/', token=False,
                      headers={'Sec-Fetch-Dest': 'document'})[1]['content-security-policy'])
        conn = http.client.HTTPConnection('127.0.0.1', launch['port'], timeout=10)
        try:
            conn.request('POST', '/__cad/recents', body=b'{}', headers={'Authorization': 'Bearer '+launch['token']})
            reply = conn.getresponse()
            self.assertEqual(reply.status, 403)
            reply.read()
        finally:
            conn.close()

    def test_api_only_needs_no_built_client(self):
        done = subprocess.run([sys.executable, '-m', 'cadgen.viewer', '--api-only', '--json'],
                              env=self.env, cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        launch = json.loads(done.stdout)
        self.assertEqual(self.get(launch, '/__cad/server')[0], 200)


if __name__ == '__main__':
    unittest.main()


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)
