"""Write the robot renderer's browser-test fixtures: what ``GET /__cad/robot`` answers for each
description here, and the primitive meshes cadgen makes for them.

The descriptions are committed as they are (``arm.urdf``, the ``arm.srdf`` paired with it,
``swing.sdf``, ``chain.urdf``, and two cadgen refuses: ``gone.urdf``, whose link mesh is
missing, and ``lonely.srdf``, with no URDF beside it). This script reads each one with
cadgen (``cadgen.robot_payload``) and writes:

* ``<name>.robot.json``: the payload, with every visual's mesh named by the URL the browser
  test's server answers for it (``/meshes/<file>`` for a link mesh file, ``/primitives/<hash>.glb``
  for a shape cadgen meshed);
* ``primitives/<hash>.glb``: those meshes, as the store holds them;
* ``refusals.json``: the sentence cadgen refuses each refused description with, which the
  test's server answers as a 400, as the viewer's route does.

So the browser test needs neither Python nor a store, and the Python suite holds these files
current (``tests/python/packages/cadgen/test_robot_payload.py``). Regenerate after changing a
description or the payload shape, from the repository root:

    .venv/bin/python packages/ui/src/renderers/robot/__fixtures__/make_fixtures.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESCRIPTIONS = ("arm.urdf", "arm.srdf", "swing.sdf", "chain.urdf", "gone.urdf", "lonely.srdf")


def fixture_payloads(cache_dir: Path) -> tuple[dict[str, dict], dict[str, str], dict[str, bytes]]:
    """``(payloads by name, refusals by name, primitive GLB bytes by hash)`` for the descriptions here,
    located as the browser test serves them. Reads through a store at ``cache_dir``."""
    os.environ["CADGEN_CACHE_DIR"] = str(cache_dir)
    from cadgen.robot_payload import RobotReadError, locate_robot_payload, read_robot_description
    from cadgen.store.objects import read_verified_object

    payloads: dict[str, dict] = {}
    refusals: dict[str, str] = {}
    meshes: dict[str, bytes] = {}
    for name in DESCRIPTIONS:
        # cadgen names a description relative to the working directory: read from this folder, so a
        # refusal says `gone.urdf` wherever this runs, and the folder it names is this one.
        previous = Path.cwd()
        os.chdir(HERE)
        try:
            payload = read_robot_description(HERE / name)
        except RobotReadError as exc:
            refusals[name] = str(exc).replace(str(HERE), "/models")
            continue
        finally:
            os.chdir(previous)
        for visual in payload["visuals"]:
            digest = visual["mesh"].get("object")
            if digest and digest not in meshes:
                meshes[digest] = read_verified_object(digest)
        payloads[name] = locate_robot_payload(
            payload,
            file_url=lambda path: "/" + Path(path).resolve().relative_to(HERE).as_posix(),
            object_url=lambda digest: f"/primitives/{digest}.glb",
        )
        for link in payloads[name]["links"]:
            for fact in link["visuals"] + link["collisions"]:
                if fact.get("path"):
                    fact["path"] = "/models/" + Path(fact["path"]).resolve().relative_to(HERE).as_posix()
    return payloads, refusals, meshes


def main() -> None:
    sys.path.insert(0, str(HERE.parents[5] / "packages" / "cadgen" / "src"))
    with tempfile.TemporaryDirectory(prefix="robot-fixtures-") as cache:
        payloads, refusals, meshes = fixture_payloads(Path(cache))
    primitives = HERE / "primitives"
    shutil.rmtree(primitives, ignore_errors=True)
    primitives.mkdir()
    for digest, data in meshes.items():
        (primitives / f"{digest}.glb").write_bytes(data)
    for name, payload in payloads.items():
        (HERE / f"{Path(name).stem}.{Path(name).suffix[1:]}.robot.json").write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    (HERE / "refusals.json").write_text(json.dumps(refusals, indent=1) + "\n", encoding="utf-8")
    for name, payload in payloads.items():
        print(f"{name}: {len(payload['articulation']['controls'])} controls, {len(payload['visuals'])} visuals")
    print(f"{len(meshes)} primitive meshes, {len(refusals)} refusals")


if __name__ == "__main__":
    main()
