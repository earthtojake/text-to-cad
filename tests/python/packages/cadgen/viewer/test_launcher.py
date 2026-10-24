"""The viewer is a short-lived launcher; one engine owns its one page, which addresses documents by
path (``/<id>``) and whose home shows the folder of the most recent launch."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from cadgen.viewer.engine_app import LINK_GONE_PAGE
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
        done = subprocess.run([sys.executable, '-m', 'cadgen.engine', 'stop'],
                              env=self.env, capture_output=True, text=True, timeout=90)
        self.assertEqual(done.returncode, 0, done.stderr)


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

    def test_launches_reuse_one_engine_and_the_home_shows_the_latest_folder(self):
        b, c = self.root / 'b', self.root / 'c'
        b.mkdir()
        c.mkdir()
        first = self.launch(cwd=b)
        again = self.launch(cwd=b)
        latest = self.launch(cwd=c)
        self.assertEqual({r['pid'] for r in (first, again, latest)}, {first['pid']})
        self.assertEqual({r['port'] for r in (first, again, latest)}, {first['port']})
        self.assertEqual([urlsplit(r['url']).path for r in (first, latest)], ['/', '/'])
        # One page: the home shows the folder of the most recent launch, c, replacing b.
        status, _, data = self.get(first, '/__cad/server')
        self.assertEqual(status, 200)
        self.assertEqual(os.path.realpath(json.loads(data)['start']), os.path.realpath(c))
        self.assertEqual(json.loads(data)['pid'], first['pid'])
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
        # A page session's link and a document named by query are forms that are gone: the home.
        for route in ('/s/abc/', '/s/abc/?file=/m/a.step', '/?doc=' + ident, '/?file=' + str(part)):
            status, headers, _ = self.get(launched, route)
            self.assertEqual((status, headers.get('location')), (302, '/'), route)

    def test_every_route_requires_token_and_keeps_host_and_post_gates(self):
        launch = self.launch()
        for route in ('/', '/assets/app.js', '/__cad/server', '/api/docs', '/__cad/api/docs', '/mcp'):
            self.assertEqual(self.get(launch, route, token=False)[0], 403, route)
            self.assertEqual(self.get(launch, route, headers={'Host': 'evil.example'})[0], 403, route)
        # A navigation without the token is refused too, with a static page saying the link is gone
        # (no script, no asset), never the raw JSON.
        status, headers, body = self.get(launch, '/', token=False, headers={'Sec-Fetch-Dest': 'document'})
        self.assertEqual((status, headers['content-type'], body), (403, 'text/html; charset=utf-8', LINK_GONE_PAGE))
        self.assertNotIn(b'<script', body)
        status, headers, _ = self.get(launch, urlsplit(launch['url']).path+'?token='+launch['token'], token=False)
        self.assertEqual(status, 302)
        self.assertIn('HttpOnly', headers['set-cookie'])
        self.assertNotIn(launch['token'], headers['location'])
        # Arrived from another origin (the browser opened on the launcher's redirect file): the
        # cookie, and a page of this origin that navigates on, so the browser sends the cookie.
        status, headers, body = self.get(launch, urlsplit(launch['url']).path+'?token='+launch['token'],
                                         token=False, headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 200)
        self.assertIn(launch['token'], headers['set-cookie'])
        self.assertIn(b'http-equiv="refresh" content="0;url=/"', body)
        self.assertNotIn(launch['token'].encode(), body)
        # A cookie from an engine that held this port before (restarted with --port) never
        # outranks the launch URL's token, and a token that is not ASCII is refused, not a crash.
        stale = {'Cookie': f"cadgen-engine-{launch['port']}=stale"}
        status, headers, _ = self.get(launch, urlsplit(launch['url']).path+'?token='+launch['token'],
                                      token=False, headers=stale)
        self.assertEqual(status, 302)
        self.assertIn(launch['token'], headers['set-cookie'])
        # A sibling cookie that another page on this host set (cookies are host-scoped, not
        # port-scoped), even one a strict parser rejects, must not drop the engine's own cookie.
        for header in (f"x=y z; cadgen-engine-{launch['port']}={launch['token']}",
                       f"cadgen-engine-{launch['port']}={launch['token']}; a[b]=1"):
            status, _, _ = self.get(launch, '/__cad/server', token=False, headers={'Cookie': header})
            self.assertEqual(status, 200, header)
        self.assertEqual(self.get(launch, '/__cad/server?token=%C3%A9', token=False)[0], 403)
        # The cookie reaches every port of this host, so it admits only what the browser says came
        # from this origin or from the person (or from a client that is not a browser); a token in
        # the header or the URL is admitted from anywhere.
        cookie = {'Cookie': f"cadgen-engine-{launch['port']}={launch['token']}"}
        for site, expected in (('same-origin', 200), ('none', 200), ('same-site', 403), ('cross-site', 403)):
            status, _, body = self.get(launch, '/__cad/server', token=False,
                                       headers={**cookie, 'Sec-Fetch-Site': site})
            self.assertEqual(status, expected, site)
            self.assertEqual(self.get(launch, '/__cad/server', headers={'Sec-Fetch-Site': site})[0], 200, site)
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
