# SDF 设计台账（design ledger）

在编写 SDF XML 之前创建或更新本台账。台账可以放在响应中、项目笔记中或生成器源文件的注释中。目标是在空间和仿真器假设变成难以审计的 XML 之前将其外化。

## 文档

| 字段 | 值 |
|---|---|
| 输出路径 | |
| 源文件 | |
| SDF 版本 | `1.12`，除非有约束 |
| 文档类型 | 模型（model）/ 世界（world）/ 世界中的模型（model-in-world） |
| 目标消费者 | Gazebo / 其他仿真器 / 仅可视化 / 模型（model）包 |
| 单位 | 米、千克、秒、弧度，除非另有文档说明 |
| 坐标约定 | 类 REP-103 / 仿真器特定 / 已记录的例外 |
| 是否需要世界（world）支持 | 是/否；原因 |
| 可选外部检查 | `gz sdf --check`、仿真器加载、CAD Viewer、其他 |

## 模型或世界范围

| 项目 | 值 |
|---|---|
| 模型（model）/世界（world）名称 | |
| 静态或动态 | |
| 规范连杆（link），如相关 | |
| 模型/世界位姿（pose） | xyz + rpy/四元数 |
| 模型/世界位姿（pose） `relative_to` | |
| include | URI + 用途 |
| 世界物理（physics）/光源（light）/插件（plugin） | 源和目标仿真器 |

## 参考系（frame）

| 参考系（frame） | 作用域 | 附属于（attached to） | 位姿（pose） | 位姿（pose） `relative_to` | 用途 | 来源 |
|---|---|---|---|---|---|---|
| | | | | | | |

当多个传感器（sensor）、嵌套模型（model）、工具参考系（frame）、插件（plugin）参考系（frame）或重复变换（transform）依赖同一关系时，使用命名参考系（frame）以提高清晰度。

## 连杆（link）

| 连杆（link） | 物理 / 参考系（frame）式 | 位姿（pose） | 位姿（pose） `relative_to` | 惯性（inertial）来源 | 附加传感器（sensor）/插件（plugin） | 备注 |
|---|---|---|---|---|---|---|
| | | | | | | |

物理动态连杆（link）需要惯性（inertial）。参考系（frame）式连杆（link）仅在已记录时可省略惯性（inertial）。

## 关节（joint）

| 关节（joint） | 类型 | 父级 | 子级 | 位姿（pose） | 位姿（pose）参考系（frame）/ `relative_to` | 轴 | 轴参考系（frame） / `expressed_in` | 极限（limit） | 正向运动 | 来源 |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

对于 revolute 和 prismatic 关节（joint），记录极限（limit）单位：revolute 用弧度，prismatic 用米。continuous 关节（joint）不应给予人为的有限位置极限，除非记录了仿真器特定原因。

## 几何（geometry）

| 所有者 | visual/collision | 名称 | 几何类型 | 位姿（pose） | 位姿（pose） `relative_to` | URI 或尺寸 | mesh 单位 | 缩放 | 来源 |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

collision 几何应根据仿真成本和稳定性选择，而非仅凭视觉相似性。

## 惯性（inertial）

| 连杆（link） | 质量 | 质心位姿（pose） | 惯性张量（inertia tensor） | 方法/来源 | 置信度 |
|---|---|---|---|---|---|
| | | | | | |

清楚标记近似值。极小、零、负或猜测的惯性（inertia）对仿真风险很高。

## 传感器（sensor）和插件（plugin）

| 元素 | 父级 | 位姿（pose）/参考系（frame） | 文件名/类型 | 参数 | 来源文档 | 假设 |
|---|---|---|---|---|---|---|
| | | | | | | |

不要编造插件（plugin）文件名、topic、参考系（frame）名称、命名空间、控制器参数或更新频率。应从仿真器文档或用户提供的配置中推导。

## Mesh URI 策略

| URI 类型 | 是否允许？ | 解析预期 | 备注 |
|---|---|---|---|
| 相对本地路径 | | 相对于生成的 `.sdf` 位置 | |
| `file://` | | 绝对本地文件 | |
| `model://` | | 仿真器模型（model）路径 | |
| `package://` | | 仿真器/ROS 包环境 | |
| `fuel://`、`http://`、`https://` | | 外部资源 | |

## 需报告的假设

列出每个猜测或推断的值：

- 变换（transform）或位姿（pose）；
- 轴符号或正向运动约定；
- mesh 单位或缩放；
- 质量、质心或惯性（inertia）；
- 目标仿真器行为；
- 插件（plugin）参数；
- 未解决的外部 URI；
- 跳过的校验或冒烟测试。

如果某个值无法推导或安全假设，仅当用户要求占位符时才生成最小占位符，并标注为占位符。

## 简洁响应模板

```text
SDF source: path/to/source.py
Generated target: path/to/output.sdf
Target consumer: Gazebo Harmonic, SDF 1.12
Bundled validation: passed with 2 warnings
External checks: gz sdf --check skipped, gz not installed
Assumptions:
- Assumed mesh units are meters.
- Assumed camera optical frame follows simulator plugin documentation.
```
