"""The build memory ceiling: how the peak is READ on each platform, cap
resolution, the trip, and memory on stage lines.

The reading half is here because it is the half no local run can prove: the
Windows branch never executes on a POSIX host, and its two spelling mistakes
(``c_ulong`` for a DWORD, ``c_ulong`` for a SIZE_T) return a plausible wrong
number rather than an error. So the struct SHAPE is asserted from any host, the
Windows reader is driven through a fake kernel32, and one unconditional
tripwire asserts a real live peak on whatever machine is running -- that last
one is the only assertion that executes the Windows branch on the Windows
runner, so it must never be skipped.
"""

from __future__ import annotations

import ctypes
import importlib
import inspect
import io
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from cadgen._internal import memory_guard
from cadgen._internal.memory_guard import ENV_VAR, FLOOR_BYTES, MemoryGuard, format_gb, peak_rss_bytes, resolve_cap_bytes
from cadgen.cli_logging import CliLogger

GB = 1024**3


class CapResolutionTest(unittest.TestCase):
    def test_env_override_in_gigabytes(self) -> None:
        self.assertEqual(12 * GB, resolve_cap_bytes({ENV_VAR: "12"}))
        self.assertEqual(int(1.5 * GB), resolve_cap_bytes({ENV_VAR: "1.5"}))

    def test_zero_disables(self) -> None:
        self.assertIsNone(resolve_cap_bytes({ENV_VAR: "0"}))
        self.assertIsNone(resolve_cap_bytes({ENV_VAR: "-3"}))

    def test_garbage_falls_back_to_the_default_not_to_disabled(self) -> None:
        self.assertIsNotNone(resolve_cap_bytes({ENV_VAR: "lots"}))

    def test_default_is_half_the_budget_with_a_floor(self) -> None:
        cap = resolve_cap_bytes({})
        self.assertIsNotNone(cap)
        self.assertGreaterEqual(cap, FLOOR_BYTES)


class GuardTripTest(unittest.TestCase):
    def _guard(self, peak: int, cap: int, stage: str = "run step model w16.py"):
        aborted: list[int] = []
        guard = MemoryGuard(
            cap,
            label="build of w16.py",
            describe_stage=lambda: stage,
            read_peak=lambda: peak,
            abort=aborted.append,
        )
        return guard, aborted

    def test_below_the_cap_nothing_happens(self) -> None:
        guard, aborted = self._guard(peak=3 * GB, cap=8 * GB)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertFalse(guard.check())
        self.assertEqual([], aborted)
        self.assertEqual("", err.getvalue())

    def test_above_the_cap_names_the_stage_and_the_override_then_aborts(self) -> None:
        guard, aborted = self._guard(peak=40 * GB, cap=32 * GB)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertTrue(guard.check())
        self.assertEqual([memory_guard.EXIT_CODE], aborted)
        message = err.getvalue()
        self.assertIn("during run step model w16.py", message)
        self.assertIn("peak 40.0 GB > cap 32.0 GB", message)
        self.assertIn(f"{ENV_VAR}=<gigabytes>", message)
        self.assertIn(f"{ENV_VAR}=0", message)

    def test_disabled_guard_never_reads_or_aborts(self) -> None:
        reads: list[int] = []
        guard = MemoryGuard(None, label="x", read_peak=lambda: reads.append(1) or 10**15, abort=lambda code: self.fail("aborted"))
        with guard:
            self.assertFalse(guard.check())
        self.assertEqual([], reads)

    def test_context_manager_thread_trips_on_its_own(self) -> None:
        import time

        aborted: list[int] = []
        guard = MemoryGuard(1, label="x", read_peak=lambda: 2, abort=aborted.append, sample_seconds=0.01)
        with guard:
            deadline = time.monotonic() + 2
            while not aborted and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual([memory_guard.EXIT_CODE], aborted)


class StageLinesCarryMemoryTest(unittest.TestCase):
    def test_verbose_stage_line_reports_peak_rss_and_stage_nesting(self) -> None:
        err = io.StringIO()
        logger = CliLogger("cad", verbose=True, stream=err) if "stream" in CliLogger.__dataclass_fields__ else CliLogger("cad", verbose=True)
        with redirect_stderr(err):
            with logger.timed("outer"):
                with logger.timed("inner"):
                    self.assertEqual("inner", logger.current_stage())
                self.assertEqual("outer", logger.current_stage())
        self.assertEqual("", logger.current_stage())
        text = err.getvalue()
        self.assertIn("inner completed in", text)
        self.assertRegex(text, r"outer completed in .*\(peak rss \d+\.\d GB\)")


class PeakRssReadingTest(unittest.TestCase):
    """The platform dispatch, both branches, from one host."""

    def test_the_module_imports_and_reads_zero_without_the_resource_module(self) -> None:
        """(a) The outage in miniature: ``resource`` is POSIX-only and this module
        is on every build's hot path. Unavailable must mean 0, never a raise.

        The module body is RE-EXECUTED under the block, not merely called into:
        the outage was a module-scope ``import resource``, and a test that only
        calls functions on an already-imported module would let it back in
        green. ``importlib.reload`` re-runs the body in the same module dict, so
        every name this file already bound stays valid."""
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "resource":
                raise ImportError("No module named 'resource'")
            return real_import(name, *args, **kwargs)

        self.addCleanup(importlib.reload, memory_guard)
        with mock.patch.object(builtins, "__import__", blocked):
            importlib.reload(memory_guard)  # the import that took Windows down
            self.assertIsNone(memory_guard._posix_peak_rss())
            if sys.platform != "win32":
                self.assertEqual(0, memory_guard.peak_rss_bytes())

    SIZE_T_FIELDS = (
        "PeakWorkingSetSize",
        "WorkingSetSize",
        "QuotaPeakPagedPoolUsage",
        "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage",
        "PagefileUsage",
        "PeakPagefileUsage",
    )

    def test_the_counters_struct_is_declared_with_the_win64_spellings(self) -> None:
        """(b1) The DECLARED types, read out of the source.

        This assertion exists because the resulting ctypes objects cannot carry
        it from a POSIX host: ``ctypes.c_size_t IS ctypes.c_ulong`` on LP64, and
        the two are the same 8 bytes there, so swapping every SIZE_T field to
        ``c_ulong`` -- 4 bytes on Win64, which would read PeakWorkingSetSize
        from the wrong offset and return a plausible wrong number rather than an
        error -- survives every size and offset check below. The spelling in the
        source is the only thing that differs on both hosts, so it is what is
        pinned."""
        source = inspect.getsource(memory_guard._windows_counters_type)
        declared = dict(re.findall(r'\("(\w+)",\s*ctypes\.(\w+)\)', source))
        self.assertEqual("c_uint32", declared.get("cb"))
        self.assertEqual("c_uint32", declared.get("PageFaultCount"))
        for name in self.SIZE_T_FIELDS:
            self.assertEqual("c_size_t", declared.get(name), name)
        self.assertEqual(10, len(declared), "the BASE struct has exactly ten fields")

    def test_the_counters_struct_has_the_win64_layout(self) -> None:
        """(b2) The layout in ABSOLUTE numbers -- 4 + 4 + 8*8 = 72.

        Host-derived expectations are what let the c_ulong mutation pass: an
        expectation computed from ``sizeof(c_size_t)`` moves with the field it
        is checking. Every host cadgen supports is 64-bit, so the Win64 numbers
        are simply written down."""
        counters = memory_guard._windows_counters_type()
        self.assertEqual(8, ctypes.sizeof(ctypes.c_void_p), "cadgen runs on 64-bit hosts only")
        self.assertEqual((0, 4), (counters.cb.offset, counters.cb.size))
        self.assertEqual((4, 4), (counters.PageFaultCount.offset, counters.PageFaultCount.size))
        for index, name in enumerate(self.SIZE_T_FIELDS):
            field = getattr(counters, name)
            self.assertEqual((8 + 8 * index, 8), (field.offset, field.size), name)
        self.assertEqual(72, ctypes.sizeof(counters))

    def test_the_windows_reader_returns_the_peak_working_set_unscaled(self) -> None:
        """(c) Windows already reports bytes, and ``cb`` must be the BASE struct's
        size -- the _EX variant is 80 and would be the wrong contract.

        72 is written down rather than asked of ``sizeof``: sizing the
        expectation from the type under test is how a grown struct would agree
        with itself."""
        calls: list[dict] = []
        pseudo_handle = 0xFFFFFFFFFFFFFFFF

        def get_current_process():
            return pseudo_handle

        def get_process_memory_info(handle, pointer, cb):
            # What the struct SAYS its size is, as well as the argument -- the
            # `counters.cb = size` line is otherwise uncovered.
            calls.append({"handle": handle, "cb": cb, "declared": pointer.contents.cb})
            pointer.contents.PeakWorkingSetSize = 7 * 1024**3
            return 1

        reader = memory_guard._windows_reader(load_library=_FakeKernel32(get_current_process, get_process_memory_info))
        self.assertIsNotNone(reader)
        self.assertEqual(7 * 1024**3, reader())
        self.assertEqual([{"handle": pseudo_handle, "cb": 72, "declared": 72}], calls)

    def test_the_windows_call_declares_its_signature(self) -> None:
        """(c2) The ABI statement, asserted as the declaration it is.

        A fake kernel32 cannot exercise ctypes marshalling at all -- these are
        plain Python functions, and ``.argtypes`` on one is an ordinary
        attribute. What it CAN pin is that production declares the signature,
        which is the thing that makes the real call correct: with no
        ``argtypes`` ctypes passes a Python int as a masked 32-bit C int, and
        the ``(HANDLE)-1`` pseudo-handle would then arrive only by way of
        libffi's sign extension."""
        counters_type = memory_guard._windows_counters_type()
        get_current_process, get_process_memory_info = (lambda: 0), (lambda handle, pointer, cb: 0)
        memory_guard._windows_reader(load_library=_FakeKernel32(get_current_process, get_process_memory_info))
        self.assertEqual([], get_current_process.argtypes)
        self.assertIs(ctypes.c_void_p, get_current_process.restype)
        self.assertEqual(
            [ctypes.c_void_p, ctypes.POINTER(counters_type), ctypes.c_uint32],
            get_process_memory_info.argtypes,
        )
        self.assertIs(ctypes.c_int, get_process_memory_info.restype)  # Win32 BOOL

    def test_the_windows_reader_gives_up_quietly_on_every_failure(self) -> None:
        """(d) A false BOOL, an unloadable library, an export that is not there."""
        def refusing(handle, pointer, cb):
            return 0  # Win32 BOOL false: nothing was written to the struct

        reader = memory_guard._windows_reader(load_library=_FakeKernel32(lambda: 0, refusing))
        self.assertIsNotNone(reader)
        self.assertIsNone(reader())

        def raising():
            raise OSError("kernel32 could not be loaded")

        self.assertIsNone(memory_guard._windows_reader(load_library=raising))
        self.assertIsNone(memory_guard._windows_reader(load_library=lambda: _NoExports()))

    def test_an_unreadable_windows_counter_fails_open(self) -> None:
        """(e) Unmeasurable must be 0 and a 0 must not trip a cap or print."""
        self.addCleanup(memory_guard._forget_windows_reader)
        memory_guard._forget_windows_reader()

        def raising():
            raise OSError("kernel32 could not be loaded")

        with mock.patch.object(memory_guard.sys, "platform", "win32"), \
                mock.patch.object(memory_guard, "_load_kernel32", raising):
            self.assertEqual(0, memory_guard.peak_rss_bytes())

        err = io.StringIO()
        guard = MemoryGuard(8 * GB, label="build of w16.py", read_peak=lambda: 0, abort=lambda code: self.fail("aborted"))
        with redirect_stderr(err):
            self.assertFalse(guard.check())
        self.assertEqual("", err.getvalue())

    def test_ru_maxrss_units_per_platform(self) -> None:
        """(f) Darwin is the exception, not "is a BSD"."""
        self.assertEqual(4096, memory_guard._scale_ru_maxrss(4096, "darwin"))
        self.assertEqual(4096 * 1024, memory_guard._scale_ru_maxrss(4096, "linux"))
        self.assertEqual(4096 * 1024, memory_guard._scale_ru_maxrss(4096, "freebsd"))

    def test_an_inactive_guard_says_so_once(self) -> None:
        """(e2) Fail-open must not be silent: a guard whose counter reads 0 is
        installed and inert, and looks exactly like a healthy small build."""
        err = io.StringIO()
        guard = MemoryGuard(8 * GB, label="build of w16.py", read_peak=lambda: 0, abort=lambda code: self.fail("aborted"))
        with redirect_stderr(err):
            with guard:
                pass
        self.assertIn("guard is INACTIVE", err.getvalue())
        self.assertIn("8.0 GB", err.getvalue())

        quiet = io.StringIO()
        measured = MemoryGuard(8 * GB, label="x", read_peak=lambda: GB, abort=lambda code: self.fail("aborted"))
        with redirect_stderr(quiet):
            with measured:
                pass
        self.assertEqual("", quiet.getvalue())

    def test_a_live_process_reports_a_believable_peak(self) -> None:
        """(g) THE TRIPWIRE. Unconditional and never skipped: on the Windows
        runner this is the only assertion that executes the Windows branch, and
        it is what catches a fail-open-swallowed breakage, the wrong units, or a
        field read from the wrong offset."""
        peak = peak_rss_bytes()
        self.assertGreater(peak, 8 * 1024**2, f"peak rss {peak} -- unmeasured, or the wrong units")
        self.assertLess(peak, 1024**4, f"peak rss {peak} -- a unit test does not use a terabyte")

    def test_an_unmeasured_peak_still_renders_on_a_stage_line(self) -> None:
        """(h) Fail-open means stage lines print `0.0 GB`, which the pin below
        (and the verbose-stage-line test) still match."""
        self.assertEqual("0.0 GB", format_gb(0))


class _FakeKernel32:
    """A stand-in for the loaded kernel32. Callable, because the reader loads it.

    The reader passes ``ctypes.pointer(counters)``, not ``byref``, so a plain
    Python function can write through the pointer -- the same shape as the fake
    ``msvcrt`` in test_coordination_lock."""

    def __init__(self, get_current_process, get_process_memory_info) -> None:
        self.GetCurrentProcess = get_current_process
        self.K32GetProcessMemoryInfo = get_process_memory_info

    def __call__(self) -> "_FakeKernel32":
        return self


class _NoExports:
    """A library that loaded but has no K32GetProcessMemoryInfo."""

    def __getattr__(self, name: str):
        raise AttributeError(name)



if __name__ == "__main__":
    unittest.main()
