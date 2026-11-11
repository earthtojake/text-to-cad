"""Where each sample robot's files come from, pinned, and where they land.

A robot is a sample here only when its maker publishes its raw CAD (a STEP of the assembly):
the point is to take that CAD through text-to-cad's whole process -- a model, its mechanism, an
export to MJCF and URDF -- and compare the result with the description Google made by hand in
MuJoCo Menagerie. Two of MuJoCo Playground's four robots qualify:

- **SO-101** (The Robot Studio, Apache-2.0): the full assembly STEP in SO-ARM100, with its
  printed parts, its six ST3215 servos and their internals, screws and the driver board; the
  maker's own URDF and MJCF (made in Onshape with onshape-to-robot) beside it; Menagerie's
  ``robotstudio_so101`` is derived from that MJCF.
- **WidowX AI** (Trossen Robotics, BSD-3-Clause): the follower arm's STEP from Trossen's downloads
  page, one simplified part per link; Trossen's generated URDF; Menagerie's ``trossen_wxai`` is
  derived from that URDF.

i2rt YAM and Unitree G1 publish a URDF and meshes but no STEP, so they are not here. Three Menagerie
robots from beyond Playground are fetched too, not yet converted:

- **xArm7** (UFACTORY): one STEP of the arm from UFACTORY's downloads page (no license stated);
  UFACTORY's xacro description in xarm_ros (BSD-3-Clause); Menagerie's ``ufactory_xarm7`` is
  derived from it.
- **reBot DevArm** (Seeed Studio, CERN-OHL-W-2.0): the RS (RobStride) build's full assembly STEP in
  reBot-DevArm, beside its per-part STEPs; Seeed's URDF in reBot-Isaacsim, from which Menagerie's
  ``seeed_rebot_devarm`` is derived.
- **OP3** (ROBOTIS): the humanoid's assembly STEP in ROBOTIS-OP-Series-Data (no license stated);
  ROBOTIS's xacro description in ROBOTIS-OP3-Common (Apache-2.0); Menagerie's ``robotis_op3`` is
  derived from it.

The xArm7's and the OP3's descriptions are xacro: ``vendor_urdf_path`` names the top file, which
``xacro`` expands into the URDF a comparison reads.

Every source is pinned: a Git repository by commit, a download by the SHA-256 of what it fetched.
The Trossen zip's URL carries a hash its docs site makes per build, so ``fetch`` finds the link on
the downloads page by the file's name and checks the bytes against the pin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # models/mujoco
UPSTREAM = ROOT / "upstream"  # each maker's files, by robot
MENAGERIE = ROOT / "menagerie"  # MuJoCo Menagerie's models, by directory
OUT = ROOT / "out"  # what text-to-cad writes, by robot: <robot>.xml (its MuJoCo function's) and export/ (the plain ones)
REPORTS = ROOT / "reports"  # compare.py's reports, by robot


@dataclass(frozen=True)
class GitSource:
    """Paths of a Git repository at one commit, checked out sparsely."""

    url: str
    commit: str
    paths: tuple[str, ...]
    license: str


@dataclass(frozen=True)
class Download:
    """A zip linked from a page by its file name, pinned by the SHA-256 of the zip."""

    page: str
    name: str
    sha256: str
    license: str


@dataclass(frozen=True)
class File:
    """One file at a fixed URL, pinned by its SHA-256 and saved under ``name`` (the URL's own name is the
    host's upload id). ``page`` is where the link is published, to find it again when it moves."""

    url: str
    name: str
    sha256: str
    page: str
    license: str


@dataclass(frozen=True)
class Robot:
    name: str
    title: str
    cad: GitSource | Download | File
    step: str  # the assembly STEP, relative to upstream/<robot>/
    menagerie: str  # Menagerie's directory
    menagerie_robot: str  # the robot's MJCF in it (no floor, no light)
    vendor_urdf: GitSource  # the maker's own URDF, for comparing ours
    vendor_urdf_path: str  # relative to upstream/<robot>/vendor/
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def folder(self) -> Path:
        return UPSTREAM / self.name

    @property
    def step_path(self) -> Path:
        return self.folder / self.step

    @property
    def menagerie_path(self) -> Path:
        return MENAGERIE / self.menagerie / self.menagerie_robot

    @property
    def vendor_urdf_file(self) -> Path:
        return self.folder / "vendor" / self.vendor_urdf_path

    @property
    def out(self) -> Path:
        return OUT / self.name


MENAGERIE_REPO = GitSource(
    url="https://github.com/google-deepmind/mujoco_menagerie",
    commit="98a70c569c4c1b6da467a20012f766ee1f8dc521",
    paths=("robotstudio_so101", "trossen_wxai", "ufactory_xarm7", "seeed_rebot_devarm", "robotis_op3"),
    license="per model: Apache-2.0 (robotstudio_so101, robotis_op3), BSD-3-Clause (trossen_wxai, ufactory_xarm7), "
            "MIT (seeed_rebot_devarm)",
)

_SO_ARM100 = GitSource(
    url="https://github.com/TheRobotStudio/SO-ARM100",
    commit="a758567c3978dfeefe282ede0500085a48fe8f78",
    paths=("STEP/SO101/SO101 Assembly.step", "Simulation/SO101/"),
    license="Apache-2.0",
)

ROBOTS: dict[str, Robot] = {
    "so101": Robot(
        name="so101",
        title="The Robot Studio SO-101",
        cad=_SO_ARM100,
        step="STEP/SO101/SO101 Assembly.step",
        menagerie="robotstudio_so101",
        menagerie_robot="so101.xml",
        vendor_urdf=_SO_ARM100,
        vendor_urdf_path="Simulation/SO101/so101_new_calib.urdf",
        notes=("The STEP is the same Git checkout as the vendor URDF: upstream/so101/ is the repository's sparse "
               "checkout, and vendor/ links to it.",),
    ),
    "wxai": Robot(
        name="wxai",
        title="Trossen Robotics WidowX AI (follower)",
        cad=Download(
            page="https://docs.trossenrobotics.com/trossen_arm/main/downloads.html",
            name="wxai_v0_follower_steps.zip",
            sha256="1697a7368395a950bbc0158114ecbaff3a7727007e9900e9347f7e7f2cd95fc2",
            license="Trossen Robotics' published CAD (the downloads page states no license)",
        ),
        step="wxai_follower.step",
        menagerie="trossen_wxai",
        menagerie_robot="wxai_follower.xml",
        vendor_urdf=GitSource(
            url="https://github.com/TrossenRobotics/trossen_arm_description",
            commit="1f36d47d104ad9370eb9a30ac255f682c42449c5",
            paths=("urdf/generated/wxai/", "meshes/wxai/", "meshes/peripherals/", "LICENSE"),
            license="BSD-3-Clause",
        ),
        vendor_urdf_path="urdf/generated/wxai/wxai_follower.urdf",
    ),
    "xarm7": Robot(
        name="xarm7",
        title="UFACTORY xArm7",
        cad=File(
            url="https://www.ufactory.cc/upfiles/download/202606/AADTYNXQGW1G.STEP",
            name="xArm 7 (XS1305).step",
            sha256="0db7d5faf55e9c58d26c4407d5ed18a3e6a65bcfb0767bf3427a03a46b845821",
            page="https://www.ufactory.cc/downloads",
            license="UFACTORY's published CAD (the downloads page states no license)",
        ),
        step="xArm 7 (XS1305).step",
        menagerie="ufactory_xarm7",
        menagerie_robot="xarm7.xml",
        vendor_urdf=GitSource(
            url="https://github.com/xArm-Developer/xarm_ros",
            commit="cf51617d98bc55a88d9aa735acfa43a0bbb8e425",
            paths=("xarm_description/urdf/", "xarm_description/config/", "xarm_description/meshes/xarm7/",
                   "xarm_description/meshes/xarm7_1305/", "xarm_description/meshes/gripper/xarm/",
                   "xarm_description/package.xml", "LICENSE"),
            license="BSD-3-Clause",
        ),
        vendor_urdf_path="xarm_description/urdf/xarm_device.urdf.xacro",
        notes=("The STEP is the arm alone (SolidWorks 2016, AP203, 1305Xarm7-M), without the gripper Menagerie's "
               "xarm7.xml carries; xarm7_nohand.xml is Menagerie's arm alone.",
               "The maker's description is xacro: expand it with dof:=7 (robot_type xarm) to compare.",),
    ),
    "rebot_devarm": Robot(
        name="rebot_devarm",
        title="Seeed Studio reBot DevArm (B601-RS)",
        cad=GitSource(
            url="https://github.com/Seeed-Projects/reBot-DevArm",
            commit="c47e37b3be9fda24681f4e43f29ede7e98be2f5a",
            paths=("hardware/reBot_B601_RS/reBot_B601_RS_v1.0_20260625.step", "LICENSE"),
            license="CERN-OHL-W-2.0",
        ),
        step="hardware/reBot_B601_RS/reBot_B601_RS_v1.0_20260625.step",
        menagerie="seeed_rebot_devarm",
        menagerie_robot="seeed_rebot_devarm.xml",
        vendor_urdf=GitSource(
            url="https://github.com/Seeed-Projects/reBot-Isaacsim",
            commit="51aa87625e6aaa1ccb8514b0d0c66e3aa1c711bf",
            paths=("urdf/RS/", "LICENSE"),
            license="MIT (the repository); urdf/RS/ carries its upstream's CERN-OHL-W-2.0",
        ),
        vendor_urdf_path="urdf/RS/urdf/ReBot_Arm_RS.urdf",
        notes=("Menagerie's model is the RS build (RobStride actuators), so the STEP is the RS assembly; the "
               "repository also has the DM (Damiao) build's assembly and per-part STEPs of both.",),
    ),
    "op3": Robot(
        name="op3",
        title="ROBOTIS OP3",
        cad=GitSource(
            url="https://github.com/ROBOTIS-GIT/ROBOTIS-OP-Series-Data",
            commit="65b8e73f2a6ff43ff92470113e5151b393e35448",
            paths=("ROBOTIS-OP3/Hardware/Mechanics/Part/ROBOTIS-OP3_part_asm.stp",),
            license="ROBOTIS's published CAD (the repository states no license)",
        ),
        step="ROBOTIS-OP3/Hardware/Mechanics/Part/ROBOTIS-OP3_part_asm.stp",
        menagerie="robotis_op3",
        menagerie_robot="op3.xml",
        vendor_urdf=GitSource(
            url="https://github.com/ROBOTIS-GIT/ROBOTIS-OP3-Common",
            commit="0780e54c2064a42089b0cf970d716ae44fec9233",
            paths=("op3_description/urdf/", "op3_description/meshes/", "op3_description/package.xml", "LICENSE"),
            license="Apache-2.0",
        ),
        vendor_urdf_path="op3_description/urdf/robotis_op3.urdf.xacro",
        notes=("The maker's description is xacro: expand it to compare.",),
    ),
}
