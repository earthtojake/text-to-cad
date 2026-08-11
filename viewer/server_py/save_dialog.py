"""Native OS Save-As dialog (subprocess), ported from saveAsDialog.mjs.

Returns exactly one of: {"path": abs}, {"cancelled": True}, {"unsupported": True}.
Honors VIEWER_SAVE_DIALOG_FORCE_PATH (value "__cancel__" -> cancelled, else
forced path) and VIEWER_DISABLE_NATIVE_SAVE_DIALOG=1 (-> unsupported). The dialog
itself stays an OS subprocess (osascript / zenity|kdialog / PowerShell) — there
is no Python equivalent.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _run_capture(command, args):
    try:
        proc = subprocess.run([command, *args], capture_output=True, text=True)
    except OSError as exc:
        return {"spawnError": exc}
    return {"code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}


def _pick_darwin(prompt, suggested_name, default_dir):
    script = [
        "on run argv",
        "set thePrompt to item 1 of argv",
        "set theName to item 2 of argv",
        "set theDir to item 3 of argv",
        'if theDir is not "" then',
        "set chosen to (choose file name with prompt thePrompt default name theName default location (POSIX file theDir))",
        "else",
        "set chosen to (choose file name with prompt thePrompt default name theName)",
        "end if",
        "return POSIX path of chosen",
        "end run",
    ]
    args = []
    for line in script:
        args += ["-e", line]
    args += [prompt, suggested_name, default_dir or ""]
    res = _run_capture("osascript", args)
    if res.get("spawnError"):
        return {"unsupported": True}
    if res.get("code") == 0:
        chosen = res["stdout"].strip()
        return {"path": chosen} if chosen else {"cancelled": True}
    return {"cancelled": True, "message": res.get("stderr", "").strip()}


def _pick_linux(suggested_name, default_dir):
    start_path = os.path.join(default_dir, suggested_name) if default_dir else suggested_name
    zenity = _run_capture("zenity", ["--file-selection", "--save", "--confirm-overwrite", f"--filename={start_path}"])
    if not zenity.get("spawnError"):
        if zenity.get("code") == 0:
            chosen = zenity["stdout"].strip()
            return {"path": chosen} if chosen else {"cancelled": True}
        return {"cancelled": True}
    kdialog = _run_capture("kdialog", ["--getsavefilename", start_path])
    if not kdialog.get("spawnError"):
        if kdialog.get("code") == 0:
            chosen = kdialog["stdout"].strip()
            return {"path": chosen} if chosen else {"cancelled": True}
        return {"cancelled": True}
    return {"unsupported": True}


def _pick_windows(suggested_name, default_dir):
    def quote(value):
        return str(value).replace("'", "''")
    parts = [
        "Add-Type -AssemblyName System.Windows.Forms;",
        "$dialog = New-Object System.Windows.Forms.SaveFileDialog;",
        f"$dialog.InitialDirectory = '{quote(default_dir)}';" if default_dir else "",
        f"$dialog.FileName = '{quote(suggested_name)}';",
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($dialog.FileName) }",
    ]
    command = " ".join(p for p in parts if p)
    res = _run_capture("powershell", ["-NoProfile", "-STA", "-Command", command])
    if res.get("spawnError"):
        return {"unsupported": True}
    if res.get("code") == 0:
        chosen = res["stdout"].strip()
        return {"path": chosen} if chosen else {"cancelled": True}
    return {"cancelled": True}


def pick_save_destination(suggested_name="export", default_dir="", prompt="Export model as:"):
    forced = str(os.environ.get("VIEWER_SAVE_DIALOG_FORCE_PATH") or "").strip()
    if forced:
        return {"cancelled": True} if forced == "__cancel__" else {"path": forced}
    if os.environ.get("VIEWER_DISABLE_NATIVE_SAVE_DIALOG") == "1":
        return {"unsupported": True}
    safe_dir = default_dir if default_dir and os.path.exists(default_dir) else ""
    try:
        if sys.platform == "darwin":
            return _pick_darwin(prompt, suggested_name, safe_dir)
        if sys.platform.startswith("win"):
            return _pick_windows(suggested_name, safe_dir)
        return _pick_linux(suggested_name, safe_dir)
    except Exception:  # noqa: BLE001
        return {"unsupported": True}
