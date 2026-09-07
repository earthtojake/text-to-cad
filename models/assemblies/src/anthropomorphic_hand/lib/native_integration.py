"""Frozen native occurrences with provenance, for inexpensive final integration.

The original procedural factories remain the design source. This native cache
avoids rebuilding several thousand accepted parts when a small subsystem moves.
"""
from pathlib import Path
import json,hashlib,shutil
from cadgen import read_step,srgb
from lib.assembly import Body
from lib.finish import FINISHES

ROOT=Path(__file__).resolve().parents[3]

def appearance(shape,record):
    if 'color' in record:shape.color=tuple(record['color'])
    if 'material' in record:shape.cad_material=dict(record['material'])

def leaves(node):
    return [leaf for child in node.children for leaf in leaves(child)] if node.children else [node]

def frozen_bodies(include_variable=True):
    report=json.loads((ROOT/'validation/anthropomorphic_hand/integration_native_base_certificate.json').read_text())
    source=ROOT/'STEP/anthropomorphic_hand/imported/integration_native_base.step'
    meta=ROOT/'validation/anthropomorphic_hand/integration_native_base_frames.json'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==report['step_sha256']
    assert hashlib.sha256(meta.read_bytes()).hexdigest()==report['metadata_sha256']
    mapping={r['name']:r for r in json.loads(meta.read_text())}
    styles=json.loads((ROOT/'validation/anthropomorphic_hand/integration_native_base_appearance.json').read_text())['occurrences']
    native=leaves(read_step(source))
    assert len(native)==len(mapping)==report['body_count']
    bodies=[]
    for shape in native:
        row=mapping[shape.label]
        if not include_variable and row['frame']=='variable':continue
        appearance(shape,styles[shape.label])
        body=Body(shape,row['frame'],row['system'],row['kind'])
        body.source_sha256=report['step_sha256'];body.source_path=str(source)
        bodies.append(body)
    return bodies

def overlay(bodies,step_path,records,expected_sha=None,replace=False):
    """Add or replace explicitly named native bodies, preserving rigid frames."""
    step_path=Path(step_path)
    payload=step_path.read_bytes()
    actual_sha=hashlib.sha256(payload).hexdigest()
    if expected_sha:assert actual_sha==expected_sha
    expected_sha=actual_sha
    archive=ROOT/'STEP/anthropomorphic_hand/imported/revisions'/f'{actual_sha}.step'
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():archive.write_bytes(payload)
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==actual_sha
    style_file=ROOT/'validation/anthropomorphic_hand/native_overlay_appearance.json'
    styles=json.loads(style_file.read_text()).get(expected_sha,{}) if style_file.exists() else {}
    native=leaves(read_step(archive));mapping={r['name']:r for r in records}
    assert len(native)==len(mapping)
    assert {s.label for s in native}==set(mapping)
    existing={b.name:b for b in bodies}
    if replace:assert set(mapping)<=set(existing)
    else:assert not set(mapping)&set(existing)
    for shape in native:
        row=mapping[shape.label]
        color=tuple(shape.color)[:3] if shape.color is not None else tuple(srgb(FINISHES['aluminum'][0]))[:3]
        language=min(FINISHES,key=lambda key:sum((a-b)**2 for a,b in zip(color,tuple(srgb(FINISHES[key][0]))[:3])))
        shape.cad_material=dict(FINISHES[language][1])
        if shape.label in styles:appearance(shape,styles[shape.label])
        body=Body(shape,row['frame'],row['system'],row['kind'])
        body.source_sha256=actual_sha
        body.source_path=str(archive)
        existing[shape.label]=body
    return list(existing.values())

def integrated_native_bodies():
    bodies=frozen_bodies()
    folder=ROOT/'STEP/anthropomorphic_hand'
    cradle=[{'name':'wrist_palm_cradle','frame':'wrist_flexion','system':'wrist','kind':'frame'}]
    bodies=overlay(bodies,folder/'palm_cradle_clearance_review.step',cradle,
        '8f5f9beb5456a6df38ad07609f71f596935806e2309a6b5befc56159f389e525',True)
    palm=json.loads((ROOT/'validation/anthropomorphic_hand/palm_hardware_placements.json').read_text())
    bodies=overlay(bodies,folder/'palm_hardware_review.step',palm['bodies'],palm['sha256'])
    old_wrist=[b for b in bodies if b.name.startswith(('wrist_abduction_drive_mouth','wrist_flexion_drive_mouth','palm_cup_drive_mouth','palm_cup_shared_drive_mouth'))]
    assert len(old_wrist)==30
    removed={b.name for b in old_wrist};bodies=[b for b in bodies if b.name not in removed]
    wrist=json.loads((ROOT/'validation/anthropomorphic_hand/wrist_guide_frames.json').read_text())
    assert wrist['body_count']==29
    bodies=overlay(bodies,folder/'wrist_guide_mounts_review.step',wrist['bodies'],wrist['sha256'])
    phalanges=json.loads((ROOT/'validation/anthropomorphic_hand/phalanx_beauty_frames.json').read_text())
    bodies=overlay(bodies,folder/'phalanx_beauty_review.step',phalanges,
        '73e22e401693dc33cd772cb8874923bbd4efd65bcc15c63da192e5fc46cee803',True)
    for family in ('cup_guide','thumb_base'):
        manifest=json.loads((ROOT/f'validation/anthropomorphic_hand/{family}_frames.json').read_text())
        bodies=overlay(bodies,Path(manifest['step']),manifest['bodies'],manifest['sha256'])
    cmc=json.loads((ROOT/'validation/anthropomorphic_hand/thumb_cmc_frames.json').read_text())
    bodies=overlay(bodies,folder/'thumb_cmc_mounts_review.step',cmc['bodies'],cmc['sha256'],True)
    banks=json.loads((ROOT/'validation/anthropomorphic_hand/palm_bank_frames.json').read_text())
    old_banks={b.name for b in bodies if '_palm_bank_' in b.name}
    assert len(old_banks)==67
    bodies=[b for b in bodies if b.name not in old_banks]
    bodies=overlay(bodies,folder/'palm_guide_mounts_review.step',banks['bodies'],banks['sha256'])
    combs=json.loads((ROOT/'validation/anthropomorphic_hand/phalanx_comb_clearance_frames.json').read_text())
    old_combs={b.name for b in bodies if any(role in b.name for role in
        ('_mcp_outlet_comb_','_pip_inlet_comb_','_pip_outlet_comb_')) and b.system in ('index','middle','ring','little')}
    assert len(old_combs)==112
    bodies=[b for b in bodies if b.name not in old_combs]
    bodies=overlay(bodies,folder/'phalanx_comb_clearance_review.step',combs,
        '5b0c28e93e903292cc15b72c51576871f6b47a43962cbff3e68140c6477fdeb7')
    hardware=json.loads((ROOT/'validation/anthropomorphic_hand/positive_yaw_hardware_build_handoff.json').read_text())
    for item in hardware.values():
        records=json.loads(Path(item['frames']).read_text())
        bodies=overlay(bodies,Path(item['step']),records,item['sha256'],True)
    ring_manifest=ROOT/'validation/anthropomorphic_hand/cmc_dorsal_ring_frames.json'
    ring_step=folder/'cmc_dorsal_ring_review.step'
    bodies=overlay(bodies,ring_step,json.loads(ring_manifest.read_text()),
        hashlib.sha256(ring_step.read_bytes()).hexdigest(),True)
    for filename,name,frame,sha in [
        ('palm_main_final_rom_review.step','palm_metacarpal_truss','wrist_flexion','6c2e669df4f176c530c5b1c8623c861b942ca60d1e75cb346bd2548f6a32adf4'),
        ('palm_little_comb_rom_review.step','fifth_metacarpal_cupping_truss','palm_cup','0cbb95eaad8463d34ce50a9eae879d01cb4c02adb56ae2531b01c2278477f015')]:
        records=[dict(name=name,frame=frame,system='palm',kind='frame')]
        bodies=overlay(bodies,folder/filename,records,sha,True)
    carrier=json.loads((ROOT/'validation/anthropomorphic_hand/cmc_carrier_relief_frames.json').read_text())
    bodies=overlay(bodies,folder/'cmc_carrier_relief_review.step',carrier,
        '7cb5ef97a37a9fdf06bf779cb4da35c518d63e6a73ed30685944d9efdf3a0173',True)
    dorsal=json.loads((ROOT/'validation/anthropomorphic_hand/compact_mcp_dorsal_frames.json').read_text())
    bodies=overlay(bodies,folder/'compact_mcp_dorsal_review.step',dorsal,
        'ac473c6bb5232953145594bb57164eac1a5ded80024f391645e5d7335861faf0',True)
    return bodies
