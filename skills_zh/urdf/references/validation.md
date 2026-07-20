# URDF 生成时验证（validation）

使用本参考了解生成的 URDF 应满足什么。`scripts/urdf` 生成路径默认进行验证（validation）；本技能中没有单独的仅验证（validation）命令。

验证（validation）是约束规则（guardrails），不能替代设计清册（ledger）或视觉/消费者冒烟测试。URDF 可以通过结构检查但仍可能有错误的空间假设。

当可用时，应将生成或修改的 `.urdf` 文件交接（handoff）给 `$cad-viewer` 以获取实时查看器链接。

## 结构检查

验证（validation）：

- 根元素为 `<robot>`；
- 机器人有非空名称；
- 每个连杆（link）有唯一非空名称；
- 每个关节（joint）有唯一非空名称；
- 每个关节（joint）有有效的父和子字段；
- 父和子连杆（link）存在；
- 每个子连杆（link）最多有一个父节点；
- 图恰好有一个根连杆（link）；
- 图连通且无环；
- 树恰好有 `links - 1` 个关节（joint），除非设计有意使用不同结构且运行时支持。

## 原点检查

对于每个关节（joint）、视觉、碰撞（collision）和惯性参数（inertial）原点，验证（validation）或审查：

- `xyz` 存在时有三个有限数值；
- `rpy` 存在时有三个有限数值；
- 省略值仅在有意时遵循 URDF 默认值；
- 单位为 `xyz` 用米，`rpy` 用弧度；
- 原点在正确的参考系（frame）中表达。

参考系（frame）正确性必须从设计清册（ledger）审查。仅 XML 验证（validation）无法证明原点在空间上正确。

## 关节（joint）检查

当前 `scripts/urdf` 源读取器支持以下关节（joint）类型：

- `fixed`
- `continuous`
- `revolute`
- `prismatic`

一些 URDF 消费者还支持 `floating` 和 `planar`；仅当项目运行时和验证（validation）路径支持时才使用它们。当前 `scripts/urdf` 读取器拒绝它们。

对于非固定关节（joint），验证（validation）或审查：

- `<axis>` 在需要处存在；
- 轴恰好有三个有限数值；
- 轴非零；
- 轴已归一化或由生成器代码有意归一化；
- 轴在关节（joint）参考系（frame）中表达；
- 正向运动在设计清册（ledger）中记录。

对于限位：

- `revolute` 上下限为弧度；
- `prismatic` 上下限为米；
- 下限不大于上限；
- effort 和 velocity 存在时为有限；
- `continuous` 关节（joint）不使用人为的有限上下限；
- `fixed` 关节（joint）不需要运动限位。

## 几何检查

通用 URDF 视觉和碰撞（collision）几何可使用：

- `<mesh>`
- `<box>`
- `<cylinder>`
- `<sphere>`

当前 `scripts/urdf` 验证（validation）路径允许视觉和碰撞（collision）几何使用这些几何类型。

对于几何，验证（validation）或审查：

- 每个视觉或碰撞（collision）块有 `<geometry>` 元素；
- 每个几何块恰好有一个支持的几何子元素；
- 基本体尺寸为正且有限；
- 网格（mesh）文件名非空；
- 网格（mesh）缩放存在时有三个正有限值；
- 视觉和碰撞（collision）原点相对于所属连杆（link）参考系（frame）；
- 碰撞（collision）几何适合目标消费者。

## 网格（mesh）引用检查

对于网格（mesh）引用，区分语法、本地存在性和运行时 package 解析。

验证（validation）或审查：

- 本地相对和绝对路径是有意的；
- 文件系统验证（validation）可用时本地文件存在；
- `package://...` URI 语法有效；
- 不错误地假设 package URI 从当前工作目录解析；
- 消费 ROS 或仿真器环境能解析 package URI；
- 网格（mesh）源单位和输出缩放可转换为米。

当前源读取器接受任何非空网格（mesh）文件名或 URI。它从生成的 URDF 文件目录解析本地网格（mesh）路径并验证（validation）这些文件存在。它以警告形式接受未解析的 `package://...` 和远程引用，因为最终网格（mesh）格式支持是消费者特定的。

如果网格（mesh）引用已更改，确认相应的网格（mesh）输出已由所属 CAD 或网格（mesh）工作流（workflow）单独重新生成。

## 惯性参数（inertial）检查

对于每个有质量或几何的物理连杆（link），优先使用显式 `inertial` 块：

- `origin` 是连杆（link）参考系（frame）中的质心；
- `mass` 为正且有限；
- `inertia` 定义 `ixx`、`ixy`、`ixz`、`iyy`、`iyz` 和 `izz`；
- 所有惯性值为有限；
- 对角惯性值为正；
- 惯性矩阵对于预期近似在物理上合理；
- 近似值已记录。

仅参考系（frame）连杆（link）可有意识地省略 `inertial`。当目标消费者使用仿真或动力学时，应指出省略惯性参数（inertial）的物理连杆（link）。

## URDF 有效性 vs 项目策略

将通用 URDF 有效性与项目特定策略分开。

通用 URDF 有效性或健全性检查示例：

- 唯一的连杆（link）和关节（joint）；
- 有效的树结构；
- 有效的关节（joint）父/子引用；
- 有限的原点；
- 非零的可动关节（joint）轴；
- 正的基本体尺寸；
- 物理惯性参数（inertial）块的质量为正。

项目策略检查示例：

- 视觉网格（mesh）引用必须使用特定扩展名；
- 视觉几何必须仅为网格（mesh）；
- 碰撞（collision）几何必须仅为基本体；
- 网格（mesh）文件必须位于特定目录下；
- 每个物理连杆（link）必须有碰撞（collision）几何；
- 每个物理连杆（link）必须有惯性参数（inertial）数据；
- package URI 必须使用特定 package 前缀。

当生成的 URDF 因项目策略失败时，应报告为策略失败，而非通用 URDF 无效。

## 失败处理

当生成时验证（validation）失败时：

1. 修复生成器源码、设计清册（ledger）或引用资产；
2. 重新生成显式 URDF 目标；
3. 不要将手动编辑生成的 `.urdf` 作为永久修复；
4. 记录任何剩余假设或未检查的空间声明。

## 工具

编写测试或针对性检查时，通过 `urdf.source.read_urdf_source()` 辅助函数使用 `scripts/urdf/source.py` 进行紧凑的机器人/连杆（link）/关节（joint）检查。

URDF 源读取器是轻量级标准库验证（validation）器。它检查本技能使用的生成子集；当置信度重要时，消费者特定的解析器和网格（mesh）加载兼容性仍应在目标运行时进行冒烟测试。
