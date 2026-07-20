# URDF 工作流（workflow）

在编辑机器人描述结构、参考系（frame）放置、网格（mesh）引用、惯性参数（inertial）数据或生成的 URDF 输出时使用本参考。

## 编辑循环

1. 找到定义 `gen_urdf()` 的 Python 源码。
2. 将该 Python 源码视为源真相，将 `.urdf` 文件视为生成的。
3. 确定目标消费者和严格性要求：可视化、TF 树、仿真、规划或真实机器人集成。
4. 在更改参考系（frame）、原点、轴、限位、网格（mesh）缩放或惯性参数（inertial）之前，创建或更新设计清册（ledger）。
5. 应用 URDF 参考系（frame）语义：关节（joint）原点在父参考系（frame）中，子连杆（link）参考系（frame）在关节（joint）参考系（frame）处，关节（joint）轴在关节（joint）参考系（frame）中，视觉/碰撞（collision）/惯性参数（inertial）原点在连杆（link）参考系（frame）中。
6. 在生成器源码中有意识地编辑连杆（link）、关节（joint）、限位、轴、原点、惯性参数（inertial）、材料、视觉/碰撞（collision）几何和网格（mesh）文件名。
7. 仅使用 `scripts/urdf <source-file>`、`scripts/urdf <source-file> -o <output.urdf>` 或 `scripts/urdf <source-file>=<output.urdf>` 重新生成显式 URDF 目标。
8. 让生成时验证（validation）捕获结构和语义问题。修复生成器源码，而非手动编辑生成的 XML。
9. 如果网格（mesh）输出已更改，仅用所属的 CAD 或网格（mesh）工作流（workflow）重新生成受影响的显式输出。
10. 当可用时，将生成或修改的 `.urdf` 文件交接（handoff）给 `$cad-viewer` 以获取实时查看器链接。
11. 当可用时，运行消费者冒烟测试并报告未检查的内容。

## 空间推理约束规则（guardrails）

LLM 容易犯看似合理的空间错误。使用以下约束规则（guardrails）：

- 不要从模糊描述推断尺寸、手性、轴、网格（mesh）单位或关节（joint）符号。
- 不要静默镜像左右零件（part），除非镜像变换和符号更改是明确的。
- 不要假设视觉网格（mesh）原点等于连杆（link）参考系（frame）、碰撞（collision）参考系（frame）或质心。
- 不要假设 CAD 网格（mesh）单位是米。STL 文件通常不带可靠单位元数据。
- 不要仅通过偏移视觉网格（mesh）来编码运动学校正；除非视觉网格（mesh）确实偏移，否则应校正连杆（link）和关节（joint）参考系（frame）。
- 保留现有已验证（validation）的变换，除非任务明确要求更改。
- 为假设使用命名常量和注释。

## 标准连杆（link）标签

对每个代表物理机器人几何的连杆（link）使用以下标签：

- `inertial`：仿真器使用的质量、质心和惯性张量。
- `visual`：显示几何和可选材料。
- `collision`：物理和规划使用的接触几何。

仅参考系（frame）连杆（link）（如 `base_footprint`、光学参考系（frame）或工具中心标记参考系（frame））在不代表物理质量或几何时，可有意识地省略这些标签。

对于可动物理连杆（link），避免零质量或缺失质量，除非目标仿真器明确支持该建模选择。如果精确质量属性不可用，使用有记录的近似值，并使该近似值易于后续替换。

## 关节（joint）编写

对于每个关节（joint），确认：

- 父和子方向正确；
- 关节（joint）原点在父连杆（link）参考系（frame）中表达；
- 子连杆（link）参考系（frame）有意与关节（joint）参考系（frame）重合；
- 非固定关节（joint）轴在关节（joint）参考系（frame）中表达；
- 正向运动已记录；
- revolute 限位为弧度；
- prismatic 限位为米；
- continuous 关节（joint）不使用人为的有限上下限；
- fixed 关节（joint）用于参考系（frame）关系和刚性装配体（assembly）。

支持的关节（joint）类型可能因项目运行时而异。如果验证（validation）器/运行时仅支持 `fixed`、`continuous`、`revolute` 和 `prismatic`，则不要编写 `floating` 或 `planar` 关节（joint），除非消费者和验证（validation）路径支持它们。

## 网格（mesh）引用

URDF 网格（mesh）文件名应从生成的 URDF 文件视角稳定可访问，或使用消费者理解的 package URI 约定。

当前 `scripts/urdf` 验证（validation）路径接受任何非空网格（mesh）文件名或 URI。本地相对网格（mesh）路径相对于生成的 URDF 文件检查；除非通过 `read_urdf_source()` 提供 package 映射，否则 `package://...` 和远程引用会以警告形式保留未解析。

使用 package URI 时，确认消费环境解析 package 根的方式与生成的 URDF 预期相同。

不要将生成的 URDF XML 作为网格（mesh）放置的源真相。优先从拥有网格（mesh）实例放置的相同源数据派生视觉网格（mesh）引用。

当网格（mesh）引用指向生成资产时，保持所有权清晰：

- CAD 或网格（mesh）工作流（workflow）拥有网格（mesh）生成；
- URDF 生成拥有引用、缩放和放置；
- SRDF/MoveIt 工作流（workflow）拥有语义组、通过 `<group_state>` 命名的关节（joint）位姿（pose）和规划元数据。

## 碰撞（collision）几何

在每个应参与物理、接触或碰撞感知规划的 `<link>` 下添加碰撞（collision）几何。不要在关节（joint）上编码碰撞（collision）行为。

每个连杆（link）使用一个或多个 `<collision>` 块。`<origin>` 在连杆（link）参考系（frame）中表达，与 `<visual>` 相同，且网格（mesh）缩放必须与导出网格（mesh）的单位匹配：

当前 `scripts/urdf` 验证（validation）器允许视觉和碰撞（collision）几何使用 `<mesh>`、`<box>`、`<cylinder>` 或 `<sphere>`。

```xml
<link name="forearm_link">
  <visual>
    <origin xyz="0 0 0" rpy="0 0 0" />
    <geometry>
      <mesh filename="package://robot_description/meshes/forearm.stl" scale="0.001 0.001 0.001" />
    </geometry>
  </visual>
  <collision>
    <origin xyz="0.12 0 0" rpy="0 1.57079632679 0" />
    <geometry>
      <cylinder radius="0.035" length="0.24" />
    </geometry>
  </collision>
</link>
```

优先选择简化的碰撞（collision）几何，而非详细的视觉网格（mesh）。从最简单到最具体的良好选项：

- 当基本体 `<box>`、`<cylinder>` 或 `<sphere>` 几何能很好地近似零件（part）时使用；
- 从 CAD 导出的粗糙、封闭碰撞（collision）网格（mesh）；
- 作为加载和冒烟测试临时回退的视觉网格（mesh）。

在生成器源码中，显式建模碰撞（collision），而非手动编辑生成的 URDF。常见模式是在每个连杆（link）规范中的 `visuals` 旁添加 `collisions` 集合，并使用与视觉网格（mesh）相同的原点和缩放辅助代码输出它。

## 惯性参数（inertial）

对于每个物理连杆（link），当目标仿真器或动力学消费者需要质量属性时，使用显式 `inertial` 块。

惯性参数（inertial）原点是连杆（link）参考系（frame）中的质心。它不自动是视觉网格（mesh）原点、碰撞（collision）原点或连杆（link）原点。

当精确质量属性不可用时，使用有记录的近似值并使其易于替换。清晰标记近似质量、质心和惯性常量。

## 冒烟测试

生成时验证（validation）后，使用最相关的可用冒烟测试：

- 在 RViz 或等效可视化中加载以检查可见放置；
- 运行 robot_state_publisher 或等效工具检查 TF 树；
- 在 Gazebo/Ignition 或其他仿真器中加载以用于物理消费者；
- 仅在 URDF 结构稳定后在 MoveIt 中加载，然后通过 SRDF 工作流（workflow）处理语义数据。

报告运行的冒烟测试以及任何会实质影响置信度的跳过检查。
