import shutil
import unittest

from cadpy_common.assembly_spec import (
    IDENTITY_TRANSFORM,
    AssemblySpecError,
    assembly_spec_from_payload,
)
from tests.python.support.cad_test_roots import IsolatedCadRoots


class AssemblySpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="assembly-spec-")
        self.cad_root = self._isolated_roots.cad_root
        self.assembly_path = self.cad_root / "STEP" / "assembly.py"
        self.assembly_path.parent.mkdir(parents=True, exist_ok=True)
        self.leaf_step = self.assembly_path.parent / "leaf.step"
        self.leaf_step.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._isolated_roots.root, ignore_errors=True)

    def test_flat_instances_are_normalized_to_root_children(self) -> None:
        spec = assembly_spec_from_payload(
            self.assembly_path,
            {
                "instances": [
                    {
                        "path": "leaf.step",
                        "name": "leaf",
                        "transform": list(IDENTITY_TRANSFORM),
                    }
                ]
            },
        )

        self.assertEqual(1, len(spec.instances))
        self.assertEqual(1, len(spec.children))
        self.assertEqual("leaf", spec.children[0].instance_id)
        self.assertEqual(self.leaf_step.resolve(), spec.children[0].source_path)

    def test_nested_children_parse_to_leaf_instances(self) -> None:
        spec = assembly_spec_from_payload(
            self.assembly_path,
            {
                "children": [
                    {
                        "name": "module",
                        "transform": list(IDENTITY_TRANSFORM),
                        "children": [
                            {
                                "path": "leaf.step",
                                "name": "leaf",
                                "transform": list(IDENTITY_TRANSFORM),
                            }
                        ],
                    }
                ]
            },
        )

        self.assertEqual(1, len(spec.children))
        self.assertEqual("module", spec.children[0].instance_id)
        self.assertEqual(1, len(spec.children[0].children))
        self.assertEqual(("leaf",), tuple(instance.instance_id for instance in spec.instances))

    def test_rejects_duplicate_sibling_names(self) -> None:
        with self.assertRaisesRegex(AssemblySpecError, "duplicates 'leaf'"):
            assembly_spec_from_payload(
                self.assembly_path,
                {
                    "children": [
                        {
                            "path": "leaf.step",
                            "name": "leaf",
                            "transform": list(IDENTITY_TRANSFORM),
                        },
                        {
                            "path": "leaf.step",
                            "name": "leaf",
                            "transform": list(IDENTITY_TRANSFORM),
                        },
                    ]
                },
            )

    def test_rejects_empty_subassembly_children(self) -> None:
        with self.assertRaisesRegex(AssemblySpecError, "children\\[1\\]\\.children must be a non-empty array"):
            assembly_spec_from_payload(
                self.assembly_path,
                {
                    "children": [
                        {
                            "name": "module",
                            "transform": list(IDENTITY_TRANSFORM),
                            "children": [],
                        }
                    ]
                },
            )

    def test_rejects_absolute_paths(self) -> None:
        with self.assertRaisesRegex(AssemblySpecError, "must be a relative STEP path"):
            assembly_spec_from_payload(
                self.assembly_path,
                {
                    "children": [
                        {
                            "path": str(self.leaf_step.resolve()),
                            "name": "leaf",
                            "transform": list(IDENTITY_TRANSFORM),
                        }
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()
