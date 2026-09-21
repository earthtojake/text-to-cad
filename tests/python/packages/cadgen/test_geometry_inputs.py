"""Geometry-complete publication and artifact-only surface readiness."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
add_repo_path("packages/cadgen/src")

from cadgen._internal import component_package as cp
from cadgen.store import surfaces
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


def store_component(shape, _unused=None, meta=None):
    prepared = cp.prepare_geometry_component(shape)
    entry = prepared["entry"]
    put_object(prepared["payload"], repair=True)
    if prepared["surface"] is not None:
        put_object(prepared["surface"], repair=True)
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

    def test_geometry_and_native_read_do_not_extract_surfaces(self):
        from cadgen._internal import surface_extract
        scene=self.scene(nested=True)
        with mock.patch.object(surface_extract, 'extract_surface_component', side_effect=AssertionError('SURF forbidden')):
            digest, tree=publish_document(scene)
            self.assertTrue(all(c['kind']=='native' for c in tree['components'].values()))
            shape=materialize(digest)
            self.assertGreater(shape.volume, 0)
            from cadgen._internal.step_scene_package import _scene_from_document_tree
            loaded=_scene_from_document_tree(scene.step_path,tree_hash=digest,step_hash=scene.step_hash)
            self.assertEqual(loaded.step_hash,scene.step_hash)
            self.assertFalse((self.root/'store/index/surface').exists())

    def test_surface_loss_never_blocks_geometry_and_repairs_exactly(self):
        from cadgen._internal import surface_extract
        digest,tree=publish_document(self.scene(nested=True))
        expected=surfaces.derive(digest)
        for result in expected.values(): object_path(result['object']).unlink()
        shutil.rmtree(self.root/'store/index/surface')
        with mock.patch.object(surface_extract,'extract_surface_component',side_effect=AssertionError('SURF forbidden')):
            self.assertGreater(materialize(digest).volume,0)
        self.assertEqual(surfaces.derive(digest),expected)
        first=next(iter(expected.values()))
        object_path(first['object']).write_bytes(b'corrupt')
        self.assertEqual(surfaces.derive(digest),expected)
        surfaces.validate_surface_bytes(read_verified_object(first['object']))

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

    def test_index_input_or_container_corruption_misses(self):
        from cadgen.store.index import read_entry,write_entry
        digest,tree=publish_document(self.scene())
        expected=surfaces.derive(digest)
        cid=next(iter(tree['components']));entry=tree['components'][cid]
        record=expected[cid]
        altered=copy.deepcopy(record);altered['producer']['ocp']='wrong'
        write_entry('surface',surfaces.surface_input(entry,surfaces.producer_identity()),altered)
        self.assertIsNone(surfaces.lookup(entry,surfaces.producer_identity()))
        self.assertEqual(surfaces.derive(digest),expected)
        broken=b'SURF'+struct.pack('<II',2,2)+b'{}'
        altered={**record,'object':put_object(broken)}
        write_entry('surface',surfaces.surface_input(entry,surfaces.producer_identity()),altered)
        self.assertIsNone(surfaces.lookup(entry,surfaces.producer_identity()))
        self.assertEqual(surfaces.derive(digest),expected)

    def test_surface_failure_never_publishes_readiness(self):
        from cadgen._internal import surface_extract
        digest,tree=publish_document(self.scene())
        with mock.patch.object(surface_extract,'extract_surface_component',side_effect=ValueError('injected extraction failure')):
            with self.assertRaisesRegex(ValueError,'injected'):surfaces.derive(digest)
        self.assertFalse((self.root/'store/index/surface').exists())
        self.assertGreater(materialize(digest).volume,0)

    def test_unknown_producer_cannot_share_persistent_namespace(self):
        with mock.patch('cadgen._internal.op_memo._runtime_versions',return_value=('1','unknown','1')):
            digest,tree=publish_document(self.scene())
            self.assertGreater(materialize(digest).volume,0)
            with self.assertRaises(ValueError):surfaces.derive(digest)
        self.assertFalse((self.root/'store/index/surface').exists())

    def test_surface_producer_requires_exact_integer_scheme_fields(self):
        producer = surfaces.producer_identity()
        for name in ("scheme", "surfFormat"):
            malformed = {**producer, name: float(producer[name])}
            with self.assertRaisesRegex(ValueError, "unsupported surface producer"):
                surfaces.producer_key(malformed)

    def test_geometry_identity_does_not_depend_on_surface_producer(self):
        scene=self.scene()
        first_hash,first=publish_document(scene)
        with mock.patch('cadgen._internal.op_memo._runtime_versions',return_value=('different','different','different')):
            second_hash,second=publish_document(scene)
            changed=surfaces.request_view(first_hash)
        normal=surfaces.request_view(first_hash)
        self.assertEqual((first_hash,first),(second_hash,second))
        self.assertNotEqual(normal['surfaceProducer'],changed['surfaceProducer'])
        cid=next(iter(first['components']))
        self.assertNotEqual(normal['components'][cid]['surfaceInput'],changed['components'][cid]['surfaceInput'])
        self.assertNotIn('surfaceProducer',first)
        self.assertNotIn('surfaceInput',first['components'][cid])

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
        digest=put_object(cp.canonical_json_bytes(tree))
        actual=materialize(digest)
        expected=self.emitted(actual,'colors-a.step')
        self.assertEqual(expected,self.emitted(materialize(digest),'colors-b.step'))
        from cadgen._internal.step_scene_package import load_step_scene_exact
        parsed=load_step_scene_exact(self.root/'colors-a.step')
        recipes=list(parsed.prototype_face_colors.values())
        self.assertEqual(len(recipes),2)
        self.assertNotEqual(list(recipes[0].values()),list(recipes[1].values()))

    def test_surface_producer_conflict_cannot_replace_expected_object(self):
        digest,tree=publish_document(self.scene())
        expected=surfaces.derive(digest)
        entry=next(iter(expected.values()))
        with self.assertRaisesRegex(ValueError,'producer conflict'):
            surfaces.derive(digest,force=True,expected_objects={entry['surfaceInput']:'0'*64})
        self.assertEqual(surfaces.derive(digest),expected)

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

    def test_surface_writers_use_only_artifacts_and_racing_bytes_agree(self):
        digest,tree=publish_document(self.scene())
        from cadgen.store import index
        original=index.read_entry
        def read(kind,key):
            if kind in {'model','output','op','component','document'}:
                raise AssertionError(f'forbidden index {kind}')
            return original(kind,key)
        with mock.patch.object(index,'read_entry',read),mock.patch.object(surfaces,'read_entry',read):
            expected=surfaces.derive(digest)
        for row in expected.values():object_path(row['object']).unlink()
        shutil.rmtree(self.root/'store/index/surface')
        code='from cadgen.store.surfaces import derive; import json,sys; print(json.dumps(derive(sys.argv[1]),sort_keys=True))'
        processes=[subprocess.Popen([sys.executable,'-c',code,digest],env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                   for _ in range(2)]
        for process in processes:
            out,error=process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,error)
            self.assertEqual(json.loads(out),json.loads(json.dumps(expected)))
        self.assertEqual(surfaces.derive(digest),expected)

    def point_box(self,parameter):
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
        vertex.TShape().ChangePoints().Append(BRep_PointOnCurve(parameter,curve,TopLoc_Location()))
        shape.cad_face_ordinal_colors={i:(i/7.,.2,.3,1.) for i in range(1,7)}
        return shape

    def test_actual_binary_throw_and_silent_loss_use_faithful_v3_artifacts(self):
        from cadgen._internal.component_package import _shape_brep_bytes
        from cadgen._internal.surface_extract import extract_surface_component
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
                records=surfaces.derive(digest)
                expected=extract_surface_component(original.wrapped,face_colors=original.cad_face_ordinal_colors)
                self.assertEqual(read_verified_object(records[cid]['object']),expected)
                self.assertEqual(records,surfaces.derive(digest,force=True))
                output=materialize(digest)
                self.assertEqual(_shape_brep_bytes(output),native_before)
                output.cad_face_ordinal_colors[1]=(0.,0.,0.,1.)
                self.assertEqual(_shape_brep_bytes(original),native_before)
                self.assertEqual(materialize(digest).cad_face_ordinal_colors[1],original.cad_face_ordinal_colors[1])

    def test_explicit_eager_surface_is_required_and_never_lazily_extracted(self):
        from build123d import Solid
        from cadgen._internal import component_package as _geometry_codec
        from cadgen._internal import surface_extract
        shape=Solid.make_box(2,3,4)
        with mock.patch.object(_geometry_codec,'_encode_brep',side_effect=_geometry_codec.CodecFidelityError('unsupported native fidelity')):
            digest,tree,cid,entry=self.component_tree(shape)
        self.assertEqual(entry['kind'],'eager-only')
        required=read_verified_object(entry['eagerSurface'])
        with mock.patch.object(surface_extract,'extract_surface_component',side_effect=AssertionError('live fallback forbidden')):
            first=surfaces.derive(digest)
            self.assertEqual(first[cid]['object'],entry['eagerSurface'])
            self.assertEqual(first,surfaces.derive(digest,force=True))
        object_path(entry['eagerSurface']).unlink()
        with self.assertRaises(FileNotFoundError):capture_tree(digest)
        with self.assertRaises(FileNotFoundError):surfaces.derive(digest)
        put_object(required,repair=True)
        self.assertEqual(first,surfaces.derive(digest))

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
        with self.assertRaisesRegex(ValueError,'declared codec'):surfaces.derive(digest)

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
        from cadgen._internal.surface_extract import extract_surface_component
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
        records=surfaces.derive(digest)
        self.assertEqual(read_verified_object(records[cid]['object']),
                         extract_surface_component(shape.wrapped,face_colors=shape.cad_face_ordinal_colors))
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

    def test_normal_surface_bytes_match_existing_extractor(self):
        from build123d import Box, Cylinder, Solid
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
        from cadgen._internal.surface_extract import extract_surface_component
        for shape in (Box(2, 3, 4), Box(4, 5, 3) - Cylinder(1, 6),
                      Solid(BRepBuilderAPI_NurbsConvert(Cylinder(2, 4).wrapped, True).Shape())):
            shape.cad_face_ordinal_colors = {1: (.2, .3, .4, 1.)}
            digest, tree, cid, entry = self.component_tree(shape)
            payload = read_verified_object(entry["brep"])
            self.assertEqual(payload, cp._shape_brep_bytes(shape))
            private = cp._build123d_shape_from_brep_bytes(payload)
            expected = extract_surface_component(private.wrapped, face_colors=shape.cad_face_ordinal_colors)
            self.assertEqual(read_verified_object(surfaces.derive(digest)[cid]["object"]), expected)

    def test_geometry_gc_retains_partial_closure_and_surface_is_independent(self):
        from build123d import Box, Cylinder, Compound, Location
        from cadgen.store.gc import reachable_objects
        from cadgen.store.index import iter_entries, remove_entry
        from cadgen.store.records import note_document_tree
        from cadgen.store.trees import tree_complete
        shape = Compound(children=[Box(2, 3, 4), Cylinder(1, 4).moved(Location((8, 0, 0)))])
        digest, tree, _ = build_tree_from_compound(shape, root_name="root")
        note_document_tree("a" * 64, digest)
        resolved = surfaces.derive(digest)
        for key, _ in list(iter_entries("component")):
            remove_entry("component", key)
        entries = list(tree["components"].values())
        object_path(entries[0]["brep"]).unlink()
        live = reachable_objects()
        self.assertIn(digest, live)
        self.assertIn(entries[1]["brep"], live)
        self.assertFalse(tree_complete(digest))
        self.assertTrue(all(row["object"] in live for row in resolved.values()))
        remove_entry("document", "a" * 64)
        live = reachable_objects()
        self.assertNotIn(digest, live)
        self.assertNotIn(entries[1]["brep"], live)
        self.assertTrue(all(row["object"] in live for row in resolved.values()))

    def test_document_hint_is_optional_coherent_and_not_in_geometry(self):
        from build123d import Box
        from cadgen.store.records import note_document_tree, document_entry_for_hash, note_document_mesh
        first = self.component_tree(Box(1, 2, 3))[0]
        second = self.component_tree(Box(2, 3, 4))[0]
        producer = surfaces.producer_identity()
        note_document_tree("a" * 64, first, surface_producer=producer)
        note_document_mesh("a" * 64, "external", "f" * 64)
        with mock.patch.object(surfaces, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            note_document_tree("a" * 64, first, surface_producer=producer)
            note_document_tree("a" * 64, first)
            selected = document_entry_for_hash("a" * 64)
            self.assertEqual(selected["surfaceProducer"], producer)
            self.assertIn("meshes", selected)
            self.assertEqual(surfaces.request_view(first, producer=producer)["tree"], first)
            note_document_tree("a" * 64, second)
        changed = document_entry_for_hash("a" * 64)
        self.assertNotIn("surfaceProducer", changed)
        self.assertNotIn("meshes", changed)

    def test_every_same_brep_variant_validates_native_kind_and_effective_recipe(self):
        from build123d import Solid
        from cadgen.store.trees import IDENTITY_16
        from cadgen.store._descriptor_bounds import Snapshot
        shape = Solid.make_box(2, 3, 4)
        digest, source, cid, entry = self.component_tree(shape)
        surface = surfaces.derive(digest)[cid]["object"]
        for mode in ("absent-face", "eager-only"):
            with self.subTest(mode=mode):
                tree = copy.deepcopy(source)
                variant = copy.deepcopy(entry)
                if mode == "absent-face":
                    variant["faceColors"] = {999: (1., 0., 0., 1.)}
                    error = ValueError
                else:
                    variant.update(kind="eager-only", eagerSurface=surface)
                    error = cp.NativeUnavailable
                payload = read_verified_object(entry["brep"])
                variant["contentHash"] = cp.geometry_component_hash(
                    variant["codec"], payload, variant["faceColors"], kind=variant["kind"],
                    eager_surface=variant.get("eagerSurface"),
                )
                other = variant["contentHash"][:16]
                tree["components"][other] = variant
                tree["occurrences"] = [{"id": f"o1.{i}", "name": f"part{i}", "component": component,
                                        "transform": IDENTITY_16} for i, component in enumerate((cid, other), 1)]
                tree["assembly"] = {"root": {"id": "o1", "name": "root", "nodeType": "assembly", "children": [
                    {"id": f"o1.{i}", "name": f"part{i}", "nodeType": "part", "children": []} for i in (1, 2)]}}
                tree["entryKind"] = "assembly"
                flat, objects = capture_tree(put_object(cp.canonical_json_bytes(tree)))
                # Force native first so a later variant exercises the shared-BREP copy branch.
                flat["components"] = {cid: flat["components"][cid], other: flat["components"][other]}
                with self.assertRaises(error):
                    materialize_descriptor(flat, captured_objects=objects)
                snapshot = Snapshot(json.dumps(flat).encode(), tuple(objects.items()), (),
                                    tuple((key, value["brep"]) for key, value in flat["components"].items())).capture_appearance()
                with self.assertRaises(error):
                    snapshot.prepare_document()
                if mode == "eager-only":
                    with self.assertRaises(cp.NativeUnavailable):
                        materialize_descriptor(flat, shapes={cid: shape, other: shape})

    def test_nonfinite_surface_index_fields_are_optional_misses_even_for_force(self):
        from build123d import Solid
        from cadgen.store.index import write_entry
        digest, tree, cid, entry = self.component_tree(Solid.make_box(2, 3, 4))
        expected = surfaces.derive(digest)
        for value in (float("nan"), float("inf")):
            record = copy.deepcopy(expected[cid])
            record["faceColors"] = {"1": [value, 0, 0, 1]}
            write_entry("surface", record["surfaceInput"], record)
            self.assertIsNone(surfaces.lookup(entry, surfaces.producer_identity()))
            self.assertEqual(surfaces.derive(digest, force=True), expected)

if __name__ == "__main__":
    unittest.main()
