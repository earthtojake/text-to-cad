"""Reveal a file, named by its absolute path, in the local operating system's file manager."""
import os
import subprocess
import sys
from pathlib import Path

from cadgen.engine import executables

from .backend import absolute_path


def reveal_path(path) -> None:
    """Show ``path`` selected in Finder, Explorer or the desktop's file manager.

    ``ValueError`` for a ref that is not an absolute path, ``FileNotFoundError`` when nothing is
    there. Never a shell: each platform's command takes the path as one argument.
    """
    target = Path(absolute_path(path)).resolve(strict=True)
    if not (target.is_file() or target.is_dir()):
        raise ValueError("Only files and directories can be revealed")
    if sys.platform == "darwin":
        subprocess.run(["/usr/bin/open", "-R", str(target)], check=True, capture_output=True, timeout=10)
    elif sys.platform == "win32":
        if "," in str(target):
            # Explorer reads its command line as comma-separated switches, so a name with a comma
            # would be read as more than one: its folder is opened by the shell instead, which takes
            # the path whole.
            os.startfile(str(target if target.is_dir() else target.parent))  # type: ignore[attr-defined]
            return
        # Windows' own Explorer, by its path: never an explorer.exe in the working folder.
        explorer = Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows") / "explorer.exe"
        subprocess.Popen([str(explorer), f"/select,{target}"], close_fds=True)
    else:
        # FileManager1 selects the item when supported; otherwise open its folder. Each helper by
        # its absolute path (``executables.find``), never a PATH entry relative to the working folder.
        bus = executables.find("dbus-send")
        if bus:
            try:
                subprocess.run([bus, "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
                    "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{target.as_uri()}", "string:"], check=True, capture_output=True, timeout=10)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        opener = executables.find("xdg-open")
        if opener is None:
            raise FileNotFoundError("xdg-open is not installed")
        subprocess.run([opener, str(target if target.is_dir() else target.parent)],
            check=True, capture_output=True, timeout=10)
