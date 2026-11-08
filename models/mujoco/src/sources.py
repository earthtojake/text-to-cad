"""Where each benchmark robot's files come from, pinned, and where they land.

A robot is in the benchmark only when its maker publishes its raw CAD (a STEP of the assembly):
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

i2rt YAM and Unitree G1 publish a URDF and meshes but no STEP, so they are not here.

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
OUT = ROOT / "out"  # what text-to-cad writes, by robot: <robot>.xml, .urdf, .sdf and their meshes
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
class Robot:
    name: str
    title: str
    cad: GitSource | Download
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
    paths=("robotstudio_so101", "trossen_wxai"),
    license="per model: Apache-2.0 (robotstudio_so101), BSD-3-Clause (trossen_wxai)",
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
            paths=("urdf/generated/wxai/", "meshes/wxai/", "LICENSE"),
            license="BSD-3-Clause",
        ),
        vendor_urdf_path="urdf/generated/wxai/wxai_follower.urdf",
    ),
}
