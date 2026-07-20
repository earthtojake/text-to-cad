# SRDF 生成器契约

在 Python 源文件中定义一个顶层无参数 `gen_srdf()` 函数。它必须返回一个包含根 SRDF XML 和所属 URDF 路径的信封字典。

```python
import xml.etree.ElementTree as ET


def gen_srdf():
    robot = ET.Element("robot", {"name": "sample_robot"})
    group = ET.SubElement(robot, "group", {"name": "manipulator"})
    ET.SubElement(group, "chain", {"base_link": "base_link", "tip_link": "tool0"})
    return {
        "xml": robot,
        "urdf": "sample_robot.urdf",
    }
```

## 必需信封

```python
{
    "xml": robot_root_element_or_xml_string,
    "urdf": "relative/path/to/robot.urdf",
}
```

当前运行时仅接受 `xml` 和 `urdf` 字段。不要添加不支持的字段。

## XML 根

XML 根必须为：

```xml
<robot name="...">
```

SRDF 的 robot name 必须与链接的 URDF robot name 匹配。

## URDF 路径

`urdf` 字段相对于生成器源文件解析。它必须：

- 是非空字符串；
- 使用 POSIX `/` 分隔符；
- 是相对路径，而非绝对路径；
- 以 `.urdf` 结尾；
- 引用已存在的文件。

CLI 注入或更新：

```xml
<tcad:urdf path="..."/>
```

`tcad` 前缀以 `https://text-to-cad.dev/srdf` 命名空间发出。注入的路径是从生成的 `.srdf` 位置到链接 URDF 的相对路径。此元数据是下游工具的本地 SRDF 约定；它不是核心 SRDF 语义元素。读取器也接受现有的遗留 `<explorer:urdf/>` 元数据。

## 支持的目标形式

```bash
python scripts/srdf path/to/source.py
python scripts/srdf path/to/source.py -o path/to/robot.srdf
python scripts/srdf a.py=out/a.srdf b.py=out/b.srdf
```

生成的输出路径由 CLI 选择。生成器不应自行写入 `.srdf` 文件。

## Group-state 单位

Group-state joint 值为 URDF 原生值：

- revolute 和 continuous joint：弧度；
- prismatic joint：米。

不要在 SRDF 中存储度数。遗留 UI/协议度数字段是兼容性别名，必须按 joint 类型转换。

## 常见语义元素示例

```python
import xml.etree.ElementTree as ET


def gen_srdf():
    robot = ET.Element("robot", {"name": "sample_robot"})

    ET.SubElement(
        robot,
        "virtual_joint",
        {
            "name": "fixed_base",
            "type": "fixed",
            "parent_frame": "world",
            "child_link": "base_link",
        },
    )

    arm = ET.SubElement(robot, "group", {"name": "manipulator"})
    ET.SubElement(arm, "chain", {"base_link": "base_link", "tip_link": "tool0"})

    gripper = ET.SubElement(robot, "group", {"name": "gripper"})
    ET.SubElement(gripper, "joint", {"name": "finger_joint"})

    ET.SubElement(
        robot,
        "end_effector",
        {
            "name": "gripper_eef",
            "parent_link": "tool0",
            "group": "gripper",
            "parent_group": "manipulator",
        },
    )

    home = ET.SubElement(robot, "group_state", {"name": "home", "group": "manipulator"})
    ET.SubElement(home, "joint", {"name": "shoulder_pan_joint", "value": "0.0"})

    ET.SubElement(
        robot,
        "disable_collisions",
        {"link1": "base_link", "link2": "shoulder_link", "reason": "Adjacent"},
    )

    return {"xml": robot, "urdf": "sample_robot.urdf"}
```

Virtual joint 和 passive joint 是有效的 SRDF 概念。当前轻量级运行时会保留它们，但尚未完全清点或验证（validation）它们；请使用 MoveIt Setup Assistant 或 MoveIt 冒烟测试来验证（validation）它们。
