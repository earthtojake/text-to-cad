# Mechanism STEP Demos

Flattened STEP mechanism assemblies inspired by the YouTube channel
[thang010146](https://www.youtube.com/@thang010146/videos). Original
mechanism design, animation, and downloadable source files are credited to
`thang010146`.

This folder is intentionally flat so CAD Viewer can catalog the top-level STEP
assemblies and their sidecars directly.

## Contents

- `*.step`: canonical mechanism assemblies.
- `__cadgen__/`: per-folder cadgen output home written beside the sources,
  holding the generated content-addressed render/selector package for each
  STEP file. Gitignored and rebuilt on demand — never commit it.
- `<name>.step.js`: optional JS parameter/animation sidecar for an imported
  STEP. CAD Viewer picks it up by name — a `.js` sitting beside `<name>.step`
  — so an imported assembly gets parameters without a generator standing in
  for it. This is viewer-only; nothing in the CAD pipeline reads it.

Extracted source archives, Inventor files, SDF working files, videos, and
intermediate generation scripts are intentionally omitted from this fixture
bundle.

## Manifest

The render/selector package (generated under `__cadgen__/`) is built on demand
for every mechanism and is omitted from this table; the optional params sidecar
is listed per mechanism below.

| Mechanism | STEP | Params sidecar | Source |
|---|---|---|---|
| 180 deg. flip mechanism | [180_degree_flip_mechanism.step](180_degree_flip_mechanism.step) | `180_degree_flip_mechanism.step.js` | [Video](https://www.youtube.com/watch?v=IGexfslM_5Y), [STEP archive](https://www.mediafire.com/file/pcjk004x96r6ibu/180FlipMechanismSTEP.zip/file) |
| Table of adjustable height 2 | [adjustable_height_table_2.step](adjustable_height_table_2.step) | `adjustable_height_table_2.step.js` | [Video](https://www.youtube.com/watch?v=c30g2UszMws), [STEP archive](https://www.mediafire.com/file/ulf0n6zbbp1veo4/TableAdjustHeight2STEP.zip/file) |
| Circular window iris shutter 2 | [circular_iris_shutter_2.step](circular_iris_shutter_2.step) |  | [Video](https://www.youtube.com/watch?v=4ckPpHpe4TM), [STEP archive](https://www.mediafire.com/file/sz86hz0w9aknnen/CircularIrisShutter2STEP.zip/file) |
| Deployable drone | [deployable_drone.step](deployable_drone.step) |  | [Video](https://www.youtube.com/watch?v=QYt_wUP52T0), [STEP archive](https://www.mediafire.com/file/7533syysab1zhrg/DeployableDroneSTEP.zip/file) |
| Robot gripper of gear-rack drives | [gear_rack_gripper.step](gear_rack_gripper.step) | `gear_rack_gripper.step.js` | [Video](https://www.youtube.com/watch?v=CP5q6YxyeQ8), user upload `RobotGripperGearRackSTEP.zip` |
| Hinge of 2 DoF | [hinge_2_dof.step](hinge_2_dof.step) |  | [Video](https://www.youtube.com/watch?v=Mvmi2AyNqx0), [STEP archive](https://www.mediafire.com/file/nl2m3asaa31dvnf/Hinge2DoFSTEP.zip/file) |
| Kinetic pyramid facade | [kinetic_pyramid_facade.step](kinetic_pyramid_facade.step) |  | [Video](https://www.youtube.com/watch?v=wA9d9uJIBGw), [STEP archive](https://www.mediafire.com/file/vri2hopfzj0k731/KineticPyramidFacadeSTEP.zip/file) |
| Knuckle joint press | [knuckle_joint_press.step](knuckle_joint_press.step) |  | [Video](https://www.youtube.com/watch?v=Vd-vErlQPPk), [STEP archive](https://www.mediafire.com/file/8cy26hg2dlovi1b/KnuckleJointPressSTEP.zip/file) |
| Meat hash machine | [meat_hash_machine.step](meat_hash_machine.step) |  | [Video](https://www.youtube.com/watch?v=QVlepLAtYJk), [STEP archive](https://www.mediafire.com/file/q1hksit7cbdm8c6/MeatHashMachineSTEP.zip/file) |
| Object moving along 8-shaped runway | [object_8_shaped_runway.step](object_8_shaped_runway.step) |  | [Video](https://www.youtube.com/watch?v=KUD4qqCNmZk), [STEP archive](https://www.mediafire.com/file/lrpeog3wavxumek/Object8runwaySTEP.zip/file) |
| Planetary gearless mechanism 2 | [planetary_gearless_mechanism_2.step](planetary_gearless_mechanism_2.step) |  | [Video](https://www.youtube.com/watch?v=Vf1mpbv8DO4), [STEP archive](https://www.mediafire.com/file/jpwetalgq5ctqvr/PlanetaryGearlessMechanism2STEP.zip/file) |
| RC plane retractable landing gear | [rc_plane_retractable_landing_gear.step](rc_plane_retractable_landing_gear.step) |  | [Video](https://www.youtube.com/watch?v=J8K3uAWMSRo), [STEP archive](https://www.mediafire.com/file/ma5cw3isx7oncfw/RCPlaneRetractableLandingGearSTEP.zip/file) |
| Screw 3-stage telescopic actuator 2b | [screw_3_stage_telescopic_actuator_2b.step](screw_3_stage_telescopic_actuator_2b.step) |  | [Video](https://www.youtube.com/watch?v=LvDbXBtNrlQ), [STEP archive](https://www.mediafire.com/file/ohra998t0bjy8qj/Screw3stageTelescopicActuator2bSTEP.zip/file) |
| Spatial planetary belt drive | [spatial_planetary_belt_drive.step](spatial_planetary_belt_drive.step) |  | [Video](https://www.youtube.com/watch?v=wnk6a-lBYCg), [STEP archive](https://www.mediafire.com/file/gbmj0t4ad11ely9/SpatialPlanetaryBeltSTEP.zip/file) |
| Static balancing mechanism using gears and spring | [static_balancing_gears_spring.step](static_balancing_gears_spring.step) |  | [Video](https://www.youtube.com/watch?v=WnDc7tv79HM), [STEP archive](https://www.mediafire.com/file/1y4nqt4jer40uyc/StaticBalancingMechanismGearSpringSTEP.zip/file) |
| Two cam mechanism for drawing rectangles | [two_cam_draw_rectangles.step](two_cam_draw_rectangles.step) |  | [Video](https://www.youtube.com/watch?v=rEmLvLY65E8), [STEP archive](https://www.mediafire.com/file/09cbcf5of21szpn/TwoCamDrawRectangleSTEP.zip/file) |
| Two input shaft differential bevel gearbox | [two_input_shaft_differential_bevel_gearbox.step](two_input_shaft_differential_bevel_gearbox.step) |  | [Video](https://www.youtube.com/watch?v=MLw1eTFPnDE), [STEP archive](https://www.mediafire.com/file/e09s8h9yoxe5luz/TwoInputShaftGearboxSTEP.zip/file) |
| Two stage gear multiplier | [two_stage_gear_multiplier.step](two_stage_gear_multiplier.step) |  | [Video](https://www.youtube.com/watch?v=y9Z5eSPG2TU), [STEP archive](https://www.mediafire.com/file/yt8nu74susrgcv3/TwoStageGearMultiplierSTEP.zip/file) |
| Converting two way linear motion into one way rotation 9b | [two_way_linear_to_one_way_rotation_9b.step](two_way_linear_to_one_way_rotation_9b.step) |  | [Video](https://www.youtube.com/watch?v=PE_Wfw5BZXk), [STEP archive](https://www.mediafire.com/file/gue5rvk6b4dgt1s/Convert2WLto1WR9bSTEP.zip/file) |
| Typewriter desk | [typewriter_desk.step](typewriter_desk.step) |  | [Video](https://www.youtube.com/watch?v=OTLIxTTfnWk), [STEP archive](https://www.mediafire.com/file/xk4fsefxcdl3mtr/TypewriterDeskSTEP.zip/file) |
| Wall mounted car shed | [wall_mounted_car_shed.step](wall_mounted_car_shed.step) |  | [Video](https://www.youtube.com/watch?v=SnVo3Zg83Pk), [STEP archive](https://www.mediafire.com/file/gepccrx2g9h3d3b/WallMountedCarShedSTEP.zip/file) |
