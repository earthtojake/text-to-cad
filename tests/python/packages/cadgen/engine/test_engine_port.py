"""Explicit server startup, private port selection, what a client meets the engine by (protocol,
document format and native line, never the release: exact release matching is gone), an older
release's engine retired by a start once idle, and persistent credentials."""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cadgen.engine import client, daemon, previous, registry, runtime
from tests.python.packages.cadgen.engine.test_progress import await_


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class EnginePortTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='cadgen-port-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.port = free_port()
        patch = mock.patch.dict(os.environ, {
            'CADGEN_ENGINE_DIR': str(self.root / 'engine'), 'CADGEN_STATE_DIR': str(self.root / 'state'),
            'CADGEN_CACHE_DIR': str(self.root / 'cache'), 'CADGEN_PORT': str(self.port),
            'CADGEN_LAUNCHER_DIR': str(self.root / 'bin'),
            'CADGEN_ENGINE_STANDBY': '0', 'CADGEN_VIEWER_WARM': '0',
        })
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.stop)

    def stop(self):
        from tests.python.support import engine_daemon

        status = client.request({'op': 'status'}, start=False)
        if status and client.request({'op': 'stop'}, start=False):
            self.assertTrue(client.wait_gone())
            # Its lock goes before its process does, and on Windows the daemon stands in the folder above
            # its state dir -- this test's, which cannot go while it lives (engine_daemon.await_exit).
            self.assertTrue(engine_daemon.await_exit(status['pid']))

    def start(self):
        connection = client.connect(start=True)
        self.assertIsNotNone(connection)
        connection.close()
        return client.request({'op': 'status'})

    def cli(self, *args, env=None):
        return subprocess.run([sys.executable, '-m', 'cadgen.cli', *args], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_missing_server_is_actionable_and_normal_requests_never_start_it(self):
        with mock.patch.object(client, '_start') as start:
            with self.assertRaisesRegex(ConnectionError, f'cadgen server --port {self.port}'):
                client.request({'op': 'pid'})
            self.assertIsNone(client.connect())
            self.assertIsNone(client.hold())
            self.assertIsNone(client.request({'op': 'status'}, start=False))
            start.assert_not_called()
        self.assertFalse(daemon.address().exists())
        viewer = self.cli('viewer', '--api-only', '--json')
        self.assertNotEqual(viewer.returncode, 0)
        self.assertIn('no cadgen server', viewer.stderr)
        self.assertFalse(daemon.address().exists())

    def test_door_is_selected_by_port_not_python_installation_or_release_label(self):
        before = daemon.address()
        with mock.patch.object(sys, 'prefix', '/different/python'), \
                mock.patch.dict(os.environ, {'CADGEN_INSTALLATION_VERSION': '99.0.0'}):
            self.assertEqual(daemon.address(), before)
        with mock.patch.dict(os.environ, {'CADGEN_PORT': str(self.port + 1 if self.port < 65535 else self.port - 1)}):
            self.assertNotEqual(daemon.address(), before)
        with mock.patch.dict(os.environ, {'CADGEN_ENGINE_DIR': str(self.root / 'other')}):
            self.assertNotEqual(daemon.address(), before)
        with mock.patch.dict(os.environ, {'CADGEN_PORT': ''}):
            self.assertEqual(daemon.selected_port(), 3245)
        for bad in ('0', '-1', '65536', 'abc'):
            with self.subTest(port=bad), mock.patch.dict(os.environ, {'CADGEN_PORT': bad}):
                with self.assertRaisesRegex(ValueError, 'between 1 and 65535'):
                    daemon.address()

    def test_diagnostics_probe_only_hello_and_preserve_the_owned_engine(self):
        from cadgen._internal import diagnostics

        first = self.start()
        found = diagnostics.engine(self.port)
        self.assertEqual(found['status'], 'compatible', found)
        self.assertEqual(found['release'], previous.version())
        self.assertEqual(found['native'], runtime.identity()['native'])
        with mock.patch.object(previous, 'version', return_value='99.0.0'):
            other = diagnostics._probe_port(self.port)
        self.assertEqual(other['status'], 'compatible', 'a release apart alone meets the engine')
        ours = runtime.identity()
        with mock.patch.object(runtime, 'identity', return_value={**ours, 'protocol': ours['protocol'] + 1}):
            refused = diagnostics._probe_port(self.port)
        self.assertEqual((refused['status'], refused['reason']), ('incompatible', 'protocol'), refused)
        self.assertEqual(refused['release'], previous.version())
        self.assertEqual(refused['port'], self.port)
        self.assertNotIn('instance', refused)
        self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])

    def test_start_binds_immediately_and_compatible_bootstrap_reuses_it(self):
        first = self.start()
        self.assertEqual(first['serving']['port'], self.port)
        with socket.create_connection(('127.0.0.1', self.port), timeout=5):
            pass
        if os.name != 'nt':
            with mock.patch.object(socket, 'create_connection', side_effect=PermissionError('sandbox blocks sockets')):
                self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])
        with mock.patch.object(client, '_start') as start:
            with client.connect(start=True):
                pass
            with client.hold(start=True):
                self.assertEqual(client.request({'op': 'status'})['holders'], 1)
            start.assert_not_called()
        server = self.cli('server', '--port', str(self.port))
        self.assertEqual(server.returncode, 0, server.stderr)
        self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])
        viewer = self.cli('viewer', '--api-only', '--json', '--port', str(self.port))
        self.assertEqual(viewer.returncode, 0, viewer.stderr)
        self.assertEqual(json.loads(viewer.stdout)['port'], self.port)
        self.assertEqual(self.cli('server', '--port', '0').returncode, 2)

    def test_the_hello_says_what_the_engine_runs_as(self):
        # What `cadgen run` makes a project's environment to match: the installation, its Python's line and
        # where its cadgen installs from (this checkout's tree: an editable install, a source on the path).
        first = self.start()
        with client.connect() as connection:
            said = connection.engine
        self.assertEqual(said['installation'], first['installation'])
        self.assertEqual(said['python'], '%d.%d' % sys.version_info[:2])
        self.assertEqual(said['source'], str(Path(daemon.engine_root()).parent))
        self.assertTrue((Path(said['source']) / 'pyproject.toml').is_file())
        self.assertEqual(said['release'], previous.version())

    def test_a_release_apart_attaches_and_another_protocol_is_refused_by_name(self):
        first = self.start()
        with mock.patch.dict(os.environ, {'CADGEN_INSTALLATION_VERSION': '99.0.0'}):
            self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])
        major, minor, patch = previous.version().split('.')
        newer = f'{major}.{minor}.{int(patch) + 1}'
        with mock.patch.object(previous, 'version', return_value=newer):
            # A client of a newer release of one protocol, format and line attaches.
            self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])
        with mock.patch.object(previous, 'version', return_value='0.0.1'), mock.patch.object(client, '_start') as start:
            # An older one's start attaches too: it never retires a newer engine.
            with client.connect(start=True) as connection:
                self.assertEqual(connection.engine['release'], first['version'])
            start.assert_not_called()
        ours = runtime.identity()
        speaks = {**ours, 'protocol': ours['protocol'] + 1}
        with mock.patch.object(runtime, 'identity', return_value=speaks), mock.patch.object(client, '_start') as start:
            with self.assertRaises(client.Incompatible) as refused:
                client.connect(start=True)
            start.assert_not_called()
        self.assertEqual(str(refused.exception), (
            f"cadgen client speaks protocol {speaks['protocol']}, the engine on port {self.port} protocol "
            f"{ours['protocol']}: update the older one (run `{runtime.INSTALL}` for the engine; "
            "`uv pip install -U cadgen` in the project)"))
        self.assertEqual((refused.exception.what, refused.exception.engine['release']), ('protocol', first['version']))
        self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])

    def other_release(self, release):
        """This protocol's engine on the selected port, of another release: this code with its release said
        as ``release`` (``previous.version`` replaced in its process), started as a client starts one, and
        answering. Its process."""
        from tests.python.support import engine_daemon

        program = ('import sys; from cadgen.engine import daemon, previous; '
                   f'previous.version = lambda: {release!r}; sys.exit(daemon.main())')
        process = subprocess.Popen([sys.executable, '-c', program], env={**os.environ, 'CADGEN_INSTALLATION_VERSION': ''},
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(engine_daemon.reap, process)
        await_(lambda: process.poll() is not None or (client.request({'op': 'status'}, start=False) or {}).get('pid'),
               f'cadgen {release}\'s engine to answer')
        self.assertIsNone(process.poll(), f'cadgen {release}\'s engine exited')
        return process

    def test_an_idle_older_engine_is_retired_and_one_of_this_release_or_a_newer_never(self):
        older = self.other_release('0.0.1')
        self.assertEqual(client.request({'op': 'status'})['version'], '0.0.1', 'it meets this client, which attaches')
        self.assertEqual(client.retire_older(), {'release': '0.0.1', 'pid': older.pid, 'port': self.port})
        self.assertEqual(older.wait(60), 0, 'stopped through its own door, as `cadgen stop` stops it')
        self.assertIsNone(client.request({'op': 'status'}, start=False))
        self.assertIsNone(client.retire_older(), 'nothing older serves the port')
        newer = self.other_release('99.0.0')
        self.assertIsNone(client.retire_older(), 'an older installation never retires a newer one')
        self.assertEqual(client.request({'op': 'status'})['pid'], newer.pid)
        client.request({'op': 'stop'})
        self.assertEqual(newer.wait(60), 0)
        first = self.start()
        self.assertIsNone(client.retire_older(), 'nor one of its own release')
        self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])

    def test_an_older_engine_in_use_is_waited_for_and_never_displaced(self):
        older = self.other_release('0.0.1')
        held = client.hold()
        self.assertEqual(client.request({'op': 'status'})['holders'], 1)
        said = (f"port {self.port} is held by cadgen 0.0.1's engine (pid {older.pid}), still in use by 1 app server: "
                f"quit that app or run `cadgen stop --port {self.port}`")
        with self.assertRaises(ConnectionError) as refused:
            client.retire_older(wait=0)
        self.assertEqual(str(refused.exception), said)
        # A start that can use it serves with it while it is in use, and says so once.
        told = []
        with mock.patch.object(client, '_start') as start, client.connect(start=True, told=told.append) as connection:
            self.assertEqual(connection.engine['release'], '0.0.1')
            start.assert_not_called()
        self.assertEqual(told, [f"cadgen 0.0.1's engine (pid {older.pid}) on port {self.port} is in use by 1 app "
                                f"server, so it serves on for {daemon.installation()}: quit that app or run "
                                f"`cadgen stop --port {self.port}` to update it"])
        # Waited for: retired once its holder lets go, and not before.
        asked, results = [], []
        status = client._status_of

        def counted(*args):
            found = status(*args)
            asked.append(found)
            return found

        with mock.patch.object(client, '_status_of', side_effect=counted):
            waiting = threading.Thread(target=lambda: results.append(client.retire_older(wait=600)), daemon=True)
            waiting.start()
            await_(lambda: asked, 'the retirement to ask the engine in use again')
            self.assertIsNone(older.poll(), 'never displaced while in use')
            held.close()
            await_(lambda: not waiting.is_alive(), 'the retirement once its holder let go')
        self.assertEqual(results, [{'release': '0.0.1', 'pid': older.pid, 'port': self.port}])
        self.assertEqual(older.wait(60), 0)

    def test_the_server_retires_an_idle_older_engine_and_says_so_once(self):
        older = self.other_release('0.0.1')
        server = subprocess.Popen([sys.executable, '-m', 'cadgen.cli', 'server'], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: server.poll() is None and server.kill())
        said: list[str] = []
        while not said or 'retired' not in said[-1]:  # its first word of a retirement, whatever came before
            line = server.stderr.readline()
            self.assertTrue(line, f'the server ended before it said the retirement: {said}')
            said.append(line)
        self.assertEqual(said[-1], f"cadgen: retired cadgen 0.0.1's engine (pid {older.pid}) for {daemon.installation()}\n")
        self.assertEqual(older.wait(60), 0)
        await_(lambda: (client.request({'op': 'status'}, start=False) or {}).get('pid') == server.pid,
               'this release\'s server to answer')
        self.stop()
        self.assertEqual(server.wait(60), 0)
        self.assertNotIn('retired', server.stderr.read(), 'said once')
        server.stderr.close()

    def test_two_explicit_ports_are_independent_and_neither_retires_the_other(self):
        from cadgen.viewer.engine_client import EngineClient

        first = self.start()
        http = EngineClient()
        self.assertEqual(http.connect()['port'], self.port)
        other = free_port()
        with mock.patch.dict(os.environ, {'CADGEN_PORT': str(other), 'CADGEN_INSTALLATION_VERSION': '99.0.0'}):
            try:
                second = self.start()
                self.assertNotEqual(second['pid'], first['pid'])
                self.assertEqual(second['serving']['port'], other)
                self.assertEqual(http.connect()['port'], other)
            finally:
                self.stop()
        self.assertEqual(client.request({'op': 'pid'})['pid'], first['pid'])
        self.assertEqual(http.connect()['port'], self.port)

    def test_an_occupied_port_fails_without_rolling_or_stopping_its_owner(self):
        with socket.socket() as held:
            held.bind(('127.0.0.1', self.port))
            held.listen(5)
            result = self.cli('server')
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn(f'port {self.port} is held', result.stderr)
            self.assertFalse(daemon.address().exists())
            from cadgen._internal import diagnostics
            self.assertEqual(diagnostics.engine(self.port)['status'], 'conflicting_listener')
            with socket.create_connection(('127.0.0.1', self.port), timeout=5):
                pass

    def test_ports_share_the_latest_saved_document_across_restarts_and_delete(self):
        import build123d as bd
        from cadgen.engine import api

        self.start()
        first = api.hand_over(bd.Box(1, 1, 1), 'port_persistence')
        second_port = free_port()
        with mock.patch.dict(os.environ, {'CADGEN_PORT': str(second_port)}):
            try:
                self.start()
                second = api.hand_over(bd.Box(2, 2, 2), 'port_persistence')
                self.assertEqual(first.id, second.id)
            finally:
                self.stop()
        self.stop()
        self.start()
        restored = api.Document(first.name, first.script, first.report, first.cwd)
        self.assertAlmostEqual(restored.shape.volume, 8)
        with mock.patch.dict(os.environ, {'CADGEN_PORT': str(second_port)}):
            try:
                self.start()
                restored = api.Document(second.name, second.script, second.report, second.cwd)
                self.assertAlmostEqual(restored.shape.volume, 8)
            finally:
                self.stop()
        api.delete([first.id])
        self.assertIsNone(registry.current().get(first.id))
        with mock.patch.dict(os.environ, {'CADGEN_PORT': str(second_port)}):
            try:
                self.start()
                self.assertIsNone(registry.current().get(second.id))
                self.assertNotIn(second.id, [row['id'] for row in client.request({'op': 'status'})['models']])
                self.assertFalse(registry.current().cache.path(f'documents/{second.id}/document.xbf').exists())
            finally:
                self.stop()

    def test_token_survives_restart_and_rotation_requires_stopping_servers(self):
        self.start()
        first = client.request({'op': 'http'})['token']
        refused = self.cli('server', '--rotate-token')
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(client.request({'op': 'http'})['token'], first)
        self.stop()
        self.start()
        self.assertEqual(client.request({'op': 'http'})['token'], first)
        self.stop()
        daemon.rotate_token()
        self.start()
        self.assertNotEqual(client.request({'op': 'http'})['token'], first)

    @unittest.skipIf(os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0), 'POSIX file permissions')
    def test_unreadable_token_is_never_replaced(self):
        held = registry.current()
        held.put_token('t' * 43)
        path = self.root / 'state' / 'engines' / 'token'
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        with self.assertRaisesRegex(ValueError, 'page token.*cannot be read'):
            daemon.bind('127.0.0.1', self.port, lambda *_: self.fail('must not bind'))
        path.chmod(0o600)
        self.assertEqual(path.read_text(encoding='utf-8').strip(), 't' * 43)


class HandshakeTest(unittest.TestCase):
    def test_pythonpath_empty_entries_are_the_callers_current_folder_and_an_empty_one_is_none(self):
        cwd = os.getcwd()
        path = os.pathsep.join(('relative', '', '/absolute'))
        with mock.patch.dict(os.environ, {'PYTHONPATH': path}):
            self.assertEqual(client.environment()['PYTHONPATH'], os.pathsep.join(
                item if os.path.isabs(item) else os.path.join(cwd, item) for item in path.split(os.pathsep)))
        with mock.patch.dict(os.environ, {'PYTHONPATH': ''}):
            self.assertEqual(client.environment()['PYTHONPATH'], '', 'Python reads an empty one as none')

    def test_an_installed_cadgen_names_the_file_it_was_installed_from_and_a_release_none(self):
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder) / 'lib' / 'site-packages'
            site.mkdir(parents=True)
            wheel = Path(folder) / 'cadgen-0.8.3-py3-none-any.whl'
            wheel.write_bytes(b'')
            recorded = {'direct_url.json': json.dumps({'url': wheel.as_uri(), 'archive_info': {}})}
            installed = SimpleNamespace(read_text=lambda name: recorded.get(name))
            import importlib.metadata

            with mock.patch.object(daemon, 'engine_root', return_value=str(site)), \
                    mock.patch.object(importlib.metadata, 'distribution', return_value=installed):
                self.assertEqual(Path(daemon.source()), wheel, "a wheel built from a checkout: that wheel")
                recorded['direct_url.json'] = json.dumps({'url': 'https://example.com/cadgen.whl', 'archive_info': {}})
                self.assertIsNone(daemon.source(), 'a file elsewhere: the release')
                del recorded['direct_url.json']
                self.assertIsNone(daemon.source(), 'a release from the index installs again by its version')
                wheel.unlink()
                recorded['direct_url.json'] = json.dumps({'url': wheel.as_uri(), 'archive_info': {}})
                self.assertIsNone(daemon.source(), 'a file that is gone names nothing')

    def test_no_work_runs_before_the_hello_meets_and_the_instance_is_verified(self):
        # An engine of another release (0.8.0) than this client's: the release never decides.
        engine = SimpleNamespace(token='a' * 32, release_version='0.8.0', port=45001, instance='instance-one',
                                 unsaid='', refusal=None, handle=mock.Mock())
        identity = {'protocol': daemon.PROTOCOL, 'release': engine.release_version, 'port': engine.port,
                    'instance': engine.instance}
        hello = client.hello(port=engine.port)
        for windows in (False, True):
            def asked(*messages):
                out = io.BytesIO()
                data = ''.join(json.dumps({'token': engine.token, **message}) + '\n' for message in messages)
                with mock.patch.object(daemon, 'WINDOWS', windows):
                    daemon._serve(engine, io.BytesIO(data.encode()), out)
                return [json.loads(row) for row in out.getvalue().splitlines()]

            self.assertIn('handshake', asked({'op': 'build'})[0]['failed'])
            later = f"xbf/{int(hello['writes'].rpartition('/')[2]) + 1}"
            for crafted, said in (({'protocol': daemon.PROTOCOL + 1}, 'speaks protocol'),
                                  ({'writes': later}, f'writes {later}; the engine (cadgen 0.8.0, port 45001)'),
                                  ({'native': {**hello['native'], 'ocp_line': '0.1'}}, 'OCP 0.1'),
                                  ({'port': engine.port + 1}, 'serves port 45001')):
                refused = asked({**hello, **crafted}, {'op': 'build', 'engineIdentity': identity})
                self.assertIn(said, refused[0]['failed'])
                self.assertEqual({key: refused[0][key] for key in ('protocol', 'release', 'port')},
                                 {key: identity[key] for key in ('protocol', 'release', 'port')},
                                 'a refusal names the engine, so the client says both sides')
                self.assertEqual(refused[0]['writes'], hello['writes'])
                self.assertNotIn('instance', refused[0])
                self.assertEqual(len(refused), 1, 'a refused hello never admits the queued work')
            self.assertIn('instance', asked(hello, {'op': 'build', 'engineIdentity': {**identity, 'instance': 'old'}})[1]['failed'])
            engine.handle.assert_not_called()
            # A control connection asks status or stop alone, whatever it speaks.
            control = {**hello, 'protocol': daemon.PROTOCOL + 1, 'writes': later, 'control': True}
            answered = asked(control, {'op': 'build', 'engineIdentity': identity})
            self.assertEqual((answered[0]['ok'], answered[0]['control']), (True, True))
            self.assertIn('status or stop', answered[1]['failed'])
            engine.handle.assert_not_called()
            asked(control, {'op': 'stop', 'engineIdentity': identity})
            self.assertEqual(engine.handle.call_args.args[0]['op'], 'stop')
            engine.handle.reset_mock()
            asked(hello, {'op': 'build', 'engineIdentity': identity})
            engine.handle.assert_called_once()
            engine.handle.reset_mock()

    def test_the_client_checks_the_engine_s_answer_by_the_same_rule(self):
        ours = runtime.identity()
        port = daemon.selected_port()
        later = f"xbf/{int(ours['writes'].rpartition('/')[2]) + 1}"

        def greeted(answer):
            reader = io.BytesIO((json.dumps(answer) + '\n').encode())
            connection = client.Connection(reader, io.BytesIO())
            # On Windows the hello carries the port file's token (client._greet reads it); this answer's
            # check needs no engine, so a port file's text stands in for the one none wrote.
            with mock.patch.object(client, '_port_text', return_value=f'{port} token'):
                return client._greet(connection)

        engine = {**ours, 'port': port, 'instance': 'one'}
        self.assertEqual(greeted({'ok': True, **engine, 'release': '0.0.1'}).engine['release'], '0.0.1',
                         'an engine of another release that meets this client')
        for answer, what, said in (({'reads': [ours['reads'][0]], 'release': '0.0.1'}, 'format',
                                    f"reads up to {ours['reads'][0]}: update the engine"),
                                   ({'native': {**ours['native'], 'ocp_line': '0.1'}}, 'native', 'the engine has'),
                                   ({'protocol': ours['protocol'] - 1}, 'protocol', 'update the older one')):
            with self.subTest(what), self.assertRaises(client.Incompatible) as refused:
                greeted({'ok': True, **engine, **answer})
            self.assertEqual(refused.exception.what, what)
            self.assertIn(said, str(refused.exception))
        with self.assertRaises(client.Incompatible) as refused:
            greeted({'failed': 'refused', **engine, 'writes': later, 'reads': ours['reads'] + [later], 'release': '0.9.0',
                     'instance': None})
        self.assertIsNone(refused.exception.what, 'the engine refused what this client cannot tell: its own words')
        self.assertIn('refused', str(refused.exception))


if __name__ == '__main__':
    unittest.main()
