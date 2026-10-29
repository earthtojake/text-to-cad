"""Real stdio and HTTP peers share an engine, with isolated MCP view state."""
from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.engine.client import request
from cadgen.mcp.browser import OPENED
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.mcp.shim import Proxy
from cadgen.viewer.engine_client import EngineClient
from tests.python.support import engine_daemon

INIT = {'protocolVersion': '2025-11-25', 'clientInfo': {'name': 'codex-mcp-client'}, 'capabilities': {}}
TEXT = {'protocolVersion': '2025-11-25', 'clientInfo': {'name': 'some-cli'}, 'capabilities': {}}
# A ``BROWSER`` that records each page it is given, and who gave it (its parent's pid), and opens nothing.
RECORDER = """import json, os, sys
from urllib.parse import unquote, urlsplit
page = open(unquote(urlsplit(sys.argv[1]).path), encoding='utf-8').read()
with open({record!r}, 'a', encoding='utf-8') as out:
    out.write(json.dumps({{'who': {who!r}, 'pid': os.getppid(), 'page': page}}) + '\\n')
sys.exit({code})
"""


class HttpSessionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='mcp-http-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.page = cls.root / 'page'
        cls.page.mkdir()
        (cls.page / 'index.html').write_text('<!doctype html><title>test app</title>', encoding='utf-8')
        # The engine's browser records any page it is given, and opens nothing: it should be given
        # none. It exits 0, as a BROWSER that refused would have webbrowser go on to the platform's
        # own browser (macOS's osascript), which no test may reach.
        cls.opened = cls.root / 'opened.jsonl'
        cls.engine_browser = cls.browser('engine', 0)
        cls.env = engine_daemon.watched({**os.environ, 'CADGEN_ENGINE_DIR': str(cls.root / 'engine'),
                   'CADGEN_STATE_DIR': str(cls.root / 'state'), 'CADGEN_ENGINE_MESH': 'inline',
                   'CADGEN_PORT': str(engine_daemon.free_port()),
                   'CADGEN_VIEWER_DIST': str(cls.page), 'BROWSER': cls.engine_browser}, cls.addClassCleanup)
        changed = patch.dict(os.environ, cls.env)
        changed.start()
        cls.addClassCleanup(changed.stop)
        from cadgen.engine.api import stop
        cls.addClassCleanup(stop)
        engine_daemon.bootstrap(cls.env)
        cls.endpoint = EngineClient().connect()
        cls.model = cls.root / 'part.stl'
        cls.model.write_bytes(b'solid part\nendsolid part\n')

    @classmethod
    def browser(cls, who, code):
        """A ``BROWSER`` command that records each page it is given (``RECORDER``) and exits ``code``."""
        script = cls.root / f'{who}-browser'
        script.write_text(f'#!{sys.executable}\n' + RECORDER.format(record=str(cls.opened), who=who, code=code), encoding='utf-8')
        script.chmod(0o755)
        return str(script)

    def proxy(self, init=INIT, **kwargs):
        proxy = Proxy(**kwargs)
        self.addCleanup(proxy.close)
        self.call(proxy, 'initialize', init)
        return proxy

    def recorded(self):
        return [json.loads(line) for line in self.opened.read_text(encoding='utf-8').splitlines()] if self.opened.exists() else []

    @contextlib.contextmanager
    def peer_environment(self, **more):
        """The environment of a stdio peer made in this process: a display, where one is asked for, no
        remote shell, and ``more`` (its BROWSER); its ``webbrowser`` reads them afresh."""
        import webbrowser

        with patch.dict(os.environ, {'DISPLAY': ':0', **more}), patch.object(webbrowser, '_tryorder', None), \
                patch.object(webbrowser, '_browsers', {}):
            for name in ('SSH_CONNECTION', 'SSH_TTY'):
                os.environ.pop(name, None)
            yield

    @unittest.skipIf(os.name == 'nt', 'a BROWSER command here is a script run by its #! line')
    def test_a_text_hosts_cad_show_opens_the_browser_from_the_stdio_peer_never_the_engine(self):
        # The engine runs in the environment of whatever started it -- here a BROWSER that records --
        # and the stdio peer in its host's: only the peer's BROWSER is given the page.
        engine = request({'op': 'status'})['pid']  # running, started with the engine's environment
        before = len(self.recorded())
        with self.peer_environment(BROWSER=self.browser('shim', 0)):
            proxy = self.proxy(TEXT)
            model = str(self.model.resolve())
            shown = self.tool(proxy, 'cad_show', {'source': model})
            self.assertNotIn('_meta', shown)
            text = shown['content'][0]['text']
            self.assertRegex(text, r'^part\.stl opened in your browser at http://127\.0\.0\.1:\d+/[0-9a-f-]{36}\?token=')
            # Opened once: the peer told the engine it opened the page, and a second show opens nothing.
            again = self.tool(proxy, 'cad_show', {'source': model})['content'][0]['text']
            self.assertTrue(again.startswith('part.stl is already open in your browser at '), again)
        opened = self.recorded()[before:]
        self.assertEqual([(row['who'], row['pid']) for row in opened], [('shim', os.getpid())])
        self.assertNotEqual(opened[0]['pid'], engine)
        link = text.split(' at ', 1)[1].split('.\n', 1)[0]
        self.assertIn(f'url={link}'.replace('&', '&amp;'), opened[0]['page'])

    @unittest.skipIf(os.name == 'nt', 'a BROWSER command here is a script run by its #! line')
    def test_a_page_the_stdio_peer_could_not_open_is_opened_again_by_the_next_show(self):
        # The peer's BROWSER exits non-zero: the answer says no browser opened, the engine counts no
        # page as open, and the next show asks the peer again. The peer's opener is that BROWSER
        # command alone: ``webbrowser.open`` would go on to the platform's own browser after it
        # (macOS's osascript), which no test may reach.
        import webbrowser

        model = self.root / 'failing.stl'
        model.write_bytes(b'solid part\nendsolid part\n')
        before = len(self.recorded())
        with self.peer_environment():
            proxy = self.proxy(TEXT, opener=webbrowser.GenericBrowser(self.browser('failing', 1)).open)
            for attempt in (1, 2):
                text = self.tool(proxy, 'cad_show', {'source': str(model.resolve())})['content'][0]['text']
                self.assertTrue(text.startswith('No browser can be opened from here (no browser could be started here'), (attempt, text))
                self.assertIn("; failing.stl's page is http://127.0.0.1:", text)
        self.assertEqual([row['who'] for row in self.recorded()[before:]], ['failing', 'failing'])

    def test_a_client_with_no_stdio_peer_is_given_the_url_and_nothing_opens(self):
        client = EngineClient()
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}

        def post(message, **more):
            status, replied, body = client.call('POST', '/mcp', json.dumps(message).encode('utf-8'), {**headers, **more})
            self.assertEqual(status, 200, body)
            return {name.lower(): value for name, value in replied.items()}, json.loads(body)['result']

        replied, _ = post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': TEXT})
        session = {'Mcp-Session-Id': replied['mcp-session-id'], 'MCP-Protocol-Version': '2025-11-25'}
        self.addCleanup(client.call, 'DELETE', '/mcp', headers=session)
        model = self.root / 'unopened.stl'
        model.write_bytes(b'solid part\nendsolid part\n')
        before = len(self.recorded())
        _, shown = post({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                         'params': {'name': 'cad_show', 'arguments': {'source': str(model.resolve())}}}, **session)
        self.assertNotIn('_meta', shown)
        self.assertRegex(shown['content'][0]['text'], r'^unopened\.stl\'s page is http://127\.0\.0\.1:\d+/\S+; nothing was '
                                                      r'opened, as this client opens no browser\.\n')
        self.assertEqual(self.recorded()[before:], [])
        # Its word that the page opened is no open the engine asked a peer for: nothing counts the page
        # as open, so a stdio peer's show of the model opens it.
        link = shown['content'][0]['text'].split(' is ', 1)[1].split('; ', 1)[0]
        status, _, _ = client.call('POST', '/mcp', json.dumps({'jsonrpc': '2.0', 'method': OPENED, 'params': {
            'url': link, 'opened': True}}).encode('utf-8'), {**headers, **session})
        self.assertEqual(status, 202)
        opened = []
        with self.peer_environment():
            proxy = self.proxy(TEXT, opener=lambda target: opened.append(target) or True)
            text = self.tool(proxy, 'cad_show', {'source': str(model.resolve())})['content'][0]['text']
        self.assertTrue(text.startswith('unopened.stl opened in your browser at '), text)
        self.assertEqual((len(opened), self.recorded()[before:]), (1, []))

    @staticmethod
    def call(proxy, method, params=None):
        return proxy.handle(method, params or {}, RequestContext(1, {}))

    def tool(self, proxy, name, arguments=None):
        return self.call(proxy, 'tools/call', {'name': name, 'arguments': arguments or {}})

    def test_two_sessions_share_engine_and_router_but_not_conversation_views(self):
        first, second = self.proxy(), self.proxy()
        self.assertNotEqual(first.session, second.session)
        # Over the real transport, a request without the page's capability is refused, never routed.
        refused = self.tool(first, 'cad_http', {'method': 'GET', 'url': '/__cad/analytics'})
        self.assertTrue(refused['isError'])
        self.assertNotIn('structuredContent', refused)
        info = request({'op': 'status'})
        sessions = {item['id'] for item in info['sessions'] if item['kind'] == 'mcp'}
        self.assertTrue({first.session, second.session} <= sessions)
        token = self.tool(first, 'cad_tab')['_meta']['dev.texttocad/httpToken']
        self.tool(first, 'cad_sync', {'view': 'one', 'surface': 'agent', 'model': str(self.model),
                  'state': {'selection': ['part#f1']}, 'focused': True, 'app': token})
        self.assertEqual(self.tool(first, 'cad_view')['structuredContent']['views'][0]['selection'], ['part#f1'])
        self.assertEqual(self.tool(second, 'cad_view')['structuredContent']['views'], [])
        reply = self.tool(first, 'cad_http', {'method': 'GET', 'url': '/__cad/server', 'headers': {'x-cadgen-app': token}})['structuredContent']
        self.assertEqual(reply['status'], 200)
        self.assertEqual(json.loads(base64.b64decode(reply['body']))['pid'], info['pid'])
        first.close()
        self.assertEqual(self.call(second, 'ping'), {})
        self.assertEqual(request({'op': 'status'})['pid'], info['pid'])
        self.assertFalse((self.root / 'state' / 'sidebar-views').exists())

    def test_inspect_export_tools_run_without_a_view(self):
        proxy = self.proxy()
        def finished(name, arguments):
            status = self.tool(proxy, name, arguments)['structuredContent']
            for _ in range(30):
                if status['state'] in ('succeeded', 'failed', 'cancelled', 'rejected'):
                    break
                status = self.tool(proxy, name, {'action': 'status', 'operationId': status['id'],
                    'epoch': status['epoch'], 'afterSequence': status['sequence'], 'waitMs': 25000})['structuredContent']
            return status

        def operation(name, arguments):
            status = finished(name, arguments)
            self.assertEqual(status['state'], 'succeeded', status)
            return status['result']
        # A model is built by its script's call, never by a tool: a bare model, held in memory alone.
        folder = (self.root / 'tool-models').resolve()
        folder.mkdir()
        script = folder / 'http_part.py'
        script.write_text('from build123d import Box\nfrom cadgen import model\n\n\n@model\n'
                          'def http_part():\n    return Box(2, 3, 4)\n', encoding='utf-8')
        from cadgen.engine.api import build_script
        built = build_script(script, ['http_part'])
        self.assertTrue(built.ok)
        ident = built.models[0]['id']  # what `python http_part.py` prints, `id:`
        self.assertNotIn('cad_build', {tool['name'] for tool in self.call(proxy, 'tools/list')['tools']})
        facts = operation('cad_inspect', {'requestId': 'inspect-request-01', 'source': f'{ident}#face 1'})
        self.assertEqual(facts['inspection']['kind'], 'face')
        target = (self.root / 'tool-export.step').resolve()
        written = operation('cad_export', {'requestId': 'export-request-001', 'source': ident, 'destinations': [str(target)]})
        # A script is never a source, whatever names it: each tool refuses it as it refuses any
        # file that is no document, and nothing is built or written.
        for at, named in enumerate((str(script), f'{script}::http_part')):
            for name, arguments in (('cad_export', {'destinations': [str(self.root / 'refused.step')]}),
                                    ('cad_snapshot', {'output': str(self.root / 'refused.png')}),
                                    ('cad_inspect', {})):
                with self.subTest(tool=name, source=named):
                    status = finished(name, {'requestId': f'refused-{name}-{at:02d}-request', 'source': named, **arguments})
                    self.assertIn(status['state'], ('failed', 'rejected'), status)
                    self.assertRegex(status.get('error', ''), 'is no document|is neither a document')
        self.assertFalse((self.root / 'refused.step').exists() or (self.root / 'refused.png').exists())
        self.assertEqual([path.name for path in folder.iterdir()], ['http_part.py'])
        self.assertEqual(written['files'][0]['bytes'], target.stat().st_size)
        self.assertGreater(target.stat().st_size, 0)

    def test_http_transport_validation_and_session_lifecycle(self):
        client = EngineClient()
        def post(message, **headers):
            return client.call('POST', '/mcp', json.dumps(message).encode('utf-8'),
                               {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', **headers})
        self.assertEqual(client.call('GET', '/mcp')[0], 405)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})[0], 400)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, **{'Mcp-Session-Id': 'unknown'})[0], 404)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': INIT}, Origin='https://evil.example')[0], 403)
        self.assertEqual(post([])[0], 400)
        self.assertEqual(post({}, Accept='application/json')[0], 406)
        proxy = self.proxy()
        headers = {'Mcp-Session-Id': proxy.session}
        self.assertEqual(post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, **headers)[0], 202)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, **headers, **{'MCP-Protocol-Version': 'bogus'})[0], 400)
        with self.assertRaises(RpcError) as failure:
            self.call(proxy, 'does/not/exist')
        self.assertEqual(failure.exception.code, -32601)
        self.assertEqual(client.call('DELETE', '/mcp', headers=headers)[0], 200)
        self.assertEqual(post({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}, **headers)[0], 404)

    def test_shim_opens_a_new_session_when_the_engine_session_ends(self):
        # A host initializes once: an expired session or a restarted engine must not leave the
        # server answering every later call with an error until the host reconnects it.
        proxy = self.proxy()
        proxy.notify('notifications/initialized', {})
        first = proxy.session
        self.assertEqual(EngineClient().call('DELETE', '/mcp', headers={'Mcp-Session-Id': first})[0], 200)
        views = self.tool(proxy, 'cad_view')
        self.assertEqual(views['structuredContent'], {'views': []})
        second = proxy.session
        self.assertNotEqual(second, first)
        from cadgen.engine.api import stop
        pid = request({'op': 'status'})['pid']
        self.assertTrue(stop())
        engine_daemon.bootstrap(self.env)  # a deliberate restart, not a document client side effect
        self.assertEqual(self.call(proxy, 'ping'), {})
        self.assertNotEqual(proxy.session, second)
        self.assertNotEqual(request({'op': 'status'})['pid'], pid)
        self.assertIn('cad_open', [tool['name'] for tool in self.call(proxy, 'tools/list')['tools']])

    def test_stdio_shim_serves_resource_and_exits_without_stopping_engine(self):
        process = subprocess.Popen([sys.executable, '-m', 'cadgen.cli', 'mcp'],
                    env={**self.env, 'CADGEN_MCP_APP_DIR': str(self.page)},
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def close():
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=20)
        self.addCleanup(close)
        def rpc(ident, method, params):
            process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})+'\n')
            process.stdin.flush()
            result = json.loads(process.stdout.readline())
            self.assertEqual(result['id'], ident)
            self.assertNotIn('error', result)
            return result['result']
        self.assertEqual(rpc(1, 'initialize', INIT)['protocolVersion'], '2025-11-25')
        # The server holds the engine while its host runs.
        self.await_holders(1)
        resources = rpc(2, 'resources/list', {})['resources']
        document = rpc(3, 'resources/read', {'uri': resources[0]['uri']})['contents'][0]['text']
        self.assertIn('<title>test app</title>', document)
        tools = rpc(4, 'tools/list', {})['tools']
        self.assertIn('cad_open', [tool['name'] for tool in tools])
        process.stdin.close()
        process.stdin = None
        self.assertEqual(process.wait(timeout=20), 0)
        self.assertTrue(request({'op': 'status'})['ok'])
        self.await_holders(0)  # let go with the host; the engine runs on

    def test_a_shim_ended_by_a_signal_or_killed_leaves_no_session_behind(self):
        # A host (codex exec) may end its MCP server with SIGTERM, or kill it outright, rather than
        # close its input: the shim ends its session on SIGTERM itself, and the engine ends the
        # session of a shim whose hold is gone, which a killed one cannot say.
        import signal

        def mcp():
            return [row for row in request({'op': 'status'})['sessions'] if row.get('kind') == 'mcp']

        # Windows has no SIGTERM a process can catch: its ending is TerminateProcess, as a kill is.
        endings = ((signal.SIGTERM, 128 + signal.SIGTERM), (signal.SIGKILL, -signal.SIGKILL)) if os.name != 'nt' \
            else ((signal.SIGTERM, 1),)
        for ending, code in endings:
            before = len(mcp())
            process = subprocess.Popen([sys.executable, '-m', 'cadgen.cli', 'mcp'], env=self.env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            self.addCleanup(lambda process=process: process.poll() is None and process.kill())
            process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': INIT}) + '\n')
            process.stdin.flush()
            self.assertNotIn('error', json.loads(process.stdout.readline()))
            self.assertEqual(len(mcp()), before + 1)
            self.await_holders(1)  # its hold taken: the name its session ends with
            process.send_signal(ending)
            self.assertEqual(process.wait(timeout=20), code, f'{ending.name}: the shim left as it should')
            process.stdin.close()
            process.stdout.close()
            deadline = time.monotonic() + 30
            while len(mcp()) != before:
                self.assertLess(time.monotonic(), deadline, f'{ending.name}: the session ended')
                time.sleep(0.05)
            self.await_holders(0)

    def await_holders(self, count):
        deadline = time.monotonic() + 60
        while request({'op': 'status'})['holders'] != count:
            self.assertLess(time.monotonic(), deadline, f'the engine came to {count} holders')
            time.sleep(0.05)

    def test_shim_imports_no_tool_server_or_viewer_application(self):
        code = "import sys; from cadgen.mcp.shim import Proxy; assert not {'cadgen.mcp.server', 'cadgen.mcp.ui', 'cadgen.viewer.http_app', 'OCP', 'build123d'} & sys.modules.keys()"
        done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == '__main__':
    unittest.main()


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup, start=False)
