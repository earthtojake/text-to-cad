"""A build has its parts' display data derived before it reports done; a view only reads.

A two-part model declaring an STL at the display tolerance, built in this process with the
daemon off (STORE.md §3, a build's parts are the build pool's to derive). The build process
itself measures and meshes nothing: its parts are one pool job's, run in a worker of their
own. With that job run here instead (``inline_artifacts``), so the mesher can be counted
and made to fail: the build meshes each part once and the STL is written from those
meshes; a list and a view of the saved STEP start no job; a part the store lost is derived
alone, by one job; and a no-op build of the model repairs a cleared store. A part no mesh
can be made of is a warning on the build, a part a snapshot and a list go on without, each
saying so in the build's words, and a declared STL's failure.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import threading
import traceback
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.inline_artifacts import inline_artifacts
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.tree_tokens import child_token, root_token  # noqa: E402
from cadgen.store.trees import IDENTITY_16  # noqa: E402

MODEL = """
from cadgen import step, stl
from cadgen import build123d as bd


@stl(out="../STL/pair.stl")
@step(out="../STEP/pair.step")
def pair():
    block = bd.Box(10, 10, 10)
    block.label = "block"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(3, 10)
    peg.label = "peg"
    return bd.Compound(children=[block, peg], label="pair")


if __name__ == "__main__":
    pair()
"""

NO_JOB = AssertionError("a view started a derivation job")
# The occurrences' tokens, minted from the tree the model returns: the root `pair`, and
# under it `block` at the origin and `peg` at x = 20 (a Cylinder is centred). The saved
# document mints the same, so the build, a snapshot and a list name them alike.
_ROOT = root_token("pair")
BLOCK_ID = child_token(_ROOT, "block", IDENTITY_16)
PEG_ID = child_token(_ROOT, "peg", [1, 0, 0, 20, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
# How every reader names the peg once its mesher has failed (``failing``): a build's warning,
# a snapshot's and a list's, an export's failure.
PEG_FAILED = f"#{PEG_ID} peg could not be meshed (MeshProductionError: ValueError: boom)"


def failing(*face_counts: int):
    """cadgen's mesher, raising instead for a part whose selector table has one of
    ``face_counts`` faces: the peg, a cylinder, has 3, and the block 6."""
    from cadgen._internal import tessellate

    real = tessellate.mesh_component

    def mesher(topods, table, face_colors, **options):
        if len(table["faces"]) in face_counts:
            raise ValueError("boom")
        return real(topods, table, face_colors, **options)

    return mesher


class BuildDerivesDisplayData(unittest.TestCase):
    def setUp(self) -> None:
        temporary = generated_cad_directory(prefix="build-display-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "src").mkdir()
        self.script = self.root / "src/pair.py"
        self.script.write_text(MODEL, encoding="utf-8")
        self.document = self.root / "STEP/pair.step"
        self.store = self.root / "store"
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON": "0"})
        patch.start()
        self.addCleanup(patch.stop)

    def build(self, mesher=None) -> tuple[str, int]:
        """Run the model in this process, its display jobs here too: its outcome word, and how
        many meshes OCCT made (by ``mesher`` when given). What it printed is ``self.output``,
        the jobs it asked for ``self.jobs``."""
        from cadgen._internal import tessellate
        from cadgen.cli._run_model import run_model_argv

        output = io.StringIO()
        with inline_artifacts() as jobs, \
                mock.patch.object(tessellate, "mesh_component", wraps=mesher or tessellate.mesh_component) as meshed, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_model_argv([str(self.script)])
        self.output = output.getvalue()
        self.jobs = [call.args[0] for call in jobs.call_args_list]
        self.assertEqual(code, 0, self.output)
        return self.output.strip().splitlines()[-1].split(" ", 1)[0], meshed.call_count

    def test_the_build_thread_measures_nothing_its_parts_are_one_pool_job(self) -> None:
        """Dispatched for real (with the daemon off, on a thread of the build's own process,
        as a pool job runs there), the display job is the only thing that measures or meshes
        the build's geometry: nothing on the build's thread calls OCCT's surface integrals
        outside the model's own code, nor the mesher -- and the parts are stored when it is
        done."""
        from OCP.BRepGProp import BRepGProp

        from cadgen._internal import tessellate
        from cadgen.cli._run_model import run_model_argv
        from cadgen.daemon import artifacts
        from cadgen.store import parts
        from cadgen.store.view import descriptor_for_view

        measured: list[str] = []
        real_integral, real_mesher = BRepGProp.SurfaceProperties_s, tessellate.mesh_component

        def on_the_job() -> bool:
            return threading.current_thread().name == "cadgen-artifact"

        def integral(*args, **kwargs):
            # The model's own code may measure (build123d does, making a plane); cadgen may not.
            stack = traceback.extract_stack()[:-1]
            if not on_the_job() and not any(Path(frame.filename).resolve() == self.script for frame in stack):
                measured.append(" < ".join(f"{Path(frame.filename).name}:{frame.name}" for frame in reversed(stack[-6:])))
            return real_integral(*args, **kwargs)

        def mesher(*args, **kwargs):
            if not on_the_job():
                raise AssertionError("meshed on the build's thread")
            return real_mesher(*args, **kwargs)

        output = io.StringIO()
        with mock.patch.object(BRepGProp, "SurfaceProperties_s", side_effect=integral), \
                mock.patch.object(tessellate, "mesh_component", side_effect=mesher), \
                mock.patch.object(artifacts, "submit_artifact", wraps=artifacts.submit_artifact) as submitted, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_model_argv([str(self.script)])
        self.assertEqual(code, 0, output.getvalue())
        self.assertEqual(measured, [])
        # The other pool jobs write the STEP from the result and verify it: no display data.
        [job] = [call.args[0] for call in submitted.call_args_list if call.args[0]["kind"] == "display"]
        self.assertEqual(len(job["cids"]), 2)
        view = descriptor_for_view(job["tree"], producer=job["producer"])
        self.assertTrue(all(parts.probe(entry["part"]) for entry in view["components"].values()), "the job stored them")

    def listing(self):
        from cadgen import step

        listed = step.snapshot(self.document, mode="list")
        self.assertTrue(listed.ok)
        return {row["name"]: row["triangleCount"] for row in listed.parts}

    def test_the_build_meshes_each_part_once_and_every_view_after_it_only_reads(self) -> None:
        from cadgen import stl

        self.assertEqual(self.build(), ("built", 2), "one display mesh a part; the STL is written from them")
        self.assertEqual([(job["kind"], len(job.get("cids") or ())) for job in self.jobs],
                         [("display", 2), ("export", 0), ("verify", 0)], "one display job for both")
        self.assertTrue((self.root / "STL/pair.stl").is_file())
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=NO_JOB), \
                mock.patch("cadgen.store.parts.derive", side_effect=NO_JOB):
            counts = self.listing()
            exported = stl.build(self.document, self.root / "again.stl", force=True)
        self.assertTrue(exported.ok)
        self.assertEqual(set(counts), {"block", "peg"})
        self.assertEqual(counts["block"], 12)

    def test_a_part_the_store_lost_is_derived_alone_by_one_job(self) -> None:
        from cadgen.store import parts

        self.build()
        expected = self.listing()
        [lost] = [key for key in (self.store / "index/part").iterdir()
                  if parts.probe(key.name)["glb"]["indexCount"] // 3 != 12]
        lost.unlink()
        with inline_artifacts() as jobs:
            self.assertEqual(self.listing(), expected)
        [job] = [call.args[0] for call in jobs.call_args_list]
        self.assertEqual((job["kind"], len(job["cids"])), ("display", 1))
        self.assertIsNotNone(parts.probe(lost.name), "the job stored the part again")

    def test_a_no_op_build_repairs_a_cleared_store(self) -> None:
        self.build()
        shutil.rmtree(self.store / "index/part")
        self.assertEqual(self.build(), ("current", 2))
        self.assertEqual(self.build(), ("current", 0))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=NO_JOB):
            self.assertEqual(set(self.listing()), {"block", "peg"})

    def test_a_no_op_build_after_a_kernel_upgrade_derives_under_this_runtime(self) -> None:
        """The document names the producer of the kernel it was built under, whose parts the
        store no longer holds. A no-op build derives them under this runtime's producer, says
        nothing about it, and re-attests the document, so views ask no worker for the old one."""
        from cadgen.store import parts

        self.build()
        [entry] = list((self.store / "index/document").iterdir())
        document = json.loads(entry.read_text(encoding="utf-8"))
        document["producer"] = {"build123d": "0.0.1", "ocp": "7.0.0", "cadqueryOcp": "7.0.0.0"}
        entry.write_text(json.dumps(document), encoding="utf-8")
        shutil.rmtree(self.store / "index/part")
        self.assertEqual(self.build(), ("current", 2))
        self.assertNotIn("warning", self.output)
        self.assertEqual(json.loads(entry.read_text(encoding="utf-8"))["producer"], parts.producer_identity())
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=NO_JOB):
            self.assertEqual(set(self.listing()), {"block", "peg"})

    def snapshot(self, mesher, *argv: str) -> tuple[int, list[str], list[str], int]:
        """``cadgen step snapshot`` of the saved document, run here with its display jobs under
        ``mesher``: the exit code, stdout's lines, stderr's warnings and failure, and how many
        display jobs it asked for."""
        from cadgen import cli
        from cadgen._internal import tessellate

        out, err = io.StringIO(), io.StringIO()
        with inline_artifacts() as jobs, mock.patch.object(tessellate, "mesh_component", wraps=mesher), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["step", "snapshot", str(self.document), *argv])
        said = [line for line in err.getvalue().splitlines()
                if line.startswith(("warning: ", "[cadgen step snapshot] FAILED: "))]
        displays = [call.args[0] for call in jobs.call_args_list if call.args[0]["kind"] == "display"]
        return code, out.getvalue().splitlines(), said, len(displays)

    def test_a_declared_mesh_export_of_a_part_that_cannot_be_meshed_fails_naming_both(self) -> None:
        """Every process meshes alike (the export's job runs here, under the same mesher): the
        STL cannot be written, so the build fails -- naming the file and the occurrence, never
        a component id and a worker's traceback -- and leaves no file."""
        from cadgen._internal import tessellate
        from cadgen.cli._run_model import run_model_argv

        output = io.StringIO()
        with inline_artifacts(), mock.patch.object(tessellate, "mesh_component", wraps=failing(3)), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_model_argv([str(self.script)])
        self.assertEqual(code, 1, output.getvalue())
        self.assertIn(f"pair.stl not written: {PEG_FAILED}", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
        self.assertFalse((self.root / "STL/pair.stl").exists())

    def test_a_part_that_cannot_be_meshed_is_a_warning_on_the_build_naming_it(self) -> None:
        # The model alone: a declared STL of the part fails the build (the test above).
        self.script.write_text(MODEL.replace('@stl(out="../STL/pair.stl")\n', ""), encoding="utf-8")
        self.assertEqual(self.build(failing(3))[0], "built", "the build stands")
        warnings = [line for line in self.output.splitlines() if "could not be meshed" in line]
        self.assertEqual(warnings, [f"[cadgen] warning: pair: {PEG_FAILED}; views leave it out"])

    def test_a_display_job_that_cannot_be_asked_for_is_a_warning_on_the_build(self) -> None:
        from cadgen.store import parts

        self.script.write_text(MODEL.replace('@stl(out="../STL/pair.stl")\n', ""), encoding="utf-8")
        with mock.patch.object(parts, "request_display", side_effect=RuntimeError("no pool")):
            self.assertEqual(self.build()[0], "built", "the build stands")
        warnings = [line for line in self.output.splitlines() if "display data not derived" in line]
        self.assertEqual(warnings, ["[cadgen] warning: pair: display data not derived (RuntimeError: no pool); "
                                    "the first view derives it"])

    def test_a_snapshot_and_a_list_go_on_without_a_part_that_cannot_be_meshed_naming_it(self) -> None:
        """As the CAD Viewer does: a snapshot draws the rest of the model and a list lists it,
        each warning of the part in the build's words, and exits as for any warning. A snapshot
        asks for the part once. Only one with nothing left to show fails, naming what it lacks."""
        from cadgen.store import parts
        from tests.python.support.png import read_png

        self.build()
        # The peg's display data is gone, and the job a snapshot asks for it fails.
        [peg] = [key for key in (self.store / "index/part").iterdir()
                 if parts.probe(key.name)["glb"]["indexCount"] // 3 != 12]
        peg.unlink()
        image = self.root / "pair.png"
        code, out, said, jobs = self.snapshot(failing(3), str(image), "--width", "320", "--height", "240")
        self.assertEqual((code, jobs), (0, 1), said)
        self.assertEqual(out, [f"saved snapshot: {image}"])
        self.assertEqual(said, [f"warning: {PEG_FAILED}, so the view does not draw it"])
        png = read_png(image.read_bytes())
        background = png.pixel(0, 0)
        drawn = sum(png.pixel(x, y) != background for x in range(0, 320, 4) for y in range(0, 240, 4))
        self.assertGreater(drawn, 200, "the block is drawn")

        code, out, said, _ = self.snapshot(failing(3), "--mode", "list")
        self.assertEqual(code, 0, said)
        self.assertEqual([(row["ref"], row["name"]) for row in json.loads(out[0])], [(f"#{BLOCK_ID}", "block")])
        self.assertEqual(said, [f"warning: {PEG_FAILED}, so the list leaves it out"])

        code, _, said, _ = self.snapshot(failing(3), "--mode", "list", "--focus", f"#{PEG_ID}")
        self.assertEqual((code, said), (1, [f"[cadgen step snapshot] FAILED: MeshProductionError: {PEG_FAILED}"]))
        shutil.rmtree(self.store / "index/part")
        code, _, said, _ = self.snapshot(failing(3, 6), "--mode", "list")
        self.assertEqual((code, said), (1, [
            f"[cadgen step snapshot] FAILED: MeshProductionError: #{BLOCK_ID} block could not be meshed "
            f"(MeshProductionError: ValueError: boom); {PEG_FAILED}"]))


if __name__ == "__main__":
    unittest.main()
