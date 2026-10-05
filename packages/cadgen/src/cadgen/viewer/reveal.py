"""Reveal a file, named by its absolute path, in the local operating system's file manager."""
import shutil
import subprocess
import sys
from pathlib import Path

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
        subprocess.Popen(["explorer.exe", f"/select,{target}"], close_fds=True)
    else:
        # FileManager1 selects the item when supported; otherwise open its folder.
        bus = shutil.which("dbus-send")
        if bus:
            try:
                subprocess.run([bus, "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
                    "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{target.as_uri()}", "string:"], check=True, capture_output=True, timeout=10)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        subprocess.run(["xdg-open", str(target if target.is_dir() else target.parent)],
            check=True, capture_output=True, timeout=10)
