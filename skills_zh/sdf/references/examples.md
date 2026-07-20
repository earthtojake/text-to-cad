# SDF 示例

这些示例展示了预期风格：显式参考系（frame）、源相关假设、简单辅助函数和结构化假设。

## 使用原始 ElementTree 的最小模型（model）

```python
import xml.etree.ElementTree as ET


def text(parent, tag, value, attrib=None):
    child = ET.SubElement(parent, tag, attrib or {})
    child.text = str(value)
    return child


def gen_sdf():
    sdf = ET.Element("sdf", {"version": "1.12"})
    model = ET.SubElement(sdf, "model", {"name": "calibration_box"})
    text(model, "pose", "0 0 0 0 0 0", {"relative_to": "world"})

    link = ET.SubElement(model, "link", {"name": "body"})
    visual = ET.SubElement(link, "visual", {"name": "body_visual"})
    geometry = ET.SubElement(visual, "geometry")
    box = ET.SubElement(geometry, "box")
    text(box, "size", "0.1 0.1 0.1")

    collision = ET.SubElement(link, "collision", {"name": "body_collision"})
    c_geometry = ET.SubElement(collision, "geometry")
    c_box = ET.SubElement(c_geometry, "box")
    text(c_box, "size", "0.1 0.1 0.1")

    inertial = ET.SubElement(link, "inertial")
    text(inertial, "mass", "1.0")
    inertia = ET.SubElement(inertial, "inertia")
    text(inertia, "ixx", "0.0016666667")
    text(inertia, "iyy", "0.0016666667")
    text(inertia, "izz", "0.0016666667")
    text(inertia, "ixy", "0")
    text(inertia, "ixz", "0")
    text(inertia, "iyz", "0")

    return {
        "xml": sdf,
        "assumptions": ["Box inertia uses a uniform-density primitive approximation."],
    }
```

## 最小世界（world）

```python
import xml.etree.ElementTree as ET


def text(parent, tag, value, attrib=None):
    child = ET.SubElement(parent, tag, attrib or {})
    child.text = str(value)
    return child


def gen_sdf():
    sdf = ET.Element("sdf", {"version": "1.12"})
    world = ET.SubElement(sdf, "world", {"name": "empty_lit_world"})

    light = ET.SubElement(world, "light", {"name": "sun", "type": "directional"})
    text(light, "pose", "0 0 10 0 0 0", {"relative_to": "world"})
    text(light, "cast_shadows", "true")

    return {
        "xml": sdf,
        "metadata": {"document_kind": "world"},
        "assumptions": ["World intentionally contains no inline model."],
    }
```

## 使用构建辅助函数的模型（model）

```python
from sdf.builder import (
    box,
    collision,
    inertial,
    joint,
    link,
    model,
    pose,
    sdf_root,
    visual,
)


BASE_MASS_KG = 2.0
ARM_MASS_KG = 0.5


def gen_sdf():
    sdf = sdf_root("1.12")
    robot = model(sdf, "two_link_demo")
    pose(robot, relative_to="world")

    base = link(robot, "base_link")
    box(visual(base, "base_visual"), (0.4, 0.3, 0.1))
    box(collision(base, "base_collision"), (0.4, 0.3, 0.1))
    inertial(base, BASE_MASS_KG, (0.02, 0.03, 0.04, 0, 0, 0))

    arm = link(robot, "arm_link")
    box(visual(arm, "arm_visual"), (0.3, 0.05, 0.05))
    box(collision(arm, "arm_collision"), (0.3, 0.05, 0.05))
    inertial(arm, ARM_MASS_KG, (0.001, 0.004, 0.004, 0, 0, 0))

    joint(
        robot,
        "shoulder_pan",
        "revolute",
        "base_link",
        "arm_link",
        axis_xyz=(0, 0, 1),
        axis_expressed_in="base_link",
    )

    return {
        "xml": sdf,
        "assumptions": [
            "Primitive inertials are approximate placeholders.",
            "Positive shoulder_pan rotates counterclockwise when viewed from +Z."
        ],
    }
```

## 来自文档的插件（plugin）块

当从目标仿真器文档复制插件（plugin）块时，保留其显式参数并报告来源：

```python
import xml.etree.ElementTree as ET


def add_known_plugin(parent):
    plugin = ET.SubElement(
        parent,
        "plugin",
        {"name": "example_control", "filename": "libexample_control.so"},
    )
    ET.SubElement(plugin, "namespace").text = "robot1"
    return plugin
```

不要编造插件（plugin）字段。如果文档来源不可用，在生成器信封（envelope）中将该插件（plugin）标记为未验证（validation）。
