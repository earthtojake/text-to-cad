# -*- coding: utf-8 -*-
"""text-to-cad QwenPaw plugin entry point.

Registers the repository's CAD, robotics, and fabrication skills with every
QwenPaw workspace, plus a ``/cad-setup`` preflight command that reports the
cadgen runtime state (presence, per-skill pin, viewer/daemon) without the
agent having to read a skill first.

The plugin ships no tools of its own: the skills are instructions over the
``cadgen`` distribution, which each skill's ``requirements.txt`` names and the
agent installs on first use.

This module must stay importable without QwenPaw installed (stdlib only at
module scope; qwenpaw/agentscope imports sit inside functions): QwenPaw
validates a plugin by importing it and requiring a ``plugin`` instance, and
this repository's policy test (``tests/python/global/test_qwenpaw_plugin.py``)
runs the same import on a checkout that has no ``qwenpaw`` package.

Skills directory resolution
---------------------------

The QwenPaw loader installs a plugin by copying THIS directory
(``.qwenpaw-plugin/``) into ``~/.qwenpaw/plugins/<id>/``, so nothing outside it
survives the install. Rather than commit a second copy of ``skills/`` to the
repository, the plugin resolves a tree that already exists, in this order:

1. ``plugins.cad.skills_dir`` in QwenPaw's own config, handed to the plugin as
   ``api.config``. Point it at a checkout's ``skills/`` and the install follows
   that tree live, the way the Claude, Codex and Skills-CLI surfaces do.
2. ``<plugin_dir>/skills`` -- a copy generated on demand with the rsync recipe
   in this directory's README, for an install with no checkout to point at.
3. ``<plugin_dir>/../skills`` -- the sibling a checkout provides, so the plugin
   also works when it is run in place rather than installed.

A configured path that does not resolve is reported as an error and is NOT
silently replaced by a lower-priority candidate: an outdated path should be
loud, not shadowed by a stale copy. ``/cad-setup`` prints which tree won.

If nothing resolves, the plugin logs a clear error and skips skill registration
instead of raising: a broken path must degrade to "plugin without skills", not
fail the QwenPaw app startup.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only, never evaluated
    from qwenpaw.plugins.api import PluginApi

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).resolve().parent

#: QwenPaw hands each plugin the ``plugins.<id>`` section of its own config as
#: ``api.config``; this key names a skills tree to provision from, which beats
#: any copy and is what lets an install follow one source of truth.
CONFIG_SKILLS_KEY = "skills_dir"

#: What the last ``register()`` resolved, reported by /cad-setup. A plugin with
#: no reachable skills tree still registers that command, because it is the
#: thing the user runs once skills are missing.
_SKILLS_STATE: dict[str, str] = {"resolved": "not registered", "path": ""}

#: Skills the fabrication/handoff boundary applies to. These are enabled by
#: default everywhere else in this repo; under QwenPaw they start disabled and
#: the user opts in per workspace, because they reach real machines: starting
#: prints on a LAN printer (bambu-labs) and uploading parts for manufacture
#: (sendcutsend). Every other skill is analysis, authoring, or local-only.
FABRICATION_SKILLS = ("bambu-labs", "sendcutsend")

#: Marker written into a workspace the first time the plugin provisions it.
#: Keeps the once-only disable semantics: after the first provision the user's
#: own enable/disable choices win, on every later startup.
_PROVISION_MARKER = ".text-to-cad-provisioned"

#: One-line pointer injected into the system prompt after the workspace
#: section. Short on purpose: it costs tokens on every turn.
_PROMPT_HINT = (
    "text-to-cad skills (CAD/URDF/SDF/DXF/G-code) are installed; "
    "run /cad-setup once to verify the cadgen runtime before first use."
)


def _is_skills_tree(candidate: Path) -> bool:
    """True when *candidate* holds this library's skills (``cad`` is the canary)."""
    return candidate.is_dir() and (candidate / "cad" / "SKILL.md").is_file()


def _resolve_skills_dir(config: dict | None = None) -> Path | None:
    """Return the skills directory the plugin will provision from, or None.

    Records which candidate won in ``_SKILLS_STATE`` so ``/cad-setup`` can
    report it: the caller has no way to tell a configured tree from a copy.

    A configured path that does not resolve is reported and returns None rather
    than falling through: a stale pointer is a misconfiguration to fix, and a
    silent fallback to a copy would let it serve skills nobody updated.
    """
    configured = (config or {}).get(CONFIG_SKILLS_KEY)
    if isinstance(configured, str) and configured.strip():
        candidate = Path(configured.strip()).expanduser()
        if _is_skills_tree(candidate):
            _SKILLS_STATE.update(resolved="configured", path=str(candidate))
            return candidate
        logger.error(
            "text-to-cad: %s=%s is not a skills tree (no cad/SKILL.md inside). "
            "Point it at a text-to-cad checkout's skills/ directory, or drop "
            "the key to fall back to a bundled copy.",
            CONFIG_SKILLS_KEY,
            candidate,
        )
        _SKILLS_STATE.update(
            resolved="configured path invalid", path=str(candidate)
        )
        return None

    for label, candidate in (
        ("bundled copy", PLUGIN_DIR / "skills"),
        ("checkout sibling", PLUGIN_DIR.parent / "skills"),
    ):
        if _is_skills_tree(candidate):
            _SKILLS_STATE.update(resolved=label, path=str(candidate))
            return candidate

    _SKILLS_STATE.update(resolved="nothing reachable", path="")
    return None


def _workspace_dirs() -> list[Path]:
    """Every configured workspace directory (empty list when unavailable)."""
    try:
        from qwenpaw.agents.skill_system.registry import list_workspaces

        return [Path(w["workspace_dir"]) for w in list_workspaces()]
    except Exception as exc:  # noqa: BLE001 - provisioning is best-effort
        logger.warning("text-to-cad: cannot list workspaces: %s", exc)
        return []


def _apply_fabrication_gate(workspace_dir: Path, skills_dir: Path) -> None:
    """Disable the fabrication skills the first time a workspace is provisioned.

    Runs after the host's install hook (priority 85 > 80). The marker file
    makes it exactly-once per provision cycle: on later startups the user's
    own enable/disable choices are left alone. The marker is removed again
    by the plugin's uninstall hook, so a reinstall treats the workspace as
    freshly provisioned and re-applies the gate (the uninstall removes the
    plugin-sourced skills; without this the reinstall would re-enable them
    and the stale marker would keep the gate off).
    """
    marker = workspace_dir / _PROVISION_MARKER
    if marker.exists():
        return
    try:
        from qwenpaw.agents.skill_system.store import (
            default_workspace_manifest,
            get_workspace_skill_manifest_path,
            mutate_json,
        )

        installed = {
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").is_file()
        }
        gated = sorted(installed & set(FABRICATION_SKILLS))
        if not gated:
            marker.touch()
            return

        def _disable(payload: dict) -> dict:
            skills = payload.setdefault("skills", {})
            for name in gated:
                entry = skills.get(name)
                if entry is None:
                    continue
                if str(entry.get("source", "")).startswith("plugin:cad"):
                    entry["enabled"] = False
            return payload

        mutate_json(
            get_workspace_skill_manifest_path(workspace_dir),
            default_workspace_manifest(),
            _disable,
        )
        marker.touch()
        logger.info(
            "text-to-cad: fabrication skills left disabled in %s: %s "
            "(enable per workspace when the user opts in)",
            workspace_dir.name,
            ", ".join(gated),
        )
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning(
            "text-to-cad: fabrication gate skipped for %s: %s",
            workspace_dir.name,
            exc,
        )


def _run_cadgen_doctor(skill_dir: Path) -> tuple[str, str]:
    """Run ``cadgen doctor <skill_dir>``; return (status, detail).

    status is one of "ok" (exit 0), "mismatch" (exit 3), "missing"
    (no cadgen on PATH) or "error".
    """
    import shutil
    import subprocess

    exe = shutil.which("cadgen")
    if exe is None:
        return (
            "missing",
            "the cadgen distribution is not installed — "
            "`python -m pip install -r <skill>/requirements.txt` (Python >= 3.11)",
        )
    try:
        result = subprocess.run(
            [exe, "doctor", str(skill_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return ("error", "cadgen doctor timed out after 120s")
    except OSError as exc:
        return ("error", f"cadgen doctor failed to run: {exc}")

    tail = (result.stdout or result.stderr or "").strip().splitlines()
    detail = tail[-1] if tail else ""
    if result.returncode == 0:
        return ("ok", detail)
    if result.returncode == 3:
        return ("mismatch", detail)
    return ("error", detail or f"cadgen doctor exited {result.returncode}")


async def _cad_setup_handler(ctx, args: str):
    """/cad-setup — report the cadgen runtime state for this workspace.

    Checks, in order: the cadgen binary, each cadgen-pinned skill's
    requirements pin (via ``cadgen doctor``), and the viewer/daemon
    lifecycle so stray background processes are visible. Returns a Msg;
    never raises into the dispatcher.
    """
    from agentscope.message import Msg, TextBlock

    workspace_dir = getattr(ctx, "workspace_dir", None)
    lines: list[str] = ["text-to-cad runtime check:"]

    if workspace_dir is None:
        lines.append("  workspace: unknown (no workspace_dir on context)")
        skills_root: Path | None = None
    else:
        workspace_dir = Path(workspace_dir)
        skills_root = workspace_dir / "skills"
        lines.append(f"  workspace: {workspace_dir}")

    source = _SKILLS_STATE["resolved"]
    if _SKILLS_STATE["path"]:
        source = f"{source} ({_SKILLS_STATE['path']})"
    lines.append(f"  skills source: {source}")

    # 1. cadgen binary presence + version
    import shutil

    exe = shutil.which("cadgen")
    if exe is None:
        lines.append(
            "  cadgen: NOT INSTALLED — install any pinned skill's "
            "requirements.txt to get it (Python >= 3.11)"
        )
    else:
        try:
            import subprocess

            version = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
        except Exception as exc:  # noqa: BLE001
            version = f"unreadable ({exc})"
        lines.append(f"  cadgen: {version} ({exe})")

    # 2. Per-skill pin check for every cadgen-pinned skill in the workspace
    if skills_root is not None and skills_root.is_dir():
        for skill_dir in sorted(skills_root.iterdir()):
            req = skill_dir / "requirements.txt"
            if not (skill_dir / "SKILL.md").is_file() or not req.is_file():
                continue
            if not any(
                line.strip().startswith("cadgen")
                for line in req.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ):
                continue
            status, detail = _run_cadgen_doctor(skill_dir)
            mark = {"ok": "OK", "mismatch": "MISMATCH", "missing": "MISSING", "error": "ERROR"}[status]
            lines.append(f"  {skill_dir.name}: {mark} — {detail}")
    else:
        lines.append("  skills: no skills/ directory in this workspace")

    # 3. Background lifecycle visibility (viewer instances, warm daemon)
    if exe is not None:
        import subprocess

        for label, argv in (
            ("viewer", [exe, "viewer", "list", "--json"]),
            ("daemon", [exe, "daemon", "status"]),
        ):
            try:
                result = subprocess.run(
                    argv, capture_output=True, text=True, timeout=30
                )
                out = (result.stdout or "").strip()
                lines.append(f"  {label}: {out.splitlines()[0] if out else 'none'}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  {label}: status unavailable ({exc})")

    return Msg(
        name="system",
        role="assistant",
        content=[TextBlock(type="text", text="\n".join(lines))],
    )


class TextToCadPlugin:
    """Installs the packaged skills into every QwenPaw workspace."""

    def register(self, api: PluginApi) -> None:
        """Register skills, the preflight command, and the setup hint.

        Args:
            api: PluginApi instance provided by the QwenPaw loader.
        """
        skills_dir = _resolve_skills_dir(getattr(api, "config", None))
        if skills_dir is None:
            logger.error(
                "text-to-cad: no skills/ tree reachable from %s — skill "
                "registration skipped. Either set %s in this plugin's config "
                "to a text-to-cad checkout's skills/ directory, or generate "
                "the bundled copy with the rsync recipe in .qwenpaw-plugin/"
                "README.md. Run /cad-setup to see what was looked for.",
                PLUGIN_DIR,
                CONFIG_SKILLS_KEY,
            )
        else:
            logger.info("Registering text-to-cad skills (%s)...", skills_dir)
            api.register_skill_provider(
                skills_dir=skills_dir,
                enabled_by_default=True,
                channels=["all"],
            )

            def _gate(workspace_info: dict) -> None:
                workspace_dir = Path(workspace_info.get("workspace_dir", ""))
                if workspace_dir.is_dir():
                    _apply_fabrication_gate(workspace_dir, skills_dir)

            api.register_startup_hook(
                hook_name="text_to_cad_fabrication_gate",
                callback=lambda: [
                    _gate({"workspace_dir": str(w)}) for w in _workspace_dirs()
                ],
                priority=85,  # after the host's install hook (priority 80)
            )
            api.register_workspace_created_hook(
                hook_name="text_to_cad_fabrication_gate",
                callback=_gate,
                priority=85,
            )

            def _clear_markers(plugin_id: str, delete_files: bool = False) -> None:
                """Remove the provision markers so a reinstall re-gates.

                The host uninstall deletes the plugin-sourced skills but not
                this plugin's marker files; without this hook a reinstall
                would find the stale marker, skip the gate, and leave the
                fabrication skills re-enabled by the fresh install.
                """
                _ = delete_files  # part of the uninstall hook contract
                for workspace_dir in _workspace_dirs():
                    try:
                        (workspace_dir / _PROVISION_MARKER).unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning(
                            "text-to-cad: could not clear provision marker "
                            "in %s: %s",
                            workspace_dir.name,
                            exc,
                        )

            api.register_uninstall_hook(
                hook_name="text_to_cad_clear_provision_markers",
                callback=_clear_markers,
            )
            logger.info("✓ text-to-cad skills registered from %s", skills_dir)

        # /cad-setup preflight: the first-run failure mode for every skill is
        # "cadgen missing or pinned elsewhere"; the command surfaces that (and
        # any viewer/daemon strays) before the agent burns a turn on it.
        api.register_slash_command(
            name="cad-setup",
            handler=_cad_setup_handler,
            category="plugin",
            help_text=(
                "Verify the text-to-cad runtime: cadgen presence/version, "
                "per-skill cadgen pins, viewer and daemon status"
            ),
        )

        # One-line system-prompt hint so the agent knows the preflight exists
        # without reading any skill. Registered only when skills resolved; a
        # plugin without skills should not advertise them.
        if skills_dir is not None:
            api.register_prompt_section(
                name="text_to_cad_setup_hint",
                after="workspace",
                provider=lambda agent: _PROMPT_HINT,
            )

        logger.info("✓ text-to-cad plugin registered")


# Export plugin instance (required by the QwenPaw plugin loader).
plugin = TextToCadPlugin()
