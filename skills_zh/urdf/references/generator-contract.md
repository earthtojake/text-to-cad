# URDF 生成器契约

在创建或编辑生成 URDF 文件的 Python 源码时使用本参考。

## 源真相

定义 `gen_urdf()` 的 Python 源码是源真相。配置的 `.urdf` 文件是生成的，不应手动编辑。

将设计清册（ledger）保持在源码附近。至少，生成器源码应使单位、参考系（frame）约定、父/子选择、关节（joint）轴、网格（mesh）缩放和假设易于审计。

## 契约

`gen_urdf()` 必须是顶层零参数函数，返回以下之一：

- 完整 URDF 文档的根 `xml.etree.ElementTree.Element`；
- 完整的 URDF XML 字符串；
- 仅含一个字段 `xml` 的封装字典，其值为 `ElementTree.Element` 或 XML 字符串。

默认生成器形式：

```python
import xml.etree.ElementTree as ET


def gen_urdf():
    robot = ET.Element("robot", {"name": "sample"})
    ET.SubElement(robot, "link", {"name": "base_link"})
    return robot
```

需要封装时，将 `xml` 设置为相同的根元素或 XML 字符串：

```python
def gen_urdf():
    robot = ET.Element("robot", {"name": "sample"})
    ET.SubElement(robot, "link", {"name": "base_link"})
    return {"xml": robot}
```

不要在封装中包含输出路径、验证（validation）、Explorer、位姿（pose）预设或消费者元数据。当前运行时拒绝 `urdf_output`、`validate` 和 `explorer_metadata` 等字段；输出路径仅由 CLI 参数选择。命名的机器人位姿（pose）属于 SRDF `<group_state>` 元素，而非 URDF 侧的 `explorer.json` 或 Explorer 元数据产物（artifact）。

CLI 序列化返回的载荷，写入已配置的 `.urdf` 输出路径，并在返回成功前验证（validation）该生成文件。

生成的 `.urdf` 输出路径由 CLI 选择。纯源目标写入同级 `.urdf`；`-o`/`--output` 覆盖单个目标；`SOURCE.py=OUTPUT.urdf` 对覆盖各个目标。

宿主项目可以施加自己的布局策略，但 URDF 技能运行时不硬编码项目目录。

## 编写期望

为物理尺寸、关节（joint）位置、关节（joint）限位、网格（mesh）缩放和惯性参数（inertial）值使用显式常量。避免在关节（joint）原点和轴中使用匿名字面量。

优先选择：

```python
BASE_TO_SHOULDER_Z_M = 0.240
SHOULDER_PAN_AXIS = (0.0, 0.0, 1.0)
FOREARM_MESH_SCALE_FROM_MM = (0.001, 0.001, 0.001)
```

而非：

```python
origin="0 0 0.24"
axis="0 0 1"
scale="0.001 0.001 0.001"
```

直接在常量附近的注释中或 `references/design-ledger.md` 风格的项目文档中记录假设。

## 参考系（frame）和单位规则

生成器必须按项目的 URDF 单位约定输出 URDF 值，通常为米、千克、秒和弧度。

输出关节（joint）前，确认：

- 父和子连杆（link）名称正确；
- 关节（joint）原点在父连杆（link）参考系（frame）中表达；
- 子连杆（link）参考系（frame）有意与关节（joint）参考系（frame）重合；
- 关节（joint）轴在关节（joint）参考系（frame）中表达；
- revolute 限位为弧度；
- prismatic 限位为米；
- continuous 关节（joint）不使用虚假的有限上下限。

输出视觉、碰撞（collision）或惯性参数（inertial）数据前，确认：

- 其原点在所属连杆（link）参考系（frame）中表达；
- 网格（mesh）缩放将网格（mesh）源单位转换为米；
- 碰撞（collision）几何有意简化或有意与视觉几何相同；
- 惯性参数（inertial）原点代表质心，而非仅仅是视觉原点。

当前 `scripts/urdf` 验证（validation）路径接受任何非空网格（mesh）文件名或 URI，在 URI 本地解析时检查本地文件存在性，并将网格（mesh）格式可加载性留给目标 URDF 消费者。视觉和碰撞（collision）几何可使用 `<mesh>`、`<box>`、`<cylinder>` 或 `<sphere>`。

## 运行时行为

`scripts/urdf` 仅运行 `gen_urdf()`。它不重新生成外部 CAD、网格（mesh）/导出、GLB/拓扑（topology）、渲染、SDF 或 SRDF/MoveIt2 产物（artifact）。

如果 URDF 视觉/碰撞（collision）网格（mesh）引用依赖于已更新的 CAD 或网格（mesh）输出，请用所属的 CAD 或网格（mesh）工作流（workflow）单独重新生成那些显式目标。

导入生成器模块会执行其顶层 Python 代码。保持顶层生成器模块确定性和低副作用。仅当任务明确要求时，才将昂贵或可变工作放在 `gen_urdf()` 之后。

## 路径

相对源目标和 CLI 输出路径从当前工作目录解析。

在生成器代码内，优先使用从生成器文件或包约定派生的路径，而非隐式 shell 工作目录假设。输出到 URDF 的网格（mesh）文件名应从生成的 `.urdf` 文件视角稳定可访问，或使用消费者理解的 package URI。
