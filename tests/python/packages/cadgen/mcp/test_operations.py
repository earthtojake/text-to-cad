"""The operation lifecycle through tools, without requiring a viewer or kernel."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.jobs import TERMINAL
from cadgen.mcp.operations import Operations, catalog
from cadgen.mcp.server import Server


class OperationsTest(unittest.TestCase):
    def finish(self, jobs, answer):
        with jobs.changed:
            self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[answer['id']]['state'] in TERMINAL, timeout=10))
        return jobs.get(answer['id'])

    def test_retry_progress_cancellation_and_session_identity(self):
        jobs = Operations()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        def inspect(**args):
            calls.append(args)
            entered.set()
            release.wait(10)
            return {'volume': 6}
        args = {'requestId': 'request-0000000001', 'source': str(Path('/tmp/model.xbf').resolve()), 'ref': 'face 1'}
        with patch('cadgen.engine.api.inspect', inspect):
            first = jobs.call('cad_inspect', args)
            self.assertTrue(entered.wait(10))
            second = jobs.call('cad_inspect', {**args, 'requestId': 'request-0000000002'})
            self.assertEqual(jobs.call('cad_inspect', args)['id'], first['id'])
            self.assertEqual(jobs.call('cad_inspect', {**args, 'ref': 'face 2'})['status'], 409)
            follow = {'action': 'cancel', 'operationId': second['id'], 'epoch': second['epoch']}
            self.assertEqual(jobs.call('cad_inspect', follow)['state'], 'cancelled')
            self.assertEqual(jobs.call('cad_export', follow)['status'], 409)
            self.assertEqual(jobs.call('cad_inspect', {**follow, 'operationId': first['id']})['status'], 409)
            self.assertEqual(jobs.call('cad_inspect', {**follow, 'epoch': 'old'})['status'], 409)
            self.assertTrue(jobs.keeps_alive())
            release.set()
            result = self.finish(jobs, first)
        self.assertEqual(result['result'], {'inspection': {'volume': 6}})
        self.assertGreater(result['sequence'], first['sequence'])
        self.assertEqual(len(calls), 1)
        self.assertFalse(jobs.keeps_alive())
        jobs.clock = lambda: result['finishedAt'] + 86401
        self.assertEqual(jobs.call('cad_inspect', args)['status'], 410)

    def test_status_carries_the_engines_latest_progress_event_and_wakes_after_sequence(self):
        # Where an operation is comes from the engine alone, as its one progress event
        # (``cadgen.engine.progress``): the status keeps the latest whole in ``progress``, says its stage's
        # words in ``stage``, and a status asked ``afterSequence`` wakes with the next one.
        from cadgen.engine.progress import event

        jobs = Operations()
        read, write = (event("export", "read", job="arm.xbf", outputs=["/tmp/arm.step"], detail="arm.xbf"),
                       event("export", "write", job="arm.xbf", outputs=["/tmp/arm.step"], detail="arm.step", done=0, total=1, elapsed_ms=40))
        said, release, written, finish = threading.Event(), threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(finish.set)

        def export(source, *destinations, progress=None, **_args):
            progress(read)
            said.set()
            release.wait(10)
            progress(write)
            written.set()
            finish.wait(10)  # held at its second event, so the status read is of that event
            return []
        args = {'requestId': 'export-request-0001', 'source': str(Path('/tmp/arm.xbf').resolve()),
                'destinations': [str(Path('/tmp/arm.step').resolve())]}
        with patch('cadgen.engine.api.export', export):
            started = jobs.call('cad_export', args)
            self.assertTrue(said.wait(10))
            follow = {'action': 'status', 'operationId': started['id'], 'epoch': started['epoch']}
            status = jobs.call('cad_export', follow)
            self.assertEqual((status['state'], status['progress'], status['stage']), ('running', read, 'Reading the document'))
            waiting = []
            asked = threading.Thread(target=lambda: waiting.append(jobs.call('cad_export', {**follow, 'afterSequence': status['sequence'], 'waitMs': 10000})))
            asked.start()
            release.set()
            asked.join(10)
            self.assertFalse(asked.is_alive(), 'the status asked after its sequence woke with the next event')
            self.assertTrue(written.wait(10))
            self.assertEqual((waiting[0]['state'], waiting[0]['progress'], waiting[0]['stage']), ('running', write, 'Writing files'))
            self.assertGreater(waiting[0]['sequence'], status['sequence'])
            finish.set()
            result = self.finish(jobs, started)
        self.assertEqual((result['state'], result['stage'], result['progress']), ('succeeded', 'Complete', write))

    def test_a_snapshot_and_an_inspection_hand_the_engine_their_progress_taker(self):
        from cadgen.engine.api import Drawn

        jobs = Operations()
        source, out = str(Path('/tmp/part.xbf').resolve()), str(Path('/tmp/part.png').resolve())
        with patch('cadgen.engine.api.snapshot', return_value=Drawn(Path(out), 4, 3, {})) as snapshot, \
                patch('cadgen.engine.api.inspect', return_value={}) as inspect:
            self.finish(jobs, jobs.call('cad_snapshot', {'requestId': 'snapshot-request-02', 'source': source, 'output': out}))
            self.finish(jobs, jobs.call('cad_inspect', {'requestId': 'inspect-request-002', 'source': source, 'query': 'closure'}))
        self.assertTrue(callable(snapshot.call_args.kwargs['progress']))
        self.assertTrue(callable(inspect.call_args.kwargs['progress']))

    def test_the_structure_is_the_summary_s_lists_with_its_text(self):
        jobs = Operations()
        structure = {'name': 'hinge', 'id': 'x', 'state': {'state': 'file', 'path': '/m/a.xbf'},
                     'parts': {'occurrences': 2, 'distinct': 2, 'root': 'hinge'},
                     'materials': [{'name': 'Aluminum 6061-T6', 'density': 2700.0, 'parts': ['hinge/base']}],
                     'unweighed': ['hinge/arm'], 'joints': [], 'couplings': [], 'states': [], 'sequences': [],
                     'animations': [], 'files': []}
        with patch('cadgen.engine.api.inspect', return_value={'summary': structure, 'closure': None}) as inspect:
            done = jobs.call('cad_inspect', {'requestId': 'inspect-structure-0001', 'source': str(Path('/tmp/a.xbf').resolve()),
                                             'query': 'structure', 'waitMs': 10000})
        self.assertEqual({key: value for key, value in inspect.call_args.kwargs.items() if key != 'progress'},
                         {'source': str(Path('/tmp/a.xbf').resolve()), 'query': 'structure'})
        self.assertTrue(callable(inspect.call_args.kwargs['progress']))
        text = done['result']['inspection']['text']
        self.assertIn('  Aluminum 6061-T6: hinge/base', text)
        self.assertNotIn('volume', text)
        self.assertNotIn('bounds', text)

    def test_closed_inputs_and_explicit_paths(self):
        jobs = Operations()
        invalid = jobs.call('cad_inspect', {'requestId': 'request-0000000001', 'source': 'relative.xbf', 'build': True})
        self.assertEqual(invalid['state'], 'rejected')
        with patch('cadgen.engine.api.inspect', side_effect=AssertionError('must not inspect')):
            answer = jobs.call('cad_inspect', {'requestId': 'request-0000000001', 'source': 'relative.xbf'})
        # Refused as it starts: nothing is queued that could only fail.
        self.assertEqual((answer['state'], answer['error']), ('rejected', 'Paths must be absolute on the engine host'))
        self.assertEqual(jobs.jobs, {})

    def test_a_result_never_leaks_the_viewer_token(self):
        jobs = Operations()
        args = {'requestId': 'inspect-request-0001', 'source': str(Path('/tmp/part.xbf').resolve())}
        with patch('cadgen.engine.api.inspect', return_value={'kind': 'face', 'url': 'http://host/?token=secret',
                                                              'token': 'secret'}):
            result = self.finish(jobs, jobs.call('cad_inspect', args))
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(result['result'], {'inspection': {'kind': 'face'}})
        self.assertNotIn('secret', json.dumps(result))

    def test_tool_envelope_and_catalog_need_no_view(self):
        server = Server()
        # Test the same adapter used by every presentation without starting analytics.
        result = server._operation('cad_export', {'requestId': 'short'})
        self.assertTrue(result['isError'])
        self.assertEqual(result['structuredContent']['state'], 'rejected')
        tools = {t['name']: t for t in catalog()}
        self.assertEqual(set(tools), {'cad_export', 'cad_snapshot', 'cad_inspect', 'cad_run'})
        self.assertTrue(tools['cad_inspect']['annotations']['readOnlyHint'])
        self.assertFalse(tools['cad_export']['annotations']['readOnlyHint'])
        self.assertTrue(all('_meta' not in tool for tool in tools.values()))

    def test_snapshot_packet_checks_nested_paths_before_rendering(self):
        jobs = Operations()
        with patch('cadgen.engine.api.snapshot') as snapshot:
            packet = {'input': str(Path('/tmp/model.xbf').resolve()), 'jobs': [{'input': 'relative.xbf', 'outputs': ['/tmp/out.png']}]}
            answer = jobs.call('cad_snapshot', {'requestId': 'snapshot-request-01', 'packet': packet})
            self.assertEqual(self.finish(jobs, answer)['state'], 'failed')
            snapshot.assert_not_called()

    def test_session_keeps_completed_long_operation_available(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from cadgen.mcp.http import Session, Sessions
        now = [0]
        jobs = Operations(clock=lambda: now[0])
        sessions = Sessions(None)
        session = Session(SimpleNamespace(operations=jobs, sidebar_views=Mock()), 'protocol', 'test', touched=0)
        sessions.sessions['s'] = session
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def inspect(**args):
            entered.set()
            release.wait(10)
            return {}
        with patch('cadgen.engine.api.inspect', inspect), patch('cadgen.mcp.http.time.monotonic', lambda: now[0]):
            started = jobs.call('cad_inspect', {'requestId': 'inspect-request-01', 'source': str(Path('/tmp/part.xbf').resolve())})
            self.assertTrue(entered.wait(10))
            now[0] = 7200
            sessions._expire()
            self.assertIn('s', sessions.sessions)
            release.set()
            self.finish(jobs, started)
            sessions._expire()
            self.assertIn('s', sessions.sessions, 'completion starts the idle window again')
            now[0] += 3601
            sessions._expire()
            self.assertNotIn('s', sessions.sessions)

    def test_a_long_session_keeps_bounded_history_and_never_refuses_for_it(self):
        # 128 finished operations once refused every later start for a day ("history is full").
        from cadgen.mcp import operations
        jobs = Operations()
        source = str(Path('/tmp/part.xbf').resolve())
        with patch('cadgen.engine.api.inspect', return_value={'long': 'x' * (3 * 1024 * 1024)}):
            answers = [self.finish(jobs, jobs.call('cad_inspect', {'requestId': f'history-request-{i:04d}', 'source': source}))
                       for i in range(operations.HISTORY_JOBS * 2 + 5)]
        self.assertTrue(all(answer['state'] == 'succeeded' for answer in answers))
        self.assertTrue(answers[-1]['result']['truncated'])
        with jobs.changed:
            self.assertLessEqual(len(jobs.jobs), operations.HISTORY_JOBS)
            self.assertLessEqual(sum(job['kept'] for job in jobs.jobs.values()), operations.HISTORY_BYTES)
            self.assertTrue(all(len(json.dumps(job.get('result'))) < 10000 for job in jobs.jobs.values()))
        again = jobs.call('cad_inspect', {'requestId': 'history-request-0000', 'source': source})
        self.assertEqual((again['state'], again['status']), ('rejected', 410))

    def test_snapshot_accepts_inline_packet_and_returns_picture_artifacts(self):
        from cadgen.engine.api import Drawn
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            packet = {'input': str(root / 'part.xbf'), 'jobs': [{'outputs': [str(root / 'view.png')]}]}
            jobs = Operations()
            with patch('cadgen.engine.api.snapshot', return_value=[Drawn(root / 'view.png', 40, 30, {})]) as snapshot:
                result = self.finish(jobs, jobs.call('cad_snapshot', {'requestId': 'snapshot-request-01', 'packet': json.dumps(packet)}))
            self.assertEqual(result['state'], 'succeeded')
            snapshot.assert_called_once()
            self.assertEqual(snapshot.call_args.kwargs['job'], packet)
            self.assertTrue(callable(snapshot.call_args.kwargs['progress']), 'the engine is handed where to say its stages')
            self.assertEqual(result['result']['pictures'][0]['path'], str(root / 'view.png'))

    def test_failure_reports_possible_outputs_and_long_result_is_explicit(self):
        jobs = Operations()
        args = {'requestId': 'export-request-001', 'source': str(Path('/tmp/source.xbf').resolve()),
                'destinations': [str(Path('/tmp/output.step').resolve())]}
        with patch('cadgen.engine.api.export', side_effect=ValueError('second translation failed')):
            answer = self.finish(jobs, jobs.call('cad_export', args))
        self.assertEqual(answer['state'], 'failed')
        self.assertTrue(answer['result']['outputsMayHaveBeenWritten'])
        with jobs.changed:
            jobs.jobs[answer['id']]['result'] = {'long': 'x' * (2 * 1024 * 1024)}
        result = jobs.get(answer['id'])
        self.assertTrue(result['result']['truncated'])
        self.assertLess(len(json.dumps(result)), 10000)


class RunOperationTest(unittest.TestCase):
    """``cad_run``: the engine runs a script as ``cadgen run`` runs it, and the operation carries the run."""

    def finish(self, jobs, answer):
        with jobs.changed:
            self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[answer['id']]['state'] in TERMINAL, timeout=30))
        return jobs.get(answer['id'])

    def folder(self):
        folder = Path(tempfile.mkdtemp(prefix='cadgen-run-op-'))
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        return folder

    def test_the_catalog_offers_cad_run_by_path_or_by_code_and_name(self):
        tool = next(tool for tool in catalog() if tool['name'] == 'cad_run')
        self.assertIn('cad_show', tool['description'])
        self.assertIn('To start: {requestId, script} or {requestId, code, name}, optionally with args, waitMs.', tool['description'])
        self.assertFalse(tool['annotations']['readOnlyHint'])

    def test_a_run_is_refused_before_anything_is_queued(self):
        jobs = Operations()
        for arguments, said in (({'script': 'model.py'}, 'script must be an absolute path'),
                                ({'code': 'print(1)'}, 'missing name'),
                                ({'code': 'print(1)', 'name': '../escape'}, 'name is letters, digits, _ and -'),
                                ({'script': str(Path('/nonexistent/arm.py').resolve())}, 'no script')):
            with self.subTest(arguments=arguments):
                answer = jobs.call('cad_run', {'requestId': 'run-request-00000001', **arguments})
                self.assertEqual((answer['state'], answer['status']), ('rejected', 400))
                self.assertIn(said, answer['error'])
        self.assertFalse(jobs.jobs)

    def test_a_run_hands_the_engine_the_script_and_reports_its_output_and_documents(self):
        script = self.folder() / 'model.py'
        script.write_text('', encoding='utf-8')
        commands = []

        def command(path, arguments):
            commands.append((path, arguments))
            return [sys.executable, '-c', "import sys; print('id: abc'); sys.stderr.write('warn\\n'); print('view: http://x/abc')"]

        documents = [{'id': 'abc', 'name': 'part', 'state': 'live'}]
        jobs = Operations()
        with patch('cadgen.mcp.runs.command', command), patch('cadgen.mcp.runs.documents', lambda path: list(documents)):
            done = self.finish(jobs, jobs.call('cad_run', {'requestId': 'run-request-00000002', 'script': str(script),
                                                           'args': ['--size', '2']}))
        self.assertEqual(done['state'], 'succeeded', done.get('error'))
        self.assertEqual(commands, [(script.resolve(), ['--size', '2'])])
        result = done['result']
        self.assertEqual(result['script'], str(script.resolve()))
        self.assertEqual(result['output'].splitlines(), ['id: abc', 'warn', 'view: http://x/abc'], 'stdout and stderr, in order')
        self.assertEqual(result['documents'], documents)
        self.assertEqual((done['progress']['kind'], done['progress']['detail']), ('run', 'view: http://x/abc'))
        self.assertEqual(done['stage'], 'Complete')

    def test_a_script_given_as_code_is_kept_by_name_and_a_rerun_takes_its_place(self):
        state = self.folder()
        jobs = Operations()
        with patch.dict(os.environ, {'CADGEN_STATE_DIR': str(state)}), \
                patch('cadgen.mcp.runs.command', lambda path, arguments: [sys.executable, str(path), *arguments]), \
                patch('cadgen.mcp.runs.documents', lambda path: []):
            first = self.finish(jobs, jobs.call('cad_run', {'requestId': 'run-request-00000003', 'name': 'arm_v2',
                                                            'code': 'import sys\nprint("first", __file__, sys.argv[1:])\n',
                                                            'args': ['a']}))
            kept = state / 'scripts' / 'arm_v2' / 'arm_v2.py'
            self.assertTrue(kept.is_file())
            self.assertEqual(first['state'], 'succeeded', first.get('error'))
            self.assertEqual(first['result']['output'], f"first {kept} ['a']")
            second = self.finish(jobs, jobs.call('cad_run', {'requestId': 'run-request-00000004', 'name': 'arm_v2',
                                                             'code': 'print("second")\n'}))
        self.assertEqual(second['state'], 'succeeded', second.get('error'))
        self.assertEqual((second['result']['script'], second['result']['output']), (str(kept), 'second'))
        self.assertEqual(kept.read_text(encoding='utf-8'), 'print("second")\n', 'one folder per name: the rerun took its place')

    def test_a_failing_run_is_the_operations_failure_with_its_last_lines(self):
        script = self.folder() / 'model.py'
        script.write_text('', encoding='utf-8')
        jobs = Operations()
        with patch('cadgen.mcp.runs.command', lambda path, arguments: [sys.executable, '-c', "print('starting'); raise SystemExit(3)"]), \
                patch('cadgen.mcp.runs.documents', lambda path: []):
            done = self.finish(jobs, jobs.call('cad_run', {'requestId': 'run-request-00000005', 'script': str(script)}))
        self.assertEqual(done['state'], 'failed')
        self.assertEqual(done['error'], 'cadgen run model.py exited 3\nstarting')
        self.assertTrue(done['result']['outputsMayHaveBeenWritten'], 'a script may have written what its models declare')

