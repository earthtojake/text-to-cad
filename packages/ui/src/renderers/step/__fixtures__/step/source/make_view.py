"""Build the fixture's model and write everything the viewer is served for it.

``hinge_block.py`` is built in a scratch directory with a store of its own, as a
person builds it, and what that build leaves is copied here: the view descriptor
(``assembly.json``, as ``descriptor_for_view`` serves it for the saved
document's tree), the document-bound sidecar (``hinge_block.step.json``),
cadgen's articulation of its kinematics (``hinge_block.articulation.json``,
``cadgen.articulation.step_articulation``), each component's part -- its
display mesh (``components/<cid>.glb``) and its selector table
(``components/<cid>.selectors.json``) -- read from the store under the part's key,
and each of its faces' exact area and centroid as cadgen measures them when a
view asks (``components/<cid>.measures.json``, ``parts.measure_face``).
Every id in them is minted by the build: the occurrences' tokens from the tree,
the elements' names from their lineage.

Run from the repository root with the repo's Python whenever the view schema,
the sidecar schema, the mesher, the selector table, the part key or the model
moves:

    .venv/bin/python packages/ui/src/renderers/step/__fixtures__/step/source/make_view.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1]
MODEL = Path(__file__).resolve().parent / "hinge_block.py"


def main() -> None:
    scratch = Path(tempfile.mkdtemp(prefix="step-fixture-"))
    try:
        (scratch / "src").mkdir()
        shutil.copy(MODEL, scratch / "src" / MODEL.name)
        environment = {**os.environ, "CADGEN_CACHE_DIR": str(scratch / "cache"), "CADGEN_DAEMON": "0"}
        subprocess.run([sys.executable, "src/hinge_block.py"], cwd=scratch, env=environment, check=True)
        os.environ["CADGEN_CACHE_DIR"] = environment["CADGEN_CACHE_DIR"]

        from cadgen._internal.selector_table import read_selector_table
        from cadgen._internal.source_sidecar import read_source_sidecar
        from cadgen.articulation import step_articulation
        from cadgen.store import parts
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.view import descriptor_for_view

        document = scratch / "STEP" / "hinge_block.step"
        document_hash = hashlib.sha256(document.read_bytes()).hexdigest()
        tree = document_entry_for_hash(document_hash)["tree"]
        view = descriptor_for_view(tree, document_hash=document_hash)
        if view is None:
            raise SystemExit("the build left no view of the document's tree")
        sidecar = read_source_sidecar(document, document_hash=document_hash) or {}
        articulation = step_articulation(view, sidecar.get("kinematics"))

        (FIXTURE / "assembly.json").write_text(json.dumps(view), encoding="utf-8")
        shutil.copy(scratch / "STEP" / "hinge_block.step.json", FIXTURE / "hinge_block.step.json")
        (FIXTURE / "hinge_block.articulation.json").write_text(json.dumps(articulation, sort_keys=True), encoding="utf-8")
        components = FIXTURE / "components"
        shutil.rmtree(components, ignore_errors=True)
        components.mkdir()
        for cid, component in view["components"].items():
            for role, suffix in (("glb", ".glb"), ("selectors", ".selectors.json")):
                payload = parts.read(component["part"], role)
                if payload is None:
                    raise SystemExit(f"{cid}: the build left no {role} for its part")
                (components / f"{cid}{suffix}").write_bytes(payload + (b"\n" if role == "selectors" else b""))
                print(cid, role, len(payload), "bytes")
            count = read_selector_table(parts.read(component["part"], "selectors"))["stats"]["faceCount"]
            measures = [{"face": face, **parts.measure_face(tree, cid, face)} for face in range(1, count + 1)]
            (components / f"{cid}.measures.json").write_text(json.dumps(measures) + "\n", encoding="utf-8")
            print(cid, "measures", count, "faces")
        print("documentHash", document_hash, "tree", tree)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
