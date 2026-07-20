# URDF 设计清册（ledger）

在创建或编辑 URDF 生成器之前使用本参考。清册（ledger）是书面的空间模型，可防止静默的参考系（frame）、轴、单位和网格（mesh）缩放错误。

清册（ledger）可以位于生成器源码注释、相邻项目文档、README 或任务说明中。它必须足够具体，使另一位工程师无需逆向工程 XML 即可审计生成的 URDF。

## 必需章节

### 机器人元数据

记录：

- 机器人名称
- 目标消费者：RViz、robot_state_publisher、Gazebo/Ignition、MoveIt、真实机器人驱动器或其他
- 单位约定：米、千克、秒、弧度，除非项目明确另有说明
- 参考系（frame）约定：适用时采用 REP-103 风格的本体约定，或有记录的例外
- 网格（mesh）单位约定：米、毫米、英寸或其他
- 尺寸来源：CAD、图纸、测量数据、供应商文档、现有 URDF 或假设

### 连杆（link）清册（ledger）

对于每个连杆（link），记录：

| 字段 | 含义 |
|---|---|
| 连杆（link）名称 | 精确的 URDF `<link name="...">` 值。 |
| 角色 | 物理连杆（link）、仅参考系（frame）连杆（link）、传感器参考系（frame）、工具参考系（frame）、基准参考系（frame）（datum）或其他。 |
| 参考系（frame）定义 | 连杆（link）参考系（frame）的位置及其轴向。 |
| 父关节（joint） | 创建此子连杆（link）参考系（frame）的关节（joint），根节点为 `none`。 |
| 视觉几何 | 基本体或网格（mesh）源，原点相对于连杆（link）参考系（frame）。 |
| 碰撞（collision）几何 | 基本体或网格（mesh）源，原点相对于连杆（link）参考系（frame）。 |
| 惯性参数（inertial）来源 | CAD 质量属性、供应商数据、近似值或有意省略。 |

仅参考系（frame）连杆（link）（如 `base_footprint`、光学参考系（frame）和 `tool0`）可以省略惯性参数（inertial）、视觉和碰撞（collision）块。应明确标记为仅参考系（frame），而非让意图含糊不清。

### 关节（joint）清册（ledger）

对于每个关节（joint），记录：

| 字段 | 含义 |
|---|---|
| 关节（joint）名称 | 精确的 URDF `<joint name="...">` 值。 |
| 类型 | 当前 `scripts/urdf` 验证（validation）器支持 `fixed`、`revolute`、`continuous` 或 `prismatic`；仅当项目有不同支持的验证（validation）路径时才记录 `floating` 或 `planar`。 |
| 父连杆（link） | 其参考系（frame）表达关节（joint）原点的连杆（link）。 |
| 子连杆（link） | 其参考系（frame）在关节（joint）参考系（frame）处创建的连杆（link）。 |
| 原点 xyz/rpy | 从父连杆（link）到关节（joint）参考系（frame）的父连杆（link）参考系（frame）变换。 |
| 轴 | 在关节（joint）参考系（frame）中表达的轴向量，用于可动关节（joint）。 |
| 限位 | revolute 为弧度，prismatic 为米，continuous 无有限上下限。 |
| 正向运动 | 正向关节（joint）运动在物理上的作用。 |
| 来源 | CAD、图纸、测量数据、现有模型或有记录的假设。 |

不要在缺少明确正向运动约定的情况下编写可动关节（joint）。轴的符号是模型的一部分，而非装饰性细节。

### 几何清册（ledger）

对于每个视觉或碰撞（collision）项，记录：

| 字段 | 含义 |
|---|---|
| 连杆（link） | 所属连杆（link）。 |
| 种类 | `visual` 或 `collision`。 |
| 几何类型 | `mesh`、`box`、`cylinder` 或 `sphere`。 |
| 来源 | CAD 导出、基本体近似、供应商网格（mesh）、生成网格（mesh）或临时占位符。 |
| 原点 xyz/rpy | 从连杆（link）参考系（frame）到几何参考系（frame）的变换。 |
| 缩放 | 网格（mesh）缩放（如适用）。 |
| 单位 | 网格（mesh）源单位和表达米所需的 URDF 缩放。 |

视觉几何用于显示。碰撞（collision）几何用于接触、规划和物理。它可以有意比视觉几何更简单。

### 惯性参数（inertial）清册（ledger）

对于每个物理连杆（link），记录：

| 字段 | 含义 |
|---|---|
| 质量 | 千克。 |
| 质心 | 在连杆（link）参考系（frame）中的惯性参数（inertial）原点 xyz。 |
| 惯性张量 | 张量值和参考系（frame）。 |
| 来源 | CAD 质量属性、供应商数据、计算、近似值或有意省略。 |
| 置信度 | 精确、估计、占位符或未知。 |

不要静默地将视觉原点复制到惯性参数（inertial）原点。视觉参考系（frame）、碰撞（collision）参考系（frame）、连杆（link）参考系（frame）和质心都可能不同。

### 假设清册（ledger）

记录每个推断或猜测的值，包括：

- 未知尺寸
- 网格（mesh）单位
- 符号约定
- 关节（joint）轴
- 父/子方向
- 视觉或碰撞（collision）偏移
- 质量、质心和惯性近似值
- 仅参考系（frame）连杆（link）意图
- 未验证（validation）的 package URI 解析

在生成器代码中为假设值使用命名常量。优先选择如 `ASSUMED_BASE_TO_SHOULDER_Z_M` 的名称，而非无标签的数字字面量。

## 当信息缺失时

如果空间信息缺失，不要编造看起来精确的变换。选择以下结果之一：

1. 保持现有源数据不变；
2. 创建带有明确假设注释的仅参考系（frame）或占位符结构；
3. 使用命名清晰的近似常量；
4. 当工作流（workflow）允许交互时，请求尺寸或 CAD 数据；
5. 报告生成的模型结构有效但在空间上是临时的。

明确标注的临时 URDF 是可接受的。看似合理但未记录的 URDF 则不可接受。
