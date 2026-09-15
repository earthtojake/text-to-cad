"""Resident-memory estimates and admission reservations, without CAD imports.

These are admission bounds, not an allocator sandbox: a native operation may
grow between measurements. Busy workers retain their reservation while waiting
for children. No function here reads or removes persistent cache entries.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

MIB = 1024 * 1024
DEFAULT_WORKER_BYTES = 2048 * MIB
DEFAULT_COMPONENT_BYTES = 384 * MIB


def _megabytes(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        amount = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a nonnegative whole number of MiB") from None
    if amount < 0:
        raise ValueError(f"{name} must be a nonnegative whole number of MiB")
    return amount * MIB


def physical_memory_bytes() -> int:
    """Physical/cgroup ceiling when discoverable; zero means unknown."""
    total = 0
    try:
        total = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, AttributeError):
        if sys.platform == "darwin":
            try:
                total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        elif os.name == "nt":
            try:
                import ctypes

                class Status(ctypes.Structure):
                    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                        (name, ctypes.c_ulonglong) for name in (
                            "physical", "available", "pagefile", "available_pagefile",
                            "virtual", "available_virtual", "extended",
                        )
                    ]

                status = Status()
                status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    total = int(status.physical)
            except (OSError, AttributeError):
                pass
    if sys.platform.startswith("linux"):
        # A container's host RAM is not its usable memory envelope.
        for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
            try:
                ceiling = int(Path(path).read_text().strip())
                if 0 < ceiling < (1 << 60):
                    total = min(total, ceiling) if total else ceiling
            except (OSError, ValueError):
                pass
    return max(0, total)


@dataclass(frozen=True)
class MemoryPolicy:
    limit_bytes: int
    worker_bytes: int = DEFAULT_WORKER_BYTES
    dependency_bytes: int = DEFAULT_WORKER_BYTES
    component_bytes: int = DEFAULT_COMPONENT_BYTES

    @classmethod
    def from_environment(cls) -> "MemoryPolicy":
        # Leave 30% to the daemon, browser and other applications. An explicit
        # zero disables admission; unknown host capacity also leaves it off.
        limit = _megabytes("CADGEN_MEMORY_MB", physical_memory_bytes() * 7 // 10)
        default_worker = min(DEFAULT_WORKER_BYTES, max(256 * MIB, limit // 3)) if limit else DEFAULT_WORKER_BYTES
        worker = max(MIB, _megabytes("CADGEN_WORKER_MEMORY_MB", default_worker))
        dependency = _megabytes("CADGEN_DEPENDENCY_MEMORY_MB", min(worker, max(0, limit - worker)))
        component = max(MIB, _megabytes("CADGEN_COMPONENT_MEMORY_MB", DEFAULT_COMPONENT_BYTES))
        return cls(limit, worker, dependency, component)


# pid -> (parent pid, resident bytes). Keep short-lived sampling work out of
# repeated status/admission calls; no process arguments or user data are read.
_sample_guard = threading.Lock()
_sample_at = 0.0
_sample: dict[int, tuple[int, int]] = {}


def _read_processes() -> dict[int, tuple[int, int]]:
    if sys.platform.startswith("linux"):
        rows: dict[int, tuple[int, int]] = {}
        try:
            entries = Path("/proc").iterdir()
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                try:
                    values = {}
                    for line in (entry / "status").read_text().splitlines():
                        key, _, value = line.partition(":")
                        if key in ("PPid", "VmRSS"):
                            values[key] = int(value.split()[0])
                    rows[int(entry.name)] = (values.get("PPid", 0), values.get("VmRSS", 0) * 1024)
                except (OSError, ValueError, IndexError):
                    continue
        except OSError:
            pass
        return rows
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=2,
            stderr=subprocess.DEVNULL,
        )
        rows = {}
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 3:
                pid, parent, kib = map(int, fields)
                rows[pid] = (parent, kib * 1024)
        return rows
    except (OSError, ValueError, subprocess.SubprocessError):
        # Reservation accounting still works when process enumeration is not
        # available (notably Windows without ps); status reports missing RSS.
        return {}


def process_tree_bytes(pids: list[int], *, rows: Mapping[int, tuple[int, int]] | None = None) -> dict[int, int]:
    """RSS per worker including its extraction subprocesses, counted once."""
    if rows is None:
        global _sample_at, _sample
        with _sample_guard:
            now = time.monotonic()
            if now - _sample_at >= 0.05:
                _sample, _sample_at = _read_processes(), now
            rows = _sample
    roots = set(pids)
    totals = {pid: max(0, int(rows[pid][1])) for pid in roots if pid in rows}
    for pid, (parent, resident) in rows.items():
        if pid in roots:
            continue
        seen = {pid}
        while parent and parent not in seen:
            if parent in roots:
                totals[parent] = totals.get(parent, 0) + max(0, int(resident))
                break
            seen.add(parent)
            parent = rows.get(parent, (0, 0))[0]
    return totals


def component_worker_limit(requested: int) -> int:
    """Fit extraction subprocess reservations inside this worker's allowance.

    One means inline work (no extra interpreter). Overrides remain upper
    bounds; they cannot bypass configured memory admission.
    """
    policy = MemoryPolicy.from_environment()
    if not policy.limit_bytes or requested <= 1:
        return max(1, requested)
    resident = process_tree_bytes([os.getpid()]).get(os.getpid(), policy.worker_bytes // 2)
    available = max(0, policy.worker_bytes - resident)
    return max(1, min(requested, available // policy.component_bytes))
