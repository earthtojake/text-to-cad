"""Loading a robot description into MuJoCo the same way whatever its format, and reading it.

An MJCF is loaded as it is. A URDF is loaded from a temporary copy with a ``<mujoco><compiler>``
that keeps its visuals and its fixed links (MuJoCo drops the first and fuses the second by default)
and with every mesh path made absolute: relative to the URDF, or a ``package://`` URI resolved by
the map given or by the nearest ancestor folder holding the rest of the path. A mesh that cannot be
found is dropped, with a warning, rather than failing the whole load.

A *link* here is what a joint moves rigidly: the joint's body and its descendants reached without
crossing another joint. The root link is the static body the first joint hangs from, with its own
fixed descendants. That makes an MJCF's bodies and a URDF's links (fused or not) comparable.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import mujoco
import numpy as np

from lib.compare_geom import Surface, primitive_mesh

ROOT = "(root)"
HINGE, SLIDE = int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)
FREE = int(mujoco.mjtJoint.mjJNT_FREE)
MESH = int(mujoco.mjtGeom.mjGEOM_MESH)
COMPILER = {"discardvisual": "false", "fusestatic": "false", "strippath": "false", "balanceinertia": "true"}


class LoadError(Exception):
    pass


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".urdf":
        return "urdf"
    if suffix == ".sdf":
        raise LoadError(f"{path}: MuJoCo cannot load SDF; compare the .xml or .urdf instead")
    try:
        tag = ET.parse(path).getroot().tag
    except ET.ParseError as e:
        raise LoadError(f"{path}: not XML ({e})") from e
    if tag == "robot":
        return "urdf"
    if tag == "mujoco":
        return "mjcf"
    raise LoadError(f"{path}: root element <{tag}> is neither <mujoco> nor <robot>")


def _resolve_mesh(filename: str, urdf: Path, packages: dict[str, Path]) -> Path | None:
    filename = filename.removeprefix("file://")
    if filename.startswith("package://"):
        pkg, _, rest = filename[len("package://"):].partition("/")
        roots = [packages[pkg]] if pkg in packages else []
        roots += list(urdf.resolve().parents)
        for r in roots:
            if (r / rest).is_file():
                return (r / rest).resolve()
        return None
    p = Path(filename)
    p = p if p.is_absolute() else urdf.parent / p
    return p.resolve() if p.is_file() else None


def _prepared_urdf(path: Path, packages: dict[str, Path], warnings: list[str]) -> str:
    tree = ET.parse(path)
    robot = tree.getroot()
    for kind in ("visual", "collision"):
        for link in robot.iter("link"):
            for el in list(link.findall(kind)):
                mesh = el.find("geometry/mesh")
                if mesh is None:
                    continue
                found = _resolve_mesh(mesh.get("filename", ""), path, packages)
                if found is None:
                    warnings.append(f"{path.name}: link {link.get('name')}: {kind} mesh "
                                    f"{mesh.get('filename')} not found, dropped")
                    link.remove(el)
                else:
                    mesh.set("filename", str(found))
    mj = robot.find("mujoco")
    if mj is None:
        mj = ET.Element("mujoco")
        robot.insert(0, mj)
    comp = mj.find("compiler")
    if comp is None:
        comp = ET.SubElement(mj, "compiler")
    for k, v in COMPILER.items():
        comp.set(k, v)
    comp.set("meshdir", str(path.parent.resolve()))
    return ET.tostring(robot, encoding="unicode")


@contextlib.contextmanager
def _captured():
    """What MuJoCo's compiler prints: it writes its warnings straight to the process's stdout/stderr."""
    lines: list[str] = []
    sys.stdout.flush()
    sys.stderr.flush()
    saved = {fd: os.dup(fd) for fd in (1, 2)}
    with tempfile.TemporaryFile(mode="w+") as f:
        for fd in saved:
            os.dup2(f.fileno(), fd)
        try:
            yield lines
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            for fd, keep in saved.items():
                os.dup2(keep, fd)
                os.close(keep)
            f.seek(0)
            lines += [ln.strip().removeprefix("WARNING: ") for ln in f.read().splitlines() if ln.strip()]


def load(path: Path, packages: dict[str, Path] | None = None) -> tuple[mujoco.MjModel, str, list[str]]:
    path = Path(path)
    if not path.is_file():
        raise LoadError(f"{path}: no such file")
    kind = detect_kind(path)
    warnings: list[str] = []
    try:
        if kind == "mjcf":
            return mujoco.MjModel.from_xml_path(str(path)), kind, warnings
        text = _prepared_urdf(path, packages or {}, warnings)
        fd, tmp = tempfile.mkstemp(suffix=".urdf", prefix="compare_")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(text)
            with _captured() as said:
                model = mujoco.MjModel.from_xml_path(tmp)
            dup = [ln for ln in said if "duplicate name" in ln]
            if dup:
                warnings.append(f"{path.name}: {len(dup)} geoms share their link's name (visual and collision); "
                                "MuJoCo left them unnamed")
            warnings += [f"{path.name}: MuJoCo: {ln}" for ln in said if ln not in dup]
            return model, kind, warnings
        finally:
            os.unlink(tmp)
    except ValueError as e:
        raise LoadError(f"{path}: MuJoCo could not load it: {e}") from e


@dataclass
class Joint:
    name: str
    id: int
    type: int  # HINGE or SLIDE
    body: int
    qpos: int
    dof: int
    range: tuple[float, float] | None
    parent: int | None = None  # index (in Desc.joints) of the joint that moves this one's parent link

    @property
    def kind(self) -> str:
        return "hinge" if self.type == HINGE else "slide"


@dataclass
class Desc:
    """One description, loaded, with its joints, links and their geometry."""

    label: str
    path: Path
    kind: str
    model: mujoco.MjModel
    data: mujoco.MjData = field(init=False)
    warnings: list[str] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)
    link_of_body: np.ndarray = field(init=False)  # joint index, -1 the root link, -2 world/elsewhere
    visual_rule: str = ""

    def __post_init__(self):
        m = self.model
        self.data = mujoco.MjData(m)
        jidx: dict[int, int] = {}
        for j in range(m.njnt):
            t = int(m.jnt_type[j])
            if t not in (HINGE, SLIDE):
                if t != FREE:
                    self.warnings.append(f"joint {m.joint(j).name or j}: ball joints are not compared")
                continue
            b = int(m.jnt_bodyid[j])
            if b in {jj.body for jj in self.joints}:
                self.warnings.append(f"joint {m.joint(j).name}: second joint on body {m.body(b).name}, "
                                     "not compared")
                continue
            rng = (float(m.jnt_range[j][0]), float(m.jnt_range[j][1])) if m.jnt_limited[j] else None
            jidx[b] = len(self.joints)
            self.joints.append(Joint(m.joint(j).name or f"joint{j}", j, t, b, int(m.jnt_qposadr[j]),
                                     int(m.jnt_dofadr[j]), rng))
        # each body's link: the nearest ancestor-or-self that carries a compared joint
        link = np.full(m.nbody, -2, dtype=int)
        for b in range(1, m.nbody):
            p = int(m.body_parentid[b])
            link[b] = jidx.get(b, link[p] if p > 0 else -3)  # -3: static, under world
        # the root link: the static subtree the first joint hangs from
        if self.joints:
            top = int(m.body_parentid[self.joints[0].body])
            while top > 0 and m.body_parentid[top] > 0 and link[top] == -3:
                top = int(m.body_parentid[top])
            for b in range(1, m.nbody):
                if link[b] == -3:
                    a = b
                    while a > 0 and a != top:
                        a = int(m.body_parentid[a])
                    link[b] = -1 if a == top else -2
        else:
            link[link == -3] = -1
        self.link_of_body = link
        for j in self.joints:
            pl = link[int(m.body_parentid[j.body])]
            j.parent = int(pl) if pl >= 0 else None
        vis = (m.geom_contype == 0) & (m.geom_conaffinity == 0) & (m.geom_group < 3)
        self.visual = vis
        self.visual_rule = "contype=conaffinity=0 and group<3"
        self.zero()

    # -- state ---------------------------------------------------------------------------------
    def zero(self) -> None:
        """Every compared joint at value 0 (not at ``ref``); free joints at their qpos0."""
        self.data.qpos[:] = self.model.qpos0
        for j in self.joints:
            self.data.qpos[j.qpos] = 0.0
        mujoco.mj_kinematics(self.model, self.data)

    def set(self, values: dict[int, float]) -> None:
        for i, v in values.items():
            self.data.qpos[self.joints[i].qpos] = v
        mujoco.mj_kinematics(self.model, self.data)

    # -- links ---------------------------------------------------------------------------------
    def link_bodies(self, key: int) -> list[int]:
        """Bodies of link ``key`` (a joint index, or -1 for the root link)."""
        return [b for b in range(1, self.model.nbody) if self.link_of_body[b] == key]

    def link_name(self, key: int) -> str:
        if key == -1:  # named for the body the first joint hangs from
            if self.joints and self.model.body_parentid[self.joints[0].body] > 0:
                return self.model.body(int(self.model.body_parentid[self.joints[0].body])).name
            bodies = self.link_bodies(-1)
            return self.model.body(bodies[0]).name if bodies else ROOT
        return self.model.body(self.joints[key].body).name

    def link_geoms(self, key: int) -> tuple[list[int], str]:
        """The geoms that stand for a link's shape, and which rule picked them: its visual meshes,
        else its visual primitives, else any of its meshes, else any primitive."""
        m = self.model
        bodies = set(self.link_bodies(key))
        geoms = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in bodies]
        mesh = [g for g in geoms if m.geom_type[g] == MESH]
        for picked, rule in (([g for g in mesh if self.visual[g]], "visual meshes"),
                             ([g for g in geoms if self.visual[g]], "visual primitives"),
                             (mesh, "meshes (no visual geoms)"),
                             (geoms, "primitives (no meshes)")):
            if picked:
                return picked, rule
        return [], "no geometry"

    def geom_tris_local(self, g: int) -> np.ndarray | None:
        m = self.model
        if m.geom_type[g] == MESH:
            mid = int(m.geom_dataid[g])
            va, vn = int(m.mesh_vertadr[mid]), int(m.mesh_vertnum[mid])
            fa, fn = int(m.mesh_faceadr[mid]), int(m.mesh_facenum[mid])
            v = m.mesh_vert[va:va + vn].astype(float)
            f = m.mesh_face[fa:fa + fn]
            return v[f]
        name = mujoco.mjtGeom(int(m.geom_type[g])).name.removeprefix("mjGEOM_").lower()
        tm = primitive_mesh(name, m.geom_size[g])
        return None if tm is None else tm.vertices[tm.faces]

    def link_tris(self, key: int) -> tuple[np.ndarray, str]:
        """A link's triangles in world coordinates at the current state."""
        geoms, rule = self.link_geoms(key)
        out = []
        for g in geoms:
            t = self.geom_tris_local(g)
            if t is None:
                continue
            R = self.data.geom_xmat[g].reshape(3, 3)
            out.append(t @ R.T + self.data.geom_xpos[g])
        return (np.concatenate(out) if out else np.zeros((0, 3, 3))), rule

    def link_surface(self, key: int, R: np.ndarray | None = None, t: np.ndarray | None = None) -> Surface:
        tris, _ = self.link_tris(key)
        if R is not None:
            tris = tris @ R.T + t
        return Surface(tris)

    def link_mass(self, key: int) -> tuple[float, np.ndarray, np.ndarray]:
        """Mass, COM (world) and inertia about the COM (world axes) of a link at the current state,
        its bodies combined with the parallel-axis theorem."""
        return self.bodies_mass(self.link_bodies(key))

    def bodies_mass(self, bodies: list[int]) -> tuple[float, np.ndarray, np.ndarray]:
        m, d = self.model, self.data
        mass = float(sum(m.body_mass[b] for b in bodies))
        if mass <= 0:
            return 0.0, np.full(3, np.nan), np.full((3, 3), np.nan)
        com = sum(m.body_mass[b] * d.xipos[b] for b in bodies) / mass
        inertia = np.zeros((3, 3))
        for b in bodies:
            R = d.ximat[b].reshape(3, 3)
            r = d.xipos[b] - com
            inertia += R @ np.diag(m.body_inertia[b]) @ R.T
            inertia += m.body_mass[b] * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
        return mass, com, inertia

    def joint_world(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """A joint's anchor and unit axis in world coordinates at the current state."""
        j = self.joints[i].id
        a = self.data.xaxis[j].copy()
        return self.data.xanchor[j].copy(), a / np.linalg.norm(a)


def describe(label: str, path: Path, packages: dict[str, Path] | None = None) -> Desc:
    model, kind, warnings = load(path, packages)
    d = Desc(label=label, path=Path(path), kind=kind, model=model)
    d.warnings[:0] = warnings
    return d
