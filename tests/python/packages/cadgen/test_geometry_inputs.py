"""Geometry-complete publication, and display data derived from it alone."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.tree_ids import tokenized
add_repo_path("packages/cadgen/src")

from cadgen._internal import component_package as cp
from cadgen.store import parts
from cadgen.store.build import build_document_tree, build_tree_from_compound
from cadgen.store.materialize import materialize, materialize_descriptor
from cadgen.store.objects import object_path, put_object, read_verified_object
from cadgen.store.trees import capture_tree, TREE_KIND, TREE_SCHEMA, _validate_structure


def publish_document(scene):
    return build_document_tree(scene)[:2]


def materialize_snapshot(descriptor, captured):
    shapes = {cid: cp.decode_geometry_component(entry, captured[entry["brep"]])
              for cid, entry in descriptor["components"].items()}
    return materialize_descriptor(descriptor, shapes=shapes)


def facts_of(digest, cid):
    """The topology facts a part's derivation takes for ``cid`` (``parts._topology``): extracted
    in memory and stored nowhere, or an eager-only component's pinned object."""
    entry = capture_tree(digest, retain_payloads=False)[0]["components"][cid]
    return parts._topology(entry, None if entry["kind"] == "eager-only" else parts._decoded(entry)[0])


def part_objects(records):
    """Every object the part records name."""
    return [record[role]["object"] for record in records.values() for role in ("glb", "selectors")]


def store_component(shape, _unused=None, meta=None):
    prepared = cp.prepare_geometry_component(shape)
    entry = prepared["entry"]
    put_object(prepared["payload"], repair=True)
    if prepared["topology"] is not None:
        put_object(prepared["topology"], repair=True)
    return entry["contentHash"][:16], entry


class GeometryInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="geometry-inputs-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_COMPONENT_WORKERS": "1", "CADGEN_DAEMON": "0",
        })
        self.env.start(); self.addCleanup(self.env.stop)
        from cadgen.store.materialize import reset_memo
        reset_memo(); self.addCleanup(reset_memo)

    def component_tree(self, shape):
        digest, tree, _ = build_tree_from_compound(shape, root_name="box")
        cid = next(iter(tree["components"]))
        return digest, tree, cid, tree["components"][cid]

    def scene(self, *, nested=False, colors=True):
        from build123d import Compound, Location, Solid
        from cadgen.step_export import export_build123d_step_file
        from cadgen._internal.step_scene_package import load_step_scene_exact
        base = Solid.make_box(2, 3, 4)
        base.label = 'box'
        base.color = (1., .2, .1, 1.)
        if colors: base.cad_face_ordinal_colors = {1: (.2, .3, .9, 1.)}
        if nested:
            part = Solid.make_cylinder(1, 3)
            part.label = 'cylinder'
            group = Compound(children=[base, part.moved(Location((4, 0, 0)))], label='group')
            clone = base.moved(Location((8, 0, 0)))
            clone.label='again'
            base = Compound(children=[group, clone], label='root')
        path = self.root / ('nested.step' if nested else 'box.step')
        export_build123d_step_file(base, path)
        return load_step_scene_exact(path)

    def emitted(self, shape, name):
        from cadgen.step_export import export_build123d_step_file
        path=self.root/name
        export_build123d_step_file(shape,path)
        return path.read_bytes()

    def test_geometry_and_native_read_extract_nothing(self):
        from cadgen._internal import topology_extract
        scene=self.scene(nested=True)
        with mock.patch.object(topology_extract, 'extract_topology_facts', side_effect=AssertionError('extraction forbidden')):
            digest, tree=publish_document(scene)
            self.assertTrue(all(c['kind']=='native' for c in tree['components'].values()))
            shape=materialize(digest)
            self.assertGreater(shape.volume, 0)
            from cadgen._internal.step_scene_package import _scene_from_document_tree
            loaded=_scene_from_document_tree(scene.step_path,tree_hash=digest,step_hash=scene.step_hash)
            self.assertEqual(loaded.step_hash,scene.step_hash)
            self.assertFalse((self.root/'store/index/part').exists())

    def test_display_data_loss_never_blocks_geometry_and_repairs_exactly(self):
        from cadgen._internal import tessellate, topology_extract
        digest,tree=publish_document(self.scene(nested=True))
        expected=parts.derive(digest)
        for result in part_objects(expected): object_path(result).unlink()
        shutil.rmtree(self.root/'store/index/part')
        with mock.patch.object(topology_extract,'extract_topology_facts',side_effect=AssertionError('extraction forbidden')), \
             mock.patch.object(tessellate,'mesh_component',side_effect=AssertionError('mesh forbidden')):
            self.assertGreater(materialize(digest).volume,0)
        self.assertEqual(parts.derive(digest),expected)
        first=part_objects(expected)[0]
        object_path(first).write_bytes(b'corrupt')
        self.assertEqual(parts.derive(digest),expected)
        self.assertEqual(hashlib.sha256(object_path(first).read_bytes()).hexdigest(),first,'the damaged object is repaired')

    def test_effective_colors_rehash_after_reconstruction(self):
        from build123d import Solid
        from cadgen._internal.component_package import _shape_brep_bytes
        shape=Solid.make_box(2,3,4)
        raw={1:(1.,0.,0.,1.),999:(0.,1.,0.,1.)}
        shape.cad_face_ordinal_colors=raw
        effective=cp.effective_face_colors(shape,raw)
        self.assertEqual(set(effective),{1})
        cid,entry=store_component(shape,_shape_brep_bytes(shape),{})
        self.assertEqual(set(entry['faceColors']),{1})
        private=cp._decode_brep(entry['codec'],read_verified_object(entry['brep']))
        self.assertEqual(entry['contentHash'],cp.geometry_component_hash(entry['codec'],read_verified_object(entry['brep']),
                         cp.effective_face_colors(private,entry['faceColors'])))
        self.assertEqual(shape.cad_face_ordinal_colors,raw)

    def test_owned_snapshot_survives_store_deletion_and_mutation(self):
        digest,tree=publish_document(self.scene(nested=True))
        descriptor,captured=capture_tree(digest)
        first=materialize_snapshot(descriptor,captured)
        expected=self.emitted(first,'before.step')
        first.label='mutated'; first.color=(0.,1.,0.,1.)
        first.children[0].label='changed child'
        shutil.rmtree(self.root/'store')
        second=materialize_snapshot(descriptor,captured)
        self.assertEqual(self.emitted(second,'after.step'),expected)
        with self.assertRaises(FileNotFoundError):materialize(digest)

    def test_missing_corrupt_and_wrong_schema_are_not_native_hits(self):
        digest,tree=publish_document(self.scene())
        entry=next(iter(tree['components'].values()))
        path=object_path(entry['brep']);correct=path.read_bytes()
        for bad in (b'corrupt',b''):
            path.write_bytes(bad)
            with self.assertRaises(ValueError):materialize(digest)
            path.write_bytes(correct)
        path.unlink()
        with self.assertRaises(FileNotFoundError):materialize(digest)
        put_object(correct,repair=True)
        bad=copy.deepcopy(tree);bad['kind']='tree'
        with self.assertRaises(ValueError):capture_tree(put_object(cp.canonical_json_bytes(bad)))
        bad=copy.deepcopy(tree);bad['components'][next(iter(bad['components']))]['codec']='auto'
        with self.assertRaises(ValueError):capture_tree(put_object(cp.canonical_json_bytes(bad)))

    def test_record_or_object_corruption_misses_and_derives_again(self):
        from cadgen.store.index import write_entry
        digest,tree=publish_document(self.scene())
        expected=parts.derive(digest)
        cid=next(iter(tree['components']));entry=tree['components'][cid]
        key=parts.part_key(entry,parts.producer_identity())
        record=expected[cid]
        for altered in ({**record,'glb':{**record['glb'],'vertexCount':record['glb']['vertexCount']+1}},
                        {**record,'selectors':{**record['selectors'],'object':put_object(b'not a selector table')}}):
            write_entry('part',key,altered)
            self.assertIsNone(parts.probe(key))
            self.assertEqual(parts.derive(digest),expected)
            self.assertEqual(parts.probe(key),record)

    def test_extraction_failure_never_publishes_a_part(self):
        from cadgen._internal import topology_extract
        digest,tree=publish_document(self.scene())
        with mock.patch.object(topology_extract,'extract_topology_facts',side_effect=ValueError('injected extraction failure')):
            with self.assertRaisesRegex(ValueError,'injected'):parts.derive(digest)
        self.assertFalse(any((self.root/'store/index/part').glob('*')))
        self.assertGreater(materialize(digest).volume,0)

    def test_unknown_producer_cannot_share_persistent_namespace(self):
        with mock.patch('cadgen.store.parts.kernel_versions',return_value=('1','unknown','1')):
            digest,tree=publish_document(self.scene())
            self.assertGreater(materialize(digest).volume,0)
            with self.assertRaises(ValueError):parts.derive(digest)
        self.assertFalse((self.root/'store/index/part').exists())

    def test_a_producer_is_the_kernel_alone(self):
        producer = parts.producer_identity()
        self.assertEqual(set(producer), {"build123d", "ocp", "cadqueryOcp"})
        # An older cadgen's hint also named its extraction scheme and format.
        for malformed in ({**producer, "scheme": 20, "surfFormat": 3}, {"build123d": producer["build123d"]}):
            with self.assertRaisesRegex(ValueError, "unsupported producer"):
                parts.producer_key(malformed)

    def test_a_components_identity_does_not_depend_on_the_producer(self):
        scene=self.scene()
        first_hash,first=publish_document(scene)

        def view():
            return parts.view_from_geometry(first_hash, capture_tree(first_hash, retain_payloads=False)[0])

        with mock.patch('cadgen.store.parts.kernel_versions',return_value=('different','different','different')):
            second_hash,second=publish_document(scene)
            changed=view()
        normal=view()
        self.assertEqual((first_hash,first),(second_hash,second))
        self.assertNotEqual(normal['producer'],changed['producer'])
        cid=next(iter(first['components']))
        self.assertNotEqual(normal['components'][cid]['part'],changed['components'][cid]['part'])
        self.assertNotIn('producer',first)
        self.assertNotIn('part',first['components'][cid])

    def test_same_brep_distinct_face_colors_do_not_share_topology(self):
        from build123d import Solid
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen.store.trees import IDENTITY_16
        shape=Solid.make_box(2,3,4)
        raw=_shape_brep_bytes(shape)
        components={}
        for color in ((1.,0.,0.,1.),(0.,0.,1.,1.)):
            shape.cad_face_ordinal_colors={1:color}
            cid,entry=store_component(shape,raw,{})
            components[cid]=entry
        self.assertEqual(len({entry['brep'] for entry in components.values()}),1)
        self.assertEqual(len(components),2)
        occurrences=[];children=[]
        for ordinal,cid in enumerate(components,1):
            transform=list(IDENTITY_16);transform[3]=(ordinal-1)*5.
            identity=f'o1.{ordinal}'
            occurrences.append({'id':identity,'name':identity,'component':cid,'transform':transform})
            children.append({'id':identity,'name':identity,'nodeType':'part','children':[]})
        tree={'kind':TREE_KIND,'schemaVersion':TREE_SCHEMA,'units':'mm','label':'colors',
              'entryKind':'assembly','components':components,'occurrences':occurrences,'links':[],
              'assembly':{'root':{'id':'o1','name':'colors','nodeType':'assembly','children':children}}}
        tree=tokenized(tree)[0]
        digest=put_object(cp.canonical_json_bytes(tree))
        actual=materialize(digest)
        expected=self.emitted(actual,'colors-a.step')
        self.assertEqual(expected,self.emitted(materialize(digest),'colors-b.step'))
        from cadgen._internal.step_scene_package import load_step_scene_exact
        parsed=load_step_scene_exact(self.root/'colors-a.step')
        recipes=list(parsed.prototype_face_colors.values())
        self.assertEqual(len(recipes),2)
        self.assertNotEqual(list(recipes[0].values()),list(recipes[1].values()))

    def test_malformed_native_or_placement_cannot_gain_materialization(self):
        digest,tree=publish_document(self.scene())
        broken=copy.deepcopy(tree)
        cid=next(iter(broken['components']));entry=broken['components'].pop(cid)
        payload=b'invalid but honestly content addressed'
        entry['brep']=put_object(payload)
        entry['contentHash']=cp.geometry_component_hash(entry['codec'],payload,entry['faceColors'])
        cid=entry['contentHash'][:16];broken['components'][cid]=entry
        broken['occurrences'][0]['component']=cid
        bad_hash=put_object(cp.canonical_json_bytes(broken))
        with self.assertRaises(Exception):materialize(bad_hash)
        broken=copy.deepcopy(tree);broken['occurrences'][0]['transform']=[0.]*15+[1.]
        with self.assertRaises(Exception):_validate_structure(broken,native=True)
        with self.assertRaises(Exception):materialize(put_object(cp.canonical_json_bytes(broken)))

    def test_hash_valid_native_reader_failure_has_a_repairable_exception(self):
        digest, tree = publish_document(self.scene())
        entry = copy.deepcopy(next(iter(tree["components"].values())))
        payload = cp._BREP_HEADERS[entry["codec"]] + b"not a native shape"
        entry["brep"] = put_object(payload)
        entry["contentHash"] = cp.geometry_component_hash(entry["codec"], payload, entry["faceColors"])
        cp.validate_geometry_component(entry, payload)
        with self.assertRaisesRegex(ValueError, "unreadable .* geometry payload") as failure:
            cp.decode_geometry_component(entry, payload)
        self.assertEqual(type(failure.exception.__cause__).__name__, "Standard_Failure")

    def test_part_writers_use_only_artifacts_and_racing_bytes_agree(self):
        digest,tree=publish_document(self.scene())
        from cadgen.store import index
        original=index.read_entry
        def read(kind,key):
            if kind in {'model','output','component','document'}:
                raise AssertionError(f'forbidden index {kind}')
            return original(kind,key)
        with mock.patch.object(index,'read_entry',read):
            expected=parts.derive(digest)
        for digest_ in part_objects(expected):object_path(digest_).unlink()
        shutil.rmtree(self.root/'store/index/part')
        code='from cadgen.store.parts import derive; import json,sys; print(json.dumps(derive(sys.argv[1]),sort_keys=True))'
        processes=[subprocess.Popen([sys.executable,'-c',code,digest],env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                   for _ in range(2)]
        for process in processes:
            out,error=process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,error)
            self.assertEqual(json.loads(out),json.loads(json.dumps(expected)))
        self.assertEqual(parts.derive(digest),expected)

    def point_box(self,parameter,location=None):
        from build123d import Solid
        from OCP.BRep import BRep_PointOnCurve,BRep_Tool
        from OCP.Geom import Geom_Line
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopoDS import TopoDS
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Ax1,gp_Dir,gp_Pnt
        shape=Solid.make_box(2,3,4)
        mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape.wrapped,TopAbs_VERTEX,mapping)
        vertex=next(TopoDS.Vertex_s(mapping.FindKey(i)) for i in range(1,mapping.Extent()+1)
                    if BRep_Tool.Pnt_s(TopoDS.Vertex_s(mapping.FindKey(i))).Coord()==(0.,0.,0.))
        curve=Geom_Line(gp_Ax1(gp_Pnt(-parameter,0,0),gp_Dir(1,0,0)))
        vertex.TShape().ChangePoints().Append(
            BRep_PointOnCurve(parameter,curve,TopLoc_Location() if location is None else location))
        shape.cad_face_ordinal_colors={i:(i/7.,.2,.3,1.) for i in range(1,7)}
        return shape

    def test_point_record_placements_compare_as_numbers(self):
        # A decoder recomposes a location chain, and the product can carry
        # -0.0 where the live shape had 0.0 (the w16 sump pan). Same number,
        # same placement: that must not demote an authored part to eager-only.
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Trsf

        def signature(zero,shift=0.):
            trsf=gp_Trsf();trsf.SetValues(1.,zero,0.,shift, 0.,0.,-1.,0., 0.,1.,0.,0.)
            return cp._point_signature(self.point_box(.5,TopLoc_Location(trsf)))

        self.assertEqual(signature(-0.),signature(0.))
        self.assertNotEqual(signature(0.),signature(0.,shift=1e-12))

    def test_actual_binary_throw_and_silent_loss_use_faithful_v3_artifacts(self):
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen._internal.topology_extract import extract_topology_facts
        from cadgen._internal.component_package import _binary_v3_bytes as binary_v3_bytes
        for parameter in (1e-295,1e-300):
            with self.subTest(parameter=parameter):
                original=self.point_box(parameter)
                native_before=_shape_brep_bytes(original)
                digest,tree,cid,entry=self.component_tree(original)
                self.assertEqual(entry['kind'],'native')
                self.assertEqual(entry['codec'],'bintools-v3')
                decoded=cp._decode_brep(entry['codec'],read_verified_object(entry['brep']))
                self.assertEqual(_shape_brep_bytes(decoded),native_before)
                self.assertEqual(binary_v3_bytes(decoded),read_verified_object(entry['brep']))
                expected=extract_topology_facts(original.wrapped)
                self.assertEqual(facts_of(digest,cid),expected)
                output=materialize(digest)
                self.assertEqual(_shape_brep_bytes(output),native_before)
                output.cad_face_ordinal_colors[1]=(0.,0.,0.,1.)
                self.assertEqual(_shape_brep_bytes(original),native_before)
                self.assertEqual(materialize(digest).cad_face_ordinal_colors[1],original.cad_face_ordinal_colors[1])

    def test_explicit_eager_topology_is_required_and_never_lazily_extracted(self):
        from build123d import Solid
        from cadgen._internal import component_package as _geometry_codec
        from cadgen._internal import topology_extract
        shape=Solid.make_box(2,3,4)
        with mock.patch.object(_geometry_codec,'_encode_brep',side_effect=_geometry_codec.CodecFidelityError('unsupported native fidelity')):
            digest,tree,cid,entry=self.component_tree(shape)
        self.assertEqual(entry['kind'],'eager-only')
        from cadgen._internal.topology_facts import read_topology_facts
        required=read_verified_object(entry['topology'])
        with mock.patch.object(topology_extract,'extract_topology_facts',side_effect=AssertionError('live fallback forbidden')):
            first=parts.derive(digest)
            self.assertEqual(facts_of(digest,cid),read_topology_facts(required))
        object_path(entry['topology']).unlink()
        with self.assertRaises(FileNotFoundError):capture_tree(digest)
        with self.assertRaises(FileNotFoundError):parts.derive(digest)
        put_object(required,repair=True)
        self.assertEqual(first,parts.derive(digest))

    def test_mislabeled_but_hash_valid_codec_cannot_decode(self):
        from build123d import Solid
        from cadgen._internal.component_package import _binary_v3_bytes as binary_v3_bytes
        from cadgen._internal.component_package import _shape_brep_bytes
        shape=Solid.make_box(2,3,4)
        for label,payload in [('bintools-v4',binary_v3_bytes(shape)),('bintools-v3',_shape_brep_bytes(shape))]:
            with self.subTest(codec=label):
                with self.assertRaisesRegex(ValueError,'declared codec'):cp._decode_brep(label,payload)
        _,tree=publish_document(self.scene())
        old_cid=next(iter(tree['components']));entry=tree['components'].pop(old_cid)
        payload=binary_v3_bytes(shape);entry['codec']='bintools-v4';entry['brep']=put_object(payload)
        entry['contentHash']=cp.geometry_component_hash(entry['codec'],payload,entry['faceColors'])
        cid=entry['contentHash'][:16];tree['components'][cid]=entry;tree['occurrences'][0]['component']=cid
        digest=put_object(cp.canonical_json_bytes(tree))
        with self.assertRaisesRegex(ValueError,'declared codec'):materialize(digest)
        with self.assertRaisesRegex(ValueError,'declared codec'):parts.derive(digest)

    def test_actual_point_on_surface_needs_faithful_ascii_artifact(self):
        from OCP.BRep import BRep_PointOnSurface,BRep_Tool
        from OCP.Geom import Geom_Plane
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopoDS import TopoDS
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Pnt,gp_Dir
        from cadgen._internal.component_package import _ascii_v3_bytes as ascii_v3_bytes
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen._internal.topology_extract import extract_topology_facts
        shape=self.point_box(.125)
        mapping=TopTools_IndexedMapOfShape();TopExp.MapShapes_s(shape.wrapped,TopAbs_VERTEX,mapping)
        vertex=next(TopoDS.Vertex_s(mapping.FindKey(i)) for i in range(1,mapping.Extent()+1)
                    if BRep_Tool.Pnt_s(TopoDS.Vertex_s(mapping.FindKey(i))).Coord()==(0.,0.,0.))
        vertex.TShape().ChangePoints().Clear()
        surface=Geom_Plane(gp_Pnt(-.125,-.375,0),gp_Dir(0,0,1))
        vertex.TShape().ChangePoints().Append(BRep_PointOnSurface(.125,.375,surface,TopLoc_Location()))
        original=_shape_brep_bytes(shape)
        digest,tree,cid,entry=self.component_tree(shape)
        self.assertEqual(entry['kind'],'native')
        self.assertEqual(entry['codec'],'breptools-ascii-v3')
        payload=read_verified_object(entry['brep'])
        decoded=cp._decode_brep(entry['codec'],payload)
        self.assertEqual(_shape_brep_bytes(decoded),original)
        self.assertEqual(ascii_v3_bytes(decoded),payload)
        self.assertEqual(facts_of(digest,cid),
                         extract_topology_facts(shape.wrapped))
        self.assertEqual(_shape_brep_bytes(materialize(digest)),original)
        for wrong in ('bintools-v4','bintools-v3'):
            with self.assertRaisesRegex(ValueError,'declared codec'):cp._decode_brep(wrong,payload)

    def test_face_recipe_canonical_bytes_are_stable_past_nine_ordinals(self):
        recipe={ordinal:(.2,.3,.4,1.) for ordinal in (1,2,10,11,75)}
        encoded=cp.canonical_json_bytes(recipe)
        self.assertEqual(encoded,cp.canonical_json_bytes(json.loads(encoded)))
        self.assertEqual(list(json.loads(encoded)),['1','10','11','2','75'])
        with self.assertRaisesRegex(ValueError,'duplicate canonical JSON key'):
            cp.canonical_json_bytes({1:'a','1':'b'})

    def test_native_facts_are_the_extractors(self):
        from build123d import Box, Cylinder, Solid
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
        from cadgen._internal.topology_extract import extract_topology_facts
        for shape in (Box(2, 3, 4), Box(4, 5, 3) - Cylinder(1, 6),
                      Solid(BRepBuilderAPI_NurbsConvert(Cylinder(2, 4).wrapped, True).Shape())):
            shape.cad_face_ordinal_colors = {1: (.2, .3, .4, 1.)}
            digest, tree, cid, entry = self.component_tree(shape)
            payload = read_verified_object(entry["brep"])
            self.assertEqual(payload, cp._shape_brep_bytes(shape))
            private = cp._build123d_shape_from_brep_bytes(payload)
            expected = extract_topology_facts(private.wrapped)
            self.assertEqual(facts_of(digest, cid), expected)

    def test_geometry_gc_retains_partial_closure_and_display_data_is_independent(self):
        from build123d import Box, Cylinder, Compound, Location
        from cadgen.store.gc import reachable_objects
        from cadgen.store.index import iter_entries, remove_entry
        from cadgen.store.records import document_key, note_document_tree
        from cadgen.store.trees import tree_complete
        shape = Compound(children=[Box(2, 3, 4), Cylinder(1, 4).moved(Location((8, 0, 0)))])
        digest, tree, _ = build_tree_from_compound(shape, root_name="root")
        note_document_tree("a" * 64, digest)
        resolved = part_objects(parts.derive(digest))
        for key, _ in list(iter_entries("component")):
            remove_entry("component", key)
        entries = list(tree["components"].values())
        object_path(entries[0]["brep"]).unlink()
        live = reachable_objects()
        self.assertIn(digest, live)
        self.assertIn(entries[1]["brep"], live)
        self.assertFalse(tree_complete(digest))
        self.assertTrue(all(row in live for row in resolved))
        remove_entry("document", document_key("a" * 64))
        live = reachable_objects()
        self.assertNotIn(digest, live)
        self.assertNotIn(entries[1]["brep"], live)
        self.assertTrue(all(row in live for row in resolved), "a part keeps its objects whatever the tree's fate")

    def test_document_hint_is_optional_coherent_and_not_in_geometry(self):
        from build123d import Box
        from cadgen.store.records import note_document_tree, document_entry_for_hash, note_document_mesh
        first = self.component_tree(Box(1, 2, 3))[0]
        second = self.component_tree(Box(2, 3, 4))[0]
        producer = parts.producer_identity()
        note_document_tree("a" * 64, first, producer=producer)
        note_document_mesh("a" * 64, "external", "f" * 64)
        with mock.patch.object(parts, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            note_document_tree("a" * 64, first, producer=producer)
            note_document_tree("a" * 64, first)
            selected = document_entry_for_hash("a" * 64)
            self.assertEqual(selected["producer"], producer)
            self.assertIn("meshes", selected)
            self.assertEqual(parts.view_from_geometry(first, capture_tree(first, retain_payloads=False)[0],
                                                      producer=producer)["tree"], first)
            note_document_tree("a" * 64, second)
        changed = document_entry_for_hash("a" * 64)
        self.assertNotIn("producer", changed)
        self.assertNotIn("meshes", changed)

    def test_every_same_brep_variant_validates_native_kind_and_effective_recipe(self):
        from build123d import Solid
        from cadgen.store.trees import IDENTITY_16
        shape = Solid.make_box(2, 3, 4)
        digest, source, cid, entry = self.component_tree(shape)
        from cadgen._internal.topology_facts import topology_facts_bytes
        surface = put_object(topology_facts_bytes(facts_of(digest, cid)))
        for mode in ("absent-face", "eager-only"):
            with self.subTest(mode=mode):
                tree = copy.deepcopy(source)
                variant = copy.deepcopy(entry)
                if mode == "absent-face":
                    # A colour on a face the body does not have: the kernel-free checks
                    # pass, the kernel's do not.
                    variant["faceColors"] = {999: (1., 0., 0., 1.)}
                    error = ValueError
                else:
                    # An eager-only component: its pinned facts stand in for a decode.
                    variant.update(kind="eager-only", topology=surface)
                    error = cp.NativeUnavailable
                payload = read_verified_object(entry["brep"])
                variant["contentHash"] = cp.geometry_component_hash(
                    variant["codec"], payload, variant["faceColors"], kind=variant["kind"],
                    topology=variant.get("topology"),
                )
                other = variant["contentHash"][:16]
                tree["components"][other] = variant
                tree["occurrences"] = [{"id": f"o1.{i}", "name": f"part{i}", "component": component,
                                        "transform": IDENTITY_16} for i, component in enumerate((cid, other), 1)]
                tree["assembly"] = {"root": {"id": "o1", "name": "root", "nodeType": "assembly", "children": [
                    {"id": f"o1.{i}", "name": f"part{i}", "nodeType": "part", "children": []} for i in (1, 2)]}}
                tree["entryKind"] = "assembly"
                tree = tokenized(tree)[0]
                flat, objects = capture_tree(put_object(cp.canonical_json_bytes(tree)))
                # Force native first so a later variant exercises the shared-BREP copy branch.
                flat["components"] = {cid: flat["components"][cid], other: flat["components"][other]}
                with self.assertRaises(error):
                    materialize_descriptor(flat, captured_objects=objects)
                if mode == "eager-only":
                    # The build's own shape for its eager-only component, which only its process
                    # holds: the document its STEP is written from is assembled with it.
                    document = materialize_descriptor(flat, captured_objects=objects, shapes={other: shape})
                    self.assertEqual(2, len(document.children))


if __name__ == "__main__":
    unittest.main()
