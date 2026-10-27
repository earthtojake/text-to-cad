"""Materials for the Moonwatch model entries.

The original authored named PBR "finishes" (`materials=` on the decorator,
assigned by leaf label). Here each finish is a `bd_materials.FinishedMaterial` set on
the part itself: the catalogue's entry for the metal, glass or rubber in
question, in the finish's look (explicit scalar `PbrProperties`), or the project's
own where the catalogue has none (sapphire, ruby, print ink). A
finish keeps the original's metalness, roughness and clearcoat (`clearcoat`,
`clearcoat_roughness`) and its old name as the description, and takes the look
fields its name implies: brushed, satin and grained steel are anisotropic
along their grain, a mirror polish is at most 0.1 rough, a polish has no
grain, and the crystal, the sapphire back and the jewels transmit light at
their index (sapphire and ruby, corundum, at 1.77), tinted by the part's own
colour. Assignments restore the authored colour after setting the native material,
so a part stays the colour its builder authored (the STEP document remained the
source of base colour then too).

Assignments use unique authored leaf labels, so factory edits cannot silently
retarget a finish through occurrence order.
"""

from __future__ import annotations

from bd_materials import FinishedMaterial, glass, metals
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties


# Corundum, the stone of a jewel and of a sapphire crystal: 3980 kg/m^3, index 1.77.
SAPPHIRE = FinishedMaterial(
    RangeMaterial(name='Sapphire', density=3980.0),
    pbr=PbrProperties.create('Glass Back', metalness=0.0, roughness=0.03, ior=1.77, transmission=1.0,
        clearcoat=0.02, clearcoat_roughness=0.05),
)
RUBY = FinishedMaterial(
    RangeMaterial(name='Ruby', density=3980.0),
    pbr=PbrProperties.create('Ruby Jewel (synthetic corundum)', metalness=0.0, roughness=0.05,
        ior=1.77, transmission=0.8, clearcoat=1.0, clearcoat_roughness=0.03),
)
PRINT_INK = FinishedMaterial(
    RangeMaterial(name='Matte Print', density=None),
    pbr=PbrProperties.create('printed ink, no density', metalness=0.0, roughness=0.85),
)
# The dial's lacquer and lume: coatings, no density of their own.
BLACK_LACQUER = FinishedMaterial(
    RangeMaterial(name='Black Lacquer', density=None),
    pbr=PbrProperties.create('Black Lacquer', metalness=0.0, roughness=0.52, clearcoat=0.35,
        clearcoat_roughness=0.15),
)
LUME = FinishedMaterial(
    RangeMaterial(name='Lume Plot', density=None),
    pbr=PbrProperties.create('Lume Plot (luminous paint)', metalness=0.0, roughness=0.65,
        clearcoat=0.15, clearcoat_roughness=0.3),
)

FINISHES = {
    # old finish name: material (a catalogue entry in the finish, or the project's own)
    "anglage_mirror": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Anglage Mirror', metalness=0.9, roughness=0.1, clearcoat=0.2,
            clearcoat_roughness=0.08),
    ),
    "bezel_anodized": FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Bezel Anodized', metalness=0.35, roughness=0.5, clearcoat=0.2,
            clearcoat_roughness=0.3),
    ),
    "blued_screw": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Blued Screw', metalness=0.9, roughness=0.14, clearcoat=0.25,
            clearcoat_roughness=0.08),
    ),
    "brass_part": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Brass Part', metalness=0.9, roughness=0.38),
    ),
    "brushed_steel": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Brushed Steel', metalness=0.9, roughness=0.5, anisotropy=0.5),
    ),
    "case_mirror_polish": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Case Mirror Polish', metalness=0.95, roughness=0.08, clearcoat=0.3,
            clearcoat_roughness=0.05),
    ),
    # copper-plated brass bridges
    "copper_plate": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Copper Plate', metalness=0.9, roughness=0.34, clearcoat=0.08,
            clearcoat_roughness=0.3),
    ),
    # gilded brass wheels
    "gilt_wheel": FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Gilt Wheel', metalness=0.95, roughness=0.24, clearcoat=0.1,
            clearcoat_roughness=0.15),
    ),
    "glass": FinishedMaterial(
        glass.soda_lime().material,
        pbr=PbrProperties.create('Glass', metalness=0.0, roughness=0.05, ior=1.52, transmission=1.0,
            clearcoat=0.3, clearcoat_roughness=0.05, attenuation_color=(0.822786, 0.930111, 0.871367),
            attenuation_distance=0.05),
    ),
    "glass_back": SAPPHIRE,
    "grained_lever": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Grained Lever', metalness=0.95, roughness=0.34, anisotropy=0.5,
            clearcoat=0.08, clearcoat_roughness=0.2),
    ),
    "matte_print": PRINT_INK,
    "polished_steel": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Polished Steel', metalness=0.92, roughness=0.12, clearcoat=0.25,
            clearcoat_roughness=0.08),
    ),
    "rubber": FinishedMaterial(
        RangeMaterial(name='NBR 70A', density=1250.0),
        pbr=PbrProperties.create('Rubber (nitrile gaskets)', metalness=0.0, roughness=0.9),
    ),
    "ruby_jewel": RUBY,
    "satin_steel": FinishedMaterial(
        metals.stainless().material,
        pbr=PbrProperties.create('Satin Steel', metalness=0.95, roughness=0.3, anisotropy=0.4, clearcoat=0.1,
            clearcoat_roughness=0.2),
    ),
    # the dial, the hands and the bracelet's polished centre links
    "black_lacquer": BLACK_LACQUER,
    "dial_polished_furniture": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Dial Polished Furniture', metalness=0.95, roughness=0.1, clearcoat=0.2,
            clearcoat_roughness=0.08),
    ),
    "lume_plot": LUME,
    # painted steel hands
    "painted_hand": FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Painted Hand', metalness=0.25, roughness=0.28, clearcoat=0.6,
            clearcoat_roughness=0.1),
    ),
    "polished_link": FinishedMaterial(
        metals.stainless(metals.Stainless.G316L_ANNEALED).material,
        pbr=PbrProperties.create('Polished Link', metalness=0.88, roughness=0.22, clearcoat=0.15,
            clearcoat_roughness=0.1),
    ),
}

MODEL_MATERIAL_ASSIGNMENTS = {
    "bracelet": [
        {"targets": ["#end_link_12", "#end_link_6",
                     *[f"#link_{side}_r{row}_{part}" for side, rows in (("12", 6), ("6", 5))
                       for row in range(1, rows + 1) for part in ("left", "right")],
                     "#clasp_body", "#clasp_cover", "#clasp_spring_blade", "#clasp_hinge_knuckle"],
         "material": "brushed_steel"},
        {"targets": [*[f"#link_{side}_r{row}_center" for side, rows in (("12", 6), ("6", 5))
                       for row in range(1, rows + 1)],
                     "#clasp_pusher_right", "#clasp_pusher_left", "#clasp_flip_lock"],
         "material": "polished_link"},
        {"targets": ["#spring_bar_12", "#spring_bar_6", *[f"#pin_12_j{k}" for k in range(1, 8)],
                     *[f"#pin_6_j{k}" for k in range(1, 7)]],
         "material": "satin_steel"},
    ],
    "dial": [
        {"targets": ["#dial_plate", "#subdial_floor:minutes30", "#subdial_floor:hours12", "#subdial_floor:seconds"],
         "material": "black_lacquer"},
        {"targets": ["#dial_foot:upper", "#dial_foot:lower"], "material": "brass_part"},
        {"targets": ["#index_frame:batons"], "material": "dial_polished_furniture"},
        {"targets": ["#hand:hour_lume", "#hand:minute_lume", "#index_lume"], "material": "lume_plot"},
        {"targets": ["#subdial_print:minutes30", "#subdial_print:hours12", "#subdial_print:seconds",
                     "#minute_track"],
         "material": "matte_print"},
        {"targets": ["#hand:hour", "#hand:minute", "#hand:chrono_seconds", "#hand:sub_minutes30",
                     "#hand:sub_hours12", "#hand:sub_seconds"],
         "material": "painted_hand"},
        {"targets": ["#hub:hour", "#hub:minute", "#hand:chrono_cap"], "material": "polished_steel"},
    ],
    # The sampler had no assignments: each coupon takes its movement counterpart's finish.
    "finishing_sampler": [
        {"targets": ["#striped_bridge_coupon", "#perlage_plate_coupon"], "material": "copper_plate"},
        {"targets": ["#bridge_jewel"], "material": "ruby_jewel"},
        {"targets": ["#blued_screw"], "material": "blued_screw"},
        {"targets": ["#snailed_wheel", "#train_wheel"], "material": "gilt_wheel"},
        {"targets": ["#pinion", "#heart_cam"], "material": "polished_steel"},
    ],
    "case": [
        {"targets": ["#bezel_insert"], "material": "bezel_anodized"},
        {"targets": ["#case_middle", "#caseback"], "material": "brushed_steel"},
        {"targets": ["#case_polish:lug_ne", "#case_polish:lug_nw", "#case_polish:lug_se",
                     "#case_polish:lug_sw", "#case_polish:bezel", "#case_polish:band_lower"],
         "material": "case_mirror_polish"},
        {"targets": ["#crystal"], "material": "glass"},
        {"targets": ["#caseback_sapphire"], "material": "glass_back"},
        {"targets": ["#tachymeter_scale"], "material": "matte_print"},
        {"targets": ["#crown", "#crown_tube", "#pusher_cap:2oclock", "#pusher_tube:2oclock",
                     "#pusher_cap:4oclock", "#pusher_tube:4oclock", "#bezel_ring"],
         "material": "polished_steel"},
        {"targets": ["#caseback_o_ring", "#crown_o_ring", "#pusher_o_ring:2oclock",
                     "#pusher_o_ring:4oclock", "#crystal_gasket"],
         "material": "rubber"},
        {"targets": ["#pusher_spring:2oclock", "#pusher_spring:4oclock", "#spring_bar:12",
                     "#spring_bar:6", "#caseback_retaining_ring"],
         "material": "satin_steel"},
    ],
    "keyless_works": [
        {"targets": ["#screw:setting_lever_spring:1", "#screw:setting_lever_spring:2"],
         "material": "blued_screw"},
        {"targets": ["#minute_wheel", "#hour_wheel"], "material": "gilt_wheel"},
        {"targets": ["#setting_lever", "#yoke", "#setting_lever_spring"], "material": "grained_lever"},
        {"targets": ["#stem", "#minute_wheel_pinion", "#winding_pinion", "#sliding_pinion",
                     "#cannon_pinion"],
         "material": "polished_steel"},
    ],
    "movement_base": [
        {"targets": ["#barrel_bridge:anglage:0", "#barrel_bridge:anglage:1",
                     "#barrel_bridge:anglage:2", "#barrel_bridge:anglage:3",
                     "#barrel_bridge:anglage:4", "#train_bridge:anglage:0",
                     "#train_bridge:anglage:1", "#pallet_bridge:anglage"],
         "material": "anglage_mirror"},
        {"targets": ["#screw:stud_holder", "#screw:barrel_bridge:left", "#screw:barrel_bridge:right",
                     "#screw:barrel_bridge:top", "#screw:train_bridge:foot",
                     "#screw:train_bridge:fourth", "#screw:train_bridge:center", "#screw:ratchet",
                     "#screw:crown_wheel", "#screw:click", "#screw:click_spring",
                     "#screw:pallet_bridge", "#screw:balance_cock"],
         "material": "blued_screw"},
        {"targets": ["#barrel_drum", "#shock_chaton", "#barrel_lid", "#chaton:center",
                     "#chaton:third", "#chaton:fourth", "#chaton:escape", "#chaton:pallet"],
         "material": "brass_part"},
        {"targets": ["#main_plate", "#barrel_bridge", "#barrel_bridge:stripe_shadow:0",
                     "#barrel_bridge:stripe_shadow:1", "#barrel_bridge:stripe_shadow:2",
                     "#barrel_bridge:stripe_shadow:3", "#barrel_bridge:stripe_shadow:4",
                     "#barrel_bridge:stripe_shadow:5", "#train_bridge",
                     "#train_bridge:stripe_shadow:0", "#train_bridge:stripe_shadow:1",
                     "#train_bridge:stripe_shadow:2", "#pallet_bridge",
                     "#pallet_bridge:stripe_shadow:0", "#pallet_bridge:stripe_shadow:1",
                     "#balance_cock", "#balance_cock:stripe_shadow:0",
                     "#balance_cock:stripe_shadow:1"],
         "material": "copper_plate"},
        {"targets": ["#center_wheel", "#third_wheel", "#fourth_wheel", "#ratchet_wheel",
                     "#escape_wheel", "#balance_wheel", *[f"#timing_screw:{i}" for i in range(16)]],
         "material": "gilt_wheel"},
        {"targets": ["#click", "#click_spring", "#pallet_fork"], "material": "grained_lever"},
        {"targets": ["#stud_holder", "#shock_bezel", "#balance_lower_shock_ring", "#shock_lyre_spring",
                     "#regulator", "#barrel_arbor", "#center_pinion", "#third_pinion", "#fourth_pinion",
                     "#escape_pinion", "#crown_wheel", "#crown_wheel_core", "#pallet_arbor",
                     "#balance_staff"],
         "material": "polished_steel"},
        {"targets": ["#shock_cap_jewel", "#plate_jewel:center", "#plate_jewel:third",
                     "#bridge_jewel:barrel", "#plate_jewel:fourth", "#bridge_jewel:center",
                     "#bridge_jewel:third", "#bridge_jewel:fourth", "#bridge_jewel:escape",
                     "#plate_jewel:escape", "#plate_jewel:pallet", "#pallet_stone:entry",
                     "#pallet_stone:exit", "#plate_jewel:balance", "#bridge_jewel:pallet",
                     "#balance_lower_cap_jewel", "#impulse_jewel"],
         "material": "ruby_jewel"},
        {"targets": ["#mainspring", "#hairspring", "#hairspring_stud"], "material": "satin_steel"},
    ],
    # The original's chronograph works had no assignments: its finishes by the same rules
    # as the base's, from what each part's colour says it is.
    "chrono_works": [
        {"targets": ["#chrono_bridge:anglage:0", "#chrono_bridge:anglage:1", "#coupling_bridge:anglage"],
         "material": "anglage_mirror"},
        {"targets": ["#screw:column_wheel", "#screw:minute_jumper", "#screw:minute_jumper_spring",
                     "#screw:coupling_wheel", "#screw:clutch_spring", "#screw:hammer",
                     "#screw:operating_lever", "#screw:operating_spring", "#screw:reset_lever",
                     "#screw:reset_spring", "#screw:brake_lever", "#screw:brake_spring",
                     "#screw:chrono_bridge:east", "#screw:chrono_bridge:south",
                     "#screw:chrono_bridge:west", "#screw:coupling_bridge"],
         "material": "blued_screw"},
        {"targets": ["#chaton:chrono_runner", "#chaton:minute_recorder", "#chaton:coupling"],
         "material": "brass_part"},
        {"targets": ["#chrono_bridge", "#coupling_bridge",
                     *[f"#chrono_bridge:stripe_shadow:{i}" for i in range(6)],
                     *[f"#coupling_bridge:stripe_shadow:{i}" for i in range(3)]],
         "material": "copper_plate"},
        {"targets": ["#chrono_runner_wheel", "#minute_recorder_wheel", "#hour_recorder_wheel",
                     "#clutch_driving_wheel", "#coupling_wheel"],
         "material": "gilt_wheel"},
        {"targets": ["#column_wheel", "#minute_jumper", "#clutch_arm", "#operating_lever",
                     "#reset_lever", "#brake_lever"],
         "material": "grained_lever"},
        {"targets": ["#column_wheel_cap", "#chrono_runner_heart_cam", "#minute_recorder_heart_cam",
                     "#hour_recorder_heart_cam", "#hammer_yoke", "#chrono_runner_arbor",
                     "#clutch_driving_arbor", "#minute_recorder_post", "#hour_recorder_post",
                     "#stud:minute_jumper", "#stud:minute_jumper_spring", "#stud:coupling_wheel",
                     "#stud:clutch_spring", "#stud:hammer", "#stud:operating_lever",
                     "#stud:operating_spring", "#stud:reset_lever", "#stud:reset_spring",
                     "#stud:brake_lever", "#stud:brake_spring"],
         "material": "polished_steel"},
        {"targets": ["#bridge_jewel:chrono_runner", "#bridge_jewel:minute_recorder", "#bridge_jewel:coupling"],
         "material": "ruby_jewel"},
        {"targets": ["#minute_jumper_spring", "#hour_recorder_friction_spring", "#clutch_spring",
                     "#operating_spring", "#reset_spring", "#brake_spring"],
         "material": "satin_steel"},
    ],
}


def _leaves(shape):
    children = list(getattr(shape, "children", ()) or ())
    if not children:
        yield shape
    for child in children:
        yield from _leaves(child)


def apply_materials(parts, model: str):
    """Set each assigned leaf's material (the old ``materials=`` pass) on the finished
    parts, before they are composed; returns the parts, and raises naming any label an
    assignment names that no leaf carries."""
    wanted = {target.lstrip("#"): FINISHES[rule["material"]]
              for rule in MODEL_MATERIAL_ASSIGNMENTS[model] for target in rule["targets"]}
    found = set()
    for leaf in (leaf for part in parts for leaf in _leaves(part)):
        material = wanted.get(leaf.label)
        if material is not None:
            color = leaf.color
            leaf.material = material
            leaf.color = color
            found.add(leaf.label)
    missing = sorted(set(wanted) - found)
    if missing:
        raise ValueError(f"{model}: no part is labelled {', '.join(missing)}")
    return parts
