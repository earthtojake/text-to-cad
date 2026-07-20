# SDF 生成器契约（generator contract）

在创建或编辑生成 SDFormat/SDF 文件的 Python 源文件时使用本参考。

## 事实来源（source of truth）

定义 `gen_sdf()` 的 Python 源文件是事实来源。已配置的 `.sdf` 输出是生成的，不应手工编辑。

## 必需的形状

`gen_sdf()` 必须是顶层零参数函数。优先返回根 `xml.etree.ElementTree.Element` 以构成完整的 SDFormat 文档。

```python
import xml.etree.ElementTree as ET


def gen_sdf():
    sdf = ET.Element("sdf", {"version": "1.12"})
    model = ET.SubElement(sdf, "model", {"name": "sample_robot"})
    ET.SubElement(model, "link", {"name": "base_link"})
    return sdf
```

根必须是 `<sdf>` 且必须包含非空 `version` 属性。除非用户或目标仿真器要求其他版本，否则新输出默认为 `version="1.12"`。

## 接受的返回值

首选：

```python
def gen_sdf():
    return sdf_root_element
```

为兼容性而接受：

```python
def gen_sdf():
    return """<?xml version="1.0"?>
<sdf version="1.12">...</sdf>
"""
```

信封（envelope）形式：

```python
def gen_sdf():
    return {
        "xml": sdf_root_element,
        "assumptions": [
            {"code": "mesh_units", "message": "Assumed mesh units are meters."},
            "Assumed lidar frame is coincident with lidar_link.",
        ],
        "warnings": [
            {"code": "plugin_unverified", "message": "Camera plugin filename was not verified in the target simulator."}
        ],
        "metadata": {
            "target_consumer": "Gazebo Harmonic",
            "sdf_version": "1.12",
        },
    }
```

信封规则：

- `xml` 是必需的，可以是 XML 元素或 XML 字符串。
- `assumptions`（如果存在）必须是字符串列表或包含 `code`、`message` 和可选 `source` 的字典列表。
- `warnings`（如果存在）必须是字符串列表或包含 `code`、`message` 和可选 `source` 的字典列表。
- `metadata`（如果存在）必须是可 JSON 序列化的、含标量值的字典。
- 不支持 `sdf_output` 等输出路径字段；通过 CLI 目标选择输出路径。
- 不支持的信封字段应以清晰错误失败。

使用信封假设使空间、物理、仿真器和资源假设可审计。不要在 XML 字面量中隐藏猜测。

## 输出路径

生成的 `.sdf` 输出路径由 CLI 选择：

- 普通源目标：源文件旁的同级 `.sdf`；
- `-o` / `--output`：对单个普通目标的覆盖；
- `SOURCE.py=OUTPUT.sdf`：多目标生成的每目标覆盖。

生成器不应自行写入输出文件。

## 源相关资产路径

不要在生成器代码中依赖 shell 工作目录来处理 mesh 或资源路径。优先使用源相关常量：

```python
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
MESH_DIR = SOURCE_DIR / "meshes"
```

对于模型（model）包，优先使用目标仿真器能理解的 URI 约定，如 `model://...`、`package://...` 或从生成的 `.sdf` 位置出发的稳定相对路径。

## 位姿（pose）和参考系（frame）纪律

在输出 `<pose>`、`<frame>`、`<joint>`、`<axis>`、`<visual>`、`<collision>`、传感器（sensor）或插件（plugin）放置元素之前，填写设计台账（design ledger）：

- 位姿（pose）值；
- 位姿（pose）参考系（frame）或 `relative_to`；
- 关节（joint）轴和 `expressed_in` 参考系（frame）；
- 正向运动约定；
- mesh 单位和缩放；
- 每个值的来源。

使用名称能暴露假设的常量：

```python
ASSUMED_BASE_TO_LIDAR_Z_M = 0.18
ASSUMED_LIDAR_YAW_RAD = 0.0
```

不要在 XML 字面量中隐藏空间猜测。

## 带有显式位姿（pose）意图的最小模型（model）示例

```python
import xml.etree.ElementTree as ET


def text(parent, tag, value, attrib=None):
    child = ET.SubElement(parent, tag, attrib or {})
    child.text = str(value)
    return child


def pose(parent, xyz=(0, 0, 0), rpy=(0, 0, 0), *, relative_to=None):
    attrib = {"relative_to": relative_to} if relative_to else {}
    return text(parent, "pose", " ".join(str(v) for v in (*xyz, *rpy)), attrib)


def gen_sdf():
    sdf = ET.Element("sdf", {"version": "1.12"})
    model = ET.SubElement(sdf, "model", {"name": "sample_robot"})
    pose(model, relative_to="world")

    base = ET.SubElement(model, "link", {"name": "base_link"})
    visual = ET.SubElement(base, "visual", {"name": "base_visual"})
    geometry = ET.SubElement(visual, "geometry")
    box = ET.SubElement(geometry, "box")
    text(box, "size", "0.4 0.3 0.1")

    return {
        "xml": sdf,
        "assumptions": ["base_link is coincident with the model frame."],
        "metadata": {"target_consumer": "visualization"},
    }
```
