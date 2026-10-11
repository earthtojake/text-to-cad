"""PROBE (do not merge): what console does a daemon's worker get on Windows?"""

import json
import os
import subprocess
import sys
import textwrap
import unittest

REPORT = textwrap.dedent(r"""
    import ctypes, json, os, sys
    k = ctypes.windll.kernel32
    buf = (ctypes.c_uint32 * 16)()
    print(json.dumps({"pid": os.getpid(), "hwnd": k.GetConsoleWindow(), "console_procs": k.GetConsoleProcessList(buf, 16)}), flush=True)
    sys.stdin.read()
""")

PARENT = textwrap.dedent(r"""
    import ctypes, json, subprocess, sys, time
    child_flags = int(sys.argv[1]); close = sys.argv[2] == "close"; report = sys.argv[3]
    k = ctypes.windll.kernel32
    buf = (ctypes.c_uint32 * 16)()
    me = {"hwnd": k.GetConsoleWindow(), "console_procs": k.GetConsoleProcessList(buf, 16)}
    child = subprocess.Popen([sys.executable, "-c", report], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             text=True, creationflags=child_flags)
    seen = json.loads(child.stdout.readline())
    if close and seen["hwnd"]:
        u = ctypes.windll.user32
        u.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
        res = ctypes.c_size_t()
        me["visible"] = u.IsWindowVisible(ctypes.c_void_p(seen["hwnd"]))
        me["sc_close"] = u.SendMessageTimeoutW(seen["hwnd"], 0x0112, 0xF060, 0, 0x0002, 5000, ctypes.byref(res))
        me["sc_close_err"] = k.GetLastError()
        try:
            code = child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            me["wm_close"] = u.SendMessageTimeoutW(seen["hwnd"], 0x0010, 0, 0, 0x0002, 5000, ctypes.byref(res))
            me["wm_close_err"] = k.GetLastError()
        try:
            code = child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            code = "still running"
    else:
        child.stdin.close()
        code = child.wait(timeout=20)
    print(json.dumps({"parent": me, "child": seen, "child_exit": code if isinstance(code, str) else hex(code & 0xFFFFFFFF)}), flush=True)
""")


@unittest.skipUnless(os.name == "nt", "probe")
class Probe(unittest.TestCase):
    def test_probe(self):
        import tempfile

        DP, NG, NW = subprocess.DETACHED_PROCESS, subprocess.CREATE_NEW_PROCESS_GROUP, subprocess.CREATE_NO_WINDOW
        rows = []
        for name, parent_flags, child_flags, close in [
            ("daemon DETACHED, worker plain", DP | NG, 0, False),
            ("daemon DETACHED, worker plain, WM_CLOSE its window", DP | NG, 0, True),
            ("daemon DETACHED, worker CREATE_NO_WINDOW", DP | NG, NW, False),
            ("daemon DETACHED, worker CREATE_NO_WINDOW, WM_CLOSE", DP | NG, NW, True),
            ("daemon CREATE_NO_WINDOW, worker plain", NW | NG, 0, False),
            ("daemon CREATE_NO_WINDOW, worker plain, WM_CLOSE", NW | NG, 0, True),
        ]:
            with tempfile.TemporaryDirectory() as tmp:
                log = os.path.join(tmp, "out.txt")
                with open(log, "wb") as out:
                    p = subprocess.Popen([sys.executable, "-c", PARENT, str(child_flags), "close" if close else "-", REPORT],
                                         stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                         cwd=tmp, creationflags=parent_flags)
                    p.wait(timeout=60)
                with open(log, encoding="utf-8", errors="replace") as fh:
                    rows.append(f"{name}: parent_exit={p.returncode} {fh.read().strip()}")
        self.fail("PROBE EVIDENCE\n" + "\n".join(rows))


if __name__ == "__main__":
    unittest.main()
