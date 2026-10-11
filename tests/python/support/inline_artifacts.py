"""Build-pool work run where it is submitted, for tests of what a job does rather
than how it is dispatched (the dispatch has its own tests: test_daemon_artifacts*)."""

from __future__ import annotations

import contextlib
from concurrent.futures import Future
from unittest import mock


@contextlib.contextmanager
def inline_artifacts(run=None):
    """Every artifact job this process submits (``artifacts.submit_artifact``, which
    ``resolve_artifact`` and ``resolve_artifacts`` go through) runs at once, on the
    submitting thread, through the worker's own entry (``artifacts.execute``) and
    result binding -- or through ``run(request)`` when given. Yields the mock, whose
    calls are the requests."""
    from cadgen.daemon import artifacts

    def submit(request, *, store_root=None):
        future = Future()
        try:
            value = run(request) if run is not None else artifacts.execute(request)
            future.set_result(artifacts.validate_result(request, artifacts.result_frame(request, value)))
        except Exception as error:  # noqa: BLE001 - the future carries it, as a worker's would
            future.set_exception(error)
        return future

    with mock.patch.object(artifacts, "submit_artifact", side_effect=submit) as submitted:
        yield submitted
