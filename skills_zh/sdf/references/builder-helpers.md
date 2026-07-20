# SDF 构建辅助函数（builder helpers）

构建辅助函数是可选的。它们的存在是为了减少 XML 构造中常见的 LLM 错误，而非替代 SDFormat 或 libsdformat。

## 辅助函数为何存在

LLM 在编写原始 XML 时常犯以下错误：

- 位姿（pose）值长度错误；
- 隐藏的度/弧度转换；
- 缺少 `relative_to` 或 `expressed_in`；
- 零或非有限关节（joint）轴；
- 负的基元尺寸；
- mesh 缩放应用不一致；
- 从 visual 复制的惯性（inertial）值；
- 由看似合理的名称编造的插件（plugin）文件名。

辅助函数应使常见路径变得显式、类型化、可审计，同时仍返回普通的 `xml.etree.ElementTree.Element` 节点。

## 设计约束

- 仅使用标准库。
- 不强制依赖 Gazebo、ROS、NumPy、lxml、CAD 或 mesh。
- 返回 ElementTree 元素。
- 与原始 ElementTree 调用组合使用。
- 校验本地数值的形状和有限性。
- 不尝试完整的 SDFormat schema 校验。
- 不静默编造参考系（frame）、轴、惯性（inertial）、插件（plugin）或传感器（sensor）参数。

## 推荐的辅助函数接口

名称可以变化以匹配当前运行时包，但辅助函数接口应保持精简。

```python
# XML 基础
text(parent, tag, value, attrib=None)
fmt_float(value)
fmt_vector(values)

# 位姿（pose）和轴
pose(parent, xyz=(0, 0, 0), rpy=(0, 0, 0), *, relative_to=None,
     rotation_format="euler_rpy", degrees=False)
quat_pose(parent, xyz=(0, 0, 0), quat_xyzw=(0, 0, 0, 1), *, relative_to=None)
axis(parent, xyz=(0, 0, 1), *, expressed_in=None)

# 文档结构
sdf_root(version="1.12")
world(parent, name)
model(parent, name, *, static=None, pose=None)
frame(parent, name, *, attached_to=None, pose=None)
link(parent, name, *, pose=None, inertial=None)
joint(parent, name, joint_type, parent_link, child_link, *, pose=None,
      axis_xyz=None, axis_expressed_in=None, axis2_xyz=None, limits=None)

# 几何（geometry）
visual(parent, name, *, pose=None)
collision(parent, name, *, pose=None)
box(parent, size_xyz)
sphere(parent, radius)
cylinder(parent, radius, length)
capsule(parent, radius, length)
mesh(parent, uri, *, scale=None)

# 物理（physics）和元数据
inertial(parent, mass, inertia, *, pose=None)
sensor(parent, name, sensor_type, *, pose=None, topic=None, update_rate=None)
plugin(parent, name, filename, params=None)
include(parent, uri, *, name=None, pose=None)
```

## 数值行为

辅助函数应拒绝：

- 非有限数值；
- 长度错误的向量；
- 负或零的基元尺寸；
- 零关节（joint）轴；
- 零质量惯性（inertial）；
- 零范数四元数。

辅助函数可以警告，但不应静默修复：

- 非单位轴；
- 非归一化四元数；
- 使用度；
- 非平凡位姿（pose）缺少 `relative_to`。

## 示例

```python
from sdf.builder import axis, box, collision, joint, link, model, sdf_root, visual

BASE_SIZE_M = (0.4, 0.3, 0.1)
LIFT_AXIS_Z = (0.0, 0.0, 1.0)


def gen_sdf():
    sdf = sdf_root("1.12")
    robot = model(sdf, "lift_fixture", static=False)

    base = link(robot, "base_link")
    v = visual(base, "base_visual")
    box(v, BASE_SIZE_M)
    c = collision(base, "base_collision")
    box(c, BASE_SIZE_M)

    carriage = link(robot, "carriage_link")
    j = joint(
        robot,
        "lift_joint",
        "prismatic",
        parent_link="base_link",
        child_link="carriage_link",
        axis_xyz=LIFT_AXIS_Z,
        axis_expressed_in="base_link",
    )

    return {
        "xml": sdf,
        "assumptions": [
            {"code": "inertials_placeholder", "message": "Inertials omitted pending measured masses."}
        ],
    }
```

## 何时不使用辅助函数

以下情况可接受使用原始 ElementTree：

- 目标仿真器需要不寻常的扩展 XML；
- 插件（plugin）有任意嵌套配置；
- 现有生成器已有清晰的内部抽象；
- 用户要求仅最小 XML 源文件。

即便如此，仍应保留命名常量、台账注释和校验。
