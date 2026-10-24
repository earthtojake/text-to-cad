"""The operation lifecycle through tools, without requiring a viewer or kernel."""
import json
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

    def test_closed_inputs_and_explicit_paths(self):
        jobs = Operations()
        invalid = jobs.call('cad_inspect', {'requestId': 'request-0000000001', 'source': 'relative.xbf', 'build': True})
        self.assertEqual(invalid['state'], 'rejected')
        answer = jobs.call('cad_inspect', {'requestId': 'request-0000000001', 'source': 'relative.xbf'})
        with patch('cadgen.engine.api.inspect', side_effect=AssertionError('must not inspect')):
            self.assertEqual(self.finish(jobs, answer)['state'], 'failed')

    def test_a_result_never_leaks_the_viewer_token(self):
        jobs = Operations()
        args = {'requestId': 'inspect-request-0001', 'source': str(Path('/tmp/part.xbf').resolve())}
        with patch('cadgen.engine.api.inspect', return_value={'kind': 'face', 'url': 'http://host/?token=secret',
                                                              'token': 'secret'}):
            result = self.finish(jobs, jobs.call('cad_inspect', args))
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(result['result'], {'inspection': {'kind': 'face'}})
        self.assertNotIn('secret', json.dumps(result))

    def test_no_tool_builds_source_text(self):
        # A model is built by its script's call (law 12): there is no build tool to call.
        self.assertNotIn('cad_build', {tool['name'] for tool in catalog()})
        answer = Operations().call('cad_build', {'requestId': 'build-request-0001', 'code': 'result = 1'})
        self.assertEqual(answer['state'], 'rejected')

    def test_tool_envelope_and_catalog_need_no_view(self):
        server = Server()
        # Test the same adapter used by every presentation without starting analytics.
        result = server._operation('cad_export', {'requestId': 'short'})
        self.assertTrue(result['isError'])
        self.assertEqual(result['structuredContent']['state'], 'rejected')
        tools = {t['name']: t for t in catalog()}
        self.assertEqual(set(tools), {'cad_export', 'cad_snapshot', 'cad_inspect'})
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
            snapshot.assert_called_once_with(job=packet)
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
