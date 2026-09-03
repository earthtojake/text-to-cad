"""The catalog-scan contract, ported from ``scanner.test.mjs``.

The strongest check on this module is not here: it is the byte-for-byte diff of
a whole catalog against the Node scanner over a real tree. What these pin is
the behaviour that diff cannot see on any one machine — the branches a
particular corpus happens not to reach, and the JS/Python semantics that agree
on well-formed input and part company on the edges.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.viewer.scanner import (
    CAD_CATALOG_SCHEMA_VERSION,
    is_served_cad_asset,
    node_basename,
    path_is_inside,
    path_relative,
    scan_cad_directory,
    sort_catalog_entries,
    source_format_for_path,
    step_kind_from_topology,
)
from cadgen.viewer.store_paths import (
    CACHE_SCHEMA_VERSION,
    render_package_dir,
    store_packages_dir,
)


class ScannerTestCase(unittest.TestCase):
    """A temp root plus a temp cadgen store, with the env pointed at both."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "models")
        os.makedirs(self.root)
        cache = os.path.join(self.tmp, "cache")
        os.makedirs(os.path.join(cache, "packages"))
        # Set AFTER the app would have been constructed: the cache root is read
        # from the environment on every call, never memoised at import.
        previous = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = cache
        self.addCleanup(self._restore_cache_dir, previous)
        self.cache = cache

    @staticmethod
    def _restore_cache_dir(previous) -> None:
        if previous is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = previous

    # --- helpers ----------------------------------------------------------

    def write(self, rel: str, text: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Bytes, not text mode: several tests assert byte counts and served
        # bodies exactly, and text mode would write \r\n on Windows.
        Path(path).write_bytes(text.encode("utf-8"))
        return path

    def package(self, rel: str, descriptor, *, raw: str | None = None) -> str:
        """Create the store package keyed by the CONTENT of ``root/<rel>``."""
        digest = hashlib.sha256(Path(self.root, rel).read_bytes()).hexdigest()
        package_dir = os.path.join(store_packages_dir(), f"{digest}-v{CACHE_SCHEMA_VERSION}")
        os.makedirs(package_dir, exist_ok=True)
        Path(package_dir, "c0.surf").write_bytes(b"SURF\x00")
        Path(package_dir, "assembly.json").write_text(
            raw if raw is not None else json.dumps(descriptor), encoding="utf-8"
        )
        return package_dir

    def scan(self) -> list[dict]:
        return scan_cad_directory(self.root)["entries"]

    def files(self) -> list[str]:
        return [entry["file"] for entry in self.scan()]

    def entry(self, name: str) -> dict:
        for entry in self.scan():
            if entry["file"] == name:
                return entry
        raise AssertionError(f"no entry {name!r} in {self.files()}")


class ArtifactsOnly(ScannerTestCase):
    def test_model_scripts_never_list(self):
        self.write("drawing.dxf.py", "print(1)")
        self.write("model.py", "print(1)")
        self.assertEqual(self.scan(), [])

    def test_the_written_artifact_is_the_entry(self):
        self.write("drawing.dxf.py", "print(1)")
        self.write("outline.dxf", "0\nSECTION\n")
        self.assertEqual(self.files(), ["outline.dxf"])

    def test_implicit_js_is_not_an_entry_and_does_not_stop_the_scan(self):
        self.write("gyroid.implicit.js", "export default 1;")
        self.write("outline.dxf", "0\n")
        self.assertEqual(self.files(), ["outline.dxf"])

    def test_a_loose_params_js_is_inert(self):
        self.write("part.stl", "solid\n")
        self.write("part.params.js", "export default {};")
        self.assertEqual(self.files(), ["part.stl"])

    def test_the_schema_version_is_4(self):
        self.assertEqual(scan_cad_directory(self.root)["schemaVersion"], 4)
        self.assertEqual(CAD_CATALOG_SCHEMA_VERSION, 4)

    def test_a_falsy_root_raises_and_a_missing_one_scans_empty(self):
        with self.assertRaises(ValueError):
            scan_cad_directory("")
        self.assertEqual(
            scan_cad_directory(os.path.join(self.tmp, "nope")),
            {"schemaVersion": 4, "entries": []},
        )


class EntryShape(ScannerTestCase):
    def test_a_single_asset_entry_and_its_key_order(self):
        self.write("outline.dxf", "0\nSECTION\n")
        entry = self.entry("outline.dxf")
        self.assertEqual(list(entry), ["file", "kind", "url", "hash", "bytes"])
        self.assertEqual(entry["kind"], "dxf")
        self.assertIn("outline.dxf?v=", entry["url"])
        self.assertEqual(len(entry["hash"]), 64)
        self.assertEqual(entry["bytes"], 10)
        self.assertNotIn("relations", entry)

    def test_a_zero_byte_file_still_lists(self):
        self.write("empty.stl", "")
        entry = self.entry("empty.stl")
        self.assertEqual(entry["bytes"], 0)
        self.assertEqual(
            entry["hash"], hashlib.sha256(b"").hexdigest()
        )

    def test_file_refs_are_posix_by_contract_because_they_become_urls(self):
        self.write("sub dir/arm.urdf", '<robot name="a"/>')
        self.assertEqual(self.files(), ["sub dir/arm.urdf"])

    @unittest.skipIf(
        os.name == "nt",
        "'*' is not a legal NTFS filename character; this URL-encoding corpus exists only on POSIX",
    )
    def test_the_v_token_and_url_encoding(self):
        self.write("a b(c)*d~e.stl", "x")
        entry = self.entry("a b(c)*d~e.stl")
        # encodeURIComponent leaves !~*'() alone and escapes the space.
        self.assertTrue(entry["url"].startswith("/a%20b(c)*d~e.stl?v="))
        stat_result = os.stat(os.path.join(self.root, "a b(c)*d~e.stl"))
        self.assertEqual(entry["url"].split("?v=")[1].count("-"), 1)
        self.assertEqual(entry["bytes"], stat_result.st_size)

    def test_kind_comes_from_the_lowercased_extension(self):
        for name, kind in (
            ("a.STL", "stl"),
            ("b.3MF", "3mf"),
            ("c.GLB", "glb"),
            ("d.SDF", "sdf"),
        ):
            self.write(name, "x")
            self.assertEqual(self.entry(name)["kind"], kind)
        self.assertEqual(source_format_for_path("x.STP", ".STP"), "stp")


class StorePackages(ScannerTestCase):
    def test_packages_resolve_by_content_hash_inside_the_store(self):
        self.write("a.step", "same bytes\n")
        self.write("sub/b.step", "same bytes\n")
        self.write("c.step", "other bytes\n")
        a = render_package_dir(os.path.join(self.root, "a.step"))
        b = render_package_dir(os.path.join(self.root, "sub", "b.step"))
        c = render_package_dir(os.path.join(self.root, "c.step"))
        self.assertTrue(path_is_inside(a, store_packages_dir()))
        self.assertEqual(a, b, "same bytes anywhere share one package")
        self.assertNotEqual(a, c)

    def test_a_missing_file_resolves_to_a_deterministic_never_created_path(self):
        unbuilt = render_package_dir(os.path.join(self.root, "gone.step"))
        self.assertTrue(path_is_inside(unbuilt, store_packages_dir()))
        self.assertTrue(node_basename(unbuilt).startswith("unbuilt-"))
        self.assertFalse(os.path.exists(unbuilt))
        self.assertEqual(unbuilt, render_package_dir(os.path.join(self.root, "gone.step")))

    def test_a_step_with_no_package_has_no_v_token_no_hash_and_no_bytes(self):
        self.write("bare.step", "ISO-10303-21;\n")
        entry = self.entry("bare.step")
        self.assertTrue(entry["url"].startswith("/__cad/store?file="))
        self.assertNotIn("&v=", entry["url"])
        self.assertEqual(entry["hash"], "")
        self.assertEqual(entry["bytes"], 0)
        self.assertEqual(entry["kind"], "part")

    def test_the_store_file_param_carries_no_leading_slash(self):
        self.write("p.step", "x\n")
        self.package("p.step", {"kind": "assembly-package", "components": {}})
        entry = self.entry("p.step")
        self.assertRegex(
            entry["url"],
            rf"^/__cad/store\?file=[0-9a-f]{{64}}-v{CACHE_SCHEMA_VERSION}&v=",
        )

    def test_hash_and_bytes_describe_assembly_json_not_the_step(self):
        self.write("p.step", "a much longer step body than the descriptor\n")
        package_dir = self.package("p.step", {"kind": "assembly-package", "components": {}})
        descriptor = Path(package_dir, "assembly.json")
        entry = self.entry("p.step")
        self.assertEqual(entry["bytes"], descriptor.stat().st_size)
        self.assertEqual(
            entry["hash"], hashlib.sha256(descriptor.read_bytes()).hexdigest()
        )


class StepKind(ScannerTestCase):
    def _kind(self, descriptor, *, raw=None) -> str:
        self.write("k.step", "x\n")
        self.package("k.step", descriptor, raw=raw)
        return self.entry("k.step")["kind"]

    def test_entry_kind_is_trimmed_and_lowercased(self):
        self.assertEqual(
            self._kind({"kind": "assembly-package", "entryKind": "  ASSEMBLY  "}), "assembly"
        )

    def test_an_assembly_root_object_makes_it_an_assembly(self):
        self.assertEqual(
            self._kind({"kind": "assembly-package", "assembly": {"root": {}}}), "assembly"
        )

    def test_an_assembly_root_string_does_not(self):
        self.assertEqual(
            self._kind({"kind": "assembly-package", "assembly": {"root": "x"}}), "part"
        )

    def test_no_package_is_a_part(self):
        self.write("k.step", "x\n")
        self.assertEqual(self.entry("k.step")["kind"], "part")

    def test_the_unit_function_answers_part_for_a_falsy_topology(self):
        self.assertEqual(step_kind_from_topology(None), "part")
        self.assertEqual(step_kind_from_topology({}), "part")


class DescriptorGate(ScannerTestCase):
    """``{}`` from ``read_step_catalog_metadata`` suppresses sourceUrl/poseUrl."""

    def _entry_with_sidecar(self, descriptor, *, raw=None, descriptor_is_dir=False) -> dict:
        self.write("g.step", "x\n")
        self.write("g.step.json", json.dumps({"kinematics": {"joints": []}}))
        digest = hashlib.sha256(Path(self.root, "g.step").read_bytes()).hexdigest()
        package_dir = os.path.join(store_packages_dir(), f"{digest}-v{CACHE_SCHEMA_VERSION}")
        os.makedirs(package_dir, exist_ok=True)
        if descriptor_is_dir:
            os.makedirs(os.path.join(package_dir, "assembly.json"), exist_ok=True)
        else:
            Path(package_dir, "assembly.json").write_text(
                raw if raw is not None else json.dumps(descriptor), encoding="utf-8"
            )
        return self.entry("g.step")

    def test_a_valid_package_publishes_both_urls(self):
        entry = self._entry_with_sidecar({"kind": "assembly-package", "components": {}})
        self.assertEqual(entry["sourceUrl"], "/g.step.json")
        self.assertEqual(entry["poseUrl"], "/g.step.json")
        self.assertNotIn("?v=", entry["sourceUrl"], "sidecar urls carry no version token")

    def test_a_wrong_descriptor_kind_suppresses_both_even_with_a_sidecar(self):
        entry = self._entry_with_sidecar({"kind": "not-a-package"})
        self.assertNotIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)

    def test_an_unparseable_descriptor_suppresses_both(self):
        entry = self._entry_with_sidecar(None, raw="{ not json")
        self.assertNotIn("sourceUrl", entry)

    def test_a_json_array_descriptor_suppresses_both(self):
        entry = self._entry_with_sidecar(None, raw="[1,2,3]")
        self.assertNotIn("sourceUrl", entry)

    def test_a_directory_named_assembly_json_counts_as_missing(self):
        entry = self._entry_with_sidecar(None, descriptor_is_dir=True)
        self.assertNotIn("sourceUrl", entry)
        self.assertEqual(entry["hash"], "")

    def test_no_package_suppresses_both(self):
        self.write("g.step", "x\n")
        self.write("g.step.json", json.dumps({"kinematics": {}}))
        entry = self.entry("g.step")
        self.assertNotIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)


class SidecarTruthiness(ScannerTestCase):
    """JS ``typeof x === "object"`` and JS truthiness, which Python's differ from."""

    def _entry(self, sidecar_text: str | None) -> dict:
        self.write("s.step", "x\n")
        if sidecar_text is not None:
            self.write("s.step.json", sidecar_text)
        self.package("s.step", {"kind": "assembly-package", "components": {}})
        return self.entry("s.step")

    def test_an_array_sidecar_counts_as_a_sidecar(self):
        entry = self._entry("[1,2]")
        self.assertIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)

    def test_an_empty_kinematics_object_still_yields_a_pose_url(self):
        # `{}` is TRUTHY in JS. Python's `or` would drop it.
        self.assertIn("poseUrl", self._entry(json.dumps({"kinematics": {}})))

    def test_explicit_nulls_yield_no_pose_url(self):
        entry = self._entry(json.dumps({"kinematics": None, "animation": None}))
        self.assertIn("sourceUrl", entry)
        self.assertNotIn("poseUrl", entry)

    def test_animation_alone_yields_a_pose_url(self):
        self.assertIn("poseUrl", self._entry(json.dumps({"animation": {"t": "x"}})))

    def test_a_scalar_sidecar_is_not_a_sidecar(self):
        for text in ('"hello"', "5", "null", "true"):
            with self.subTest(text=text):
                self.assertNotIn("sourceUrl", self._entry(text))

    def test_an_invalid_sidecar_is_not_a_sidecar(self):
        self.assertNotIn("sourceUrl", self._entry("{ not json"))

    def test_no_sidecar_at_all(self):
        self.assertNotIn("sourceUrl", self._entry(None))

    def test_the_catalog_publishes_no_provenance(self):
        entry = self._entry(json.dumps({"schemaVersion": 5, "sourceKind": "step"}))
        for forbidden in ("sourceKind", "source", "poseHatchUrl", "moduleUrl", "legacyParamsSidecar"):
            self.assertNotIn(forbidden, entry)

    def test_the_sidecar_suffix_is_appended_to_the_whole_name(self):
        self.write("u.STP", "x\n")
        self.write("u.STP.json", json.dumps({"kinematics": {}}))
        self.package("u.STP", {"kind": "assembly-package", "components": {}})
        self.assertEqual(self.entry("u.STP")["sourceUrl"], "/u.STP.json")


class SrdfPairing(ScannerTestCase):
    def test_an_srdf_pairs_with_the_matching_same_directory_urdf(self):
        self.write("arm.urdf", '<?xml version="1.0"?><robot name="arm"><link name="l"/></robot>')
        self.write("other.urdf", '<robot name="other"/>')
        self.write("arm.srdf", '<robot name="arm"/>')
        relation = self.entry("arm.srdf")["relations"]["urdf"]
        self.assertEqual(list(relation), ["file", "url", "hash", "bytes"])
        self.assertEqual(relation["file"], "arm.urdf")

    def test_a_prolog_of_declaration_comment_and_doctype_is_skipped(self):
        self.write("z.urdf", '<robot name="z"/>')
        self.write(
            "z.srdf",
            '<?xml version="1.0"?><!-- c --><!DOCTYPE robot><robot name="z"/>',
        )
        self.assertEqual(self.entry("z.srdf")["relations"]["urdf"]["file"], "z.urdf")

    def test_single_quotes_and_spaced_attributes_work(self):
        self.write("q.urdf", "<robot  name = 'q'  version=\"1\" />")
        self.write("q.srdf", "<robot name='q'/>")
        self.assertIn("relations", self.entry("q.srdf"))

    def test_ambiguity_yields_no_pairing(self):
        self.write("one.urdf", '<robot name="dup"/>')
        self.write("two.urdf", '<robot name="dup"/>')
        self.write("dup.srdf", '<robot name="dup"/>')
        self.assertNotIn("relations", self.entry("dup.srdf"))

    def test_a_robot_with_no_name_never_pairs(self):
        self.write("n.urdf", "<robot/>")
        self.write("n.srdf", "<robot/>")
        self.assertNotIn("relations", self.entry("n.srdf"))

    def test_a_urdf_in_another_directory_never_pairs(self):
        self.write("deep/far.urdf", '<robot name="far"/>')
        self.write("far.srdf", '<robot name="far"/>')
        self.assertNotIn("relations", self.entry("far.srdf"))

    def test_invalid_utf8_is_replaced_not_fatal_so_mojibake_still_pairs(self):
        Path(self.root, "m.urdf").write_bytes(b'<robot name="m\xff\xfe"/>')
        Path(self.root, "m.srdf").write_bytes(b'<robot name="m\xff\xfe"/>')
        self.assertIn("relations", self.entry("m.srdf"))

    def test_a_leading_bom_is_skipped(self):
        self.write("b.urdf", '﻿<robot name="b"/>')
        self.write("b.srdf", '﻿<robot name="b"/>')
        self.assertIn("relations", self.entry("b.srdf"))

    def test_a_non_robot_root_never_pairs(self):
        self.write("x.urdf", '<sdf name="x"/>')
        self.write("x.srdf", '<sdf name="x"/>')
        self.assertNotIn("relations", self.entry("x.srdf"))

    def test_a_hidden_urdf_still_wins_the_pairing(self):
        # A latent inconsistency preserved verbatim: the relation URL it hands
        # out is then refused by is_served_cad_asset, so the client gets a 404
        # on a link the catalog gave it. Recorded here so a "fix" is deliberate.
        self.write(".arm.urdf", '<robot name="hid"/>')
        self.write("hid.srdf", '<robot name="hid"/>')
        relation = self.entry("hid.srdf")["relations"]["urdf"]
        self.assertEqual(relation["file"], ".arm.urdf")
        self.assertFalse(is_served_cad_asset(os.path.join(self.root, ".arm.urdf")))


class SymlinkPolicy(ScannerTestCase):
    def test_directory_symlinks_are_followed_on_purpose(self):
        os.makedirs(os.path.join(self.tmp, "library_real"))
        Path(self.tmp, "library_real", "part.step").write_text("x\n", encoding="utf-8")
        os.symlink(os.path.join(self.tmp, "library_real"), os.path.join(self.root, "library"))
        # The literal POSIX spelling, never os.path.join.
        self.assertEqual(self.files(), ["library/part.step"])

    def test_a_symlink_loop_terminates_with_exactly_one_entry(self):
        self.write("model.step", "x\n")
        os.symlink(".", os.path.join(self.root, "loop"))
        self.assertEqual(len([f for f in self.files() if f.endswith("model.step")]), 1)

    def test_broken_symlinks_are_skipped_not_fatal(self):
        self.write("ok.stl", "x")
        os.symlink(os.path.join(self.tmp, "nowhere.stl"), os.path.join(self.root, "dangling.stl"))
        self.assertEqual(self.files(), ["ok.stl"])

    def test_file_symlinks_are_followed_and_not_deduplicated(self):
        self.write("real.stl", "same")
        os.symlink(os.path.join(self.root, "real.stl"), os.path.join(self.root, "link.stl"))
        entries = self.scan()
        self.assertEqual([e["file"] for e in entries], ["link.stl", "real.stl"])
        self.assertEqual(entries[0]["hash"], entries[1]["hash"])

    def test_an_earlier_sorted_alias_hides_the_real_directory(self):
        # The flip side of the visited-real-path loop guard, not a separate
        # rule: dedup is by DIRECTORY, so only the first spelling is walked.
        os.makedirs(os.path.join(self.root, "real"))
        Path(self.root, "real", "part.stl").write_text("x", encoding="utf-8")
        os.symlink(os.path.join(self.root, "real"), os.path.join(self.root, "Alink"))
        self.assertEqual(self.files(), ["Alink/part.stl"])

    def test_a_link_out_of_the_root_is_served(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        Path(outside, "secret.step").write_text("outside\n", encoding="utf-8")
        os.symlink(os.path.join(outside, "secret.step"), os.path.join(self.root, "escape.step"))
        self.assertEqual(self.files(), ["escape.step"])


class WalkRules(ScannerTestCase):
    def test_skipped_directories_and_hidden_names(self):
        for skipped in ("dist", "build", "coverage", "node_modules", "__pycache__", "viewer", "__cadgen__"):
            self.write(f"{skipped}/x.stl", "x")
        self.write(".hidden/secret.stl", "x")
        self.write(".dotfile.stl", "x")
        self.write("kept.stl", "x")
        self.assertEqual(self.files(), ["kept.stl"])

    def test_the_skipped_set_is_matched_with_exact_case(self):
        # Written without a lowercase twin so a case-insensitive filesystem
        # cannot merge the two directories and hide the assertion.
        self.write("Dist/kept.stl", "x")
        self.write("BUILD/kept.stl", "x")
        self.assertEqual(sorted(self.files()), ["BUILD/kept.stl", "Dist/kept.stl"])

    def test_the_depth_cap_stops_the_walk(self):
        current = self.root
        for level in range(70):
            current = os.path.join(current, f"d{level}")
            os.makedirs(current)
            Path(current, f"f{level}.stl").write_text("x", encoding="utf-8")
        files = self.files()
        # Files at the root are collected at depth 0, so d<k> is entered at
        # depth k+1 and the guard admits k <= 63.
        self.assertEqual(len(files), 64)
        self.assertTrue(any(f.endswith("d63/f63.stl") for f in files))
        self.assertFalse(any(f.endswith("d64/f64.stl") for f in files))

    def test_only_the_source_extensions_become_entries(self):
        for name in ("a.step", "b.stp", "c.stl", "d.3mf", "e.glb", "f.dxf", "g.urdf", "h.srdf", "i.sdf"):
            self.write(name, "x")
        for name in ("j.json", "k.js", "l.txt", "m.py", "n", "o.stepx"):
            self.write(name, "x")
        self.assertEqual(len(self.scan()), 9)


class NaturalOrder(ScannerTestCase):
    def test_numeric_runs_compare_as_integers(self):
        for name in ("v2.10.step", "v2.9.step", "v10.1.step"):
            self.write(name, "x")
        self.assertEqual(self.files(), ["v2.9.step", "v2.10.step", "v10.1.step"])

    def test_ties_preserve_the_walk_order_and_the_sort_is_non_mutating(self):
        entries = [{"file": "b"}, {"file": "A"}, {"file": "a"}, {"file": "B"}]
        ordered = sort_catalog_entries(entries)
        self.assertEqual([e["file"] for e in ordered], ["A", "a", "b", "B"])
        self.assertEqual([e["file"] for e in entries], ["b", "A", "a", "B"])

    def test_the_key_coerces_a_missing_or_falsy_file_to_empty(self):
        entries = [{"file": "a"}, {}, {"file": None}, {"file": 0}, {"file": ""}]
        self.assertEqual(sort_catalog_entries(entries)[-1]["file"], "a")

    def test_punctuation_sorts_before_digits_before_letters(self):
        for name in ("_x.stl", "9.stl", "a.stl"):
            self.write(name, "x")
        self.assertEqual(self.files(), ["_x.stl", "9.stl", "a.stl"])


class ServedAssetGate(unittest.TestCase):
    def test_the_gate(self):
        self.assertFalse(is_served_cad_asset("/root/.secret.step"))
        self.assertTrue(is_served_cad_asset("/root/part.step.json"))
        self.assertTrue(is_served_cad_asset("/root/PART.STEP.JSON"))
        self.assertTrue(is_served_cad_asset("/root/part.stp.json"))
        self.assertFalse(is_served_cad_asset("/root/random.js"))
        self.assertFalse(is_served_cad_asset("/root/part.step.js"))
        self.assertFalse(is_served_cad_asset("/root/secrets.json"))
        self.assertTrue(is_served_cad_asset("/root/part.step"))
        self.assertTrue(is_served_cad_asset("/root/part.SDF"))
        self.assertFalse(is_served_cad_asset("/root/notes.txt"))

    def test_the_hidden_check_is_on_the_basename_only(self):
        # A model root that itself lives under a hidden absolute path must
        # still serve; hidden components BELOW the root are the backend's job.
        self.assertTrue(is_served_cad_asset("/home/u/.models/part.step"))

    def test_a_backslash_is_an_ordinary_filename_character_on_posix(self):
        if os.name == "nt":
            self.skipTest("POSIX-only semantics")
        # Normalising backslashes here would let this pass the hidden gate.
        self.assertFalse(is_served_cad_asset("/root/.secret\\x.step"))


class PathHelpers(unittest.TestCase):
    def test_path_relative_answers_empty_for_equal_paths(self):
        # os.path.relpath answers "." and the hidden-component check would then
        # read the served root itself as hidden.
        self.assertEqual(path_relative("/a/b", "/a/b"), "")
        self.assertEqual(path_relative("/a", "/a/b"), "b")
        self.assertEqual(path_relative("/a", "/b"), os.path.join("..", "b"))

    def test_path_is_inside_treats_realpath_as_alias_equality(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        real_root = os.path.join(tmp, "root")
        os.makedirs(os.path.join(real_root, "sub"))
        Path(real_root, "sub", "part.step").write_text("x", encoding="utf-8")
        alias = os.path.join(tmp, "alias")
        os.symlink(real_root, alias)
        self.assertTrue(path_is_inside(os.path.join(alias, "sub", "part.step"), alias))
        self.assertTrue(path_is_inside(os.path.join(real_root, "sub", "part.step"), alias))
        self.assertTrue(path_is_inside(os.path.join(alias, "sub", "part.step"), real_root))
        self.assertFalse(path_is_inside(os.path.join(tmp, "outside.step"), alias))

    def test_a_dotdot_after_a_symlinked_component_is_still_refused(self):
        # The lexical branch runs FIRST and collapses "..", which is the whole
        # reason realpath may not be the primary check.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = os.path.join(tmp, "root")
        outside = os.path.join(tmp, "outside")
        os.makedirs(root)
        os.makedirs(outside)
        os.symlink(outside, os.path.join(root, "lib"))
        self.assertFalse(path_is_inside(os.path.join(root, "lib", "..", "..", "x.step"), root))

    def test_a_name_prefix_sibling_is_not_inside(self):
        self.assertFalse(path_is_inside("/base/root-evil/x.step", "/base/root"))
        self.assertFalse(path_is_inside("/base/rootevil", "/base/root"))
        self.assertTrue(path_is_inside("/base/root/x.step", "/base/root"))

    def test_node_basename_strips_trailing_separators(self):
        self.assertEqual(node_basename("/a/b/"), "b")
        self.assertEqual(node_basename("/a/b"), "b")
        self.assertEqual(node_basename("/"), "")
        self.assertEqual(node_basename("b"), "b")


if __name__ == "__main__":
    unittest.main()
