# CAD Skills 中文版

本目录是 [text-to-cad](https://github.com/earthtojake/text-to-cad) 项目 `skills/` 的中文翻译版。
原项目是一个面向 CAD、机器人和硬件设计 agent 的技能库，提供从自然语言生成、检查、
验证到制造交接的全流程工作流。

翻译说明见 [TRANSLATION_GUIDE.md](./TRANSLATION_GUIDE.md)。

## 技能清单

共 11 个技能，涵盖 CAD 建模、机器人描述、制造、查看器等领域。

### cad

创建、修改、检查和验证（validation）以 STEP 为先的参数化 CAD 零件（part）和装配体
（assembly）。用于自然语言 CAD 规格说明、参考图像、2D 技术图纸、STEP/STP 生成或直接检查、
Python CAD 源码、源码级关节（joint）、选择器（selector）引用、几何事实、测量、配合
（mating）增量、快照（snapshot），以及从 CAD 几何生成的 STL/3MF/原生 GLB 等附带产物
（sidecar）输出。

- 目录：`cad/`
- 核心契约：`gen_step()` 返回 build123d 形状或装配体信封

### urdf

URDF 机器人描述生成及默认生成时验证（validation）。在创建、编辑、重新生成、检查或调试
`.urdf` 文件、Python `gen_urdf()` 源码、机器人连杆（link）、关节（joint）、限位、
惯性参数（inertial）、视觉/碰撞（collision）几何、网格（mesh）引用、参考系（frame）约定
或生成的机器人描述产物（artifact）时使用。SRDF 技能用于 MoveIt2 语义组和 IK/路径规划语义；
cad-viewer 技能用于本地 MoveIt2 服务器控制；CAD 技能用于 STEP/STL/3MF/DXF/GLB 输出。

- 目录：`urdf/`
- 核心契约：`gen_urdf()` 返回 URDF XML

### srdf

MoveIt2 SRDF 生成、验证（validation）与规划语义（planning semantics）工作流（workflow）。
在创建、编辑、重新生成、检查或验证（validation） `.srdf` 文件、`gen_srdf()` 源、
MoveIt planning group、virtual joint、passive joint、end effector、group state、
disabled collision、与 URDF 关联的规划语义，或用于实时审查的 SRDF 交接（handoff）时使用。
机器人结构请使用 URDF skill，仿真器描述请使用 SDF skill，渲染、实时审查链接以及可选的
MoveIt2 控件请使用 cad-viewer skill。

- 目录：`srdf/`
- 核心契约：`gen_srdf()` 返回 SRDF XML

### sdf

SDFormat/SDF 模型（model）与世界（world）生成、校验及仿真器（simulator）交付。用于
`.sdf` 文件、SDFormat XML、Python `gen_sdf()` 源文件、模型（model）、世界（world）、
连杆（link）、关节（joint）、位姿（pose）、参考系（frame）、惯性（inertial）、
visual/collision 几何（geometry）、mesh URI、传感器（sensor）、光源（light）、物理
（physics）、插件（plugin）、include、Gazebo、静态 SDF 审查或仿真器特定的元数据。不用于
signed-distance-field 几何。

- 目录：`sdf/`
- 核心契约：`gen_sdf()` 返回 SDF XML

### dxf

从 Python ezdxf 源码生成、重新生成并验证（validation） 2D DXF 图纸。用于 DXF 文件、
`gen_dxf()` 源码、2D 轮廓、外形、模板、垫片、面板、展开图、激光/等离子/水刀切割排版，
以及 CAD 几何的 2D 图纸导出。

- 目录：`dxf/`
- 核心契约：`gen_dxf()` 返回 ezdxf 文档

### cad-viewer

启动或复用 CAD Viewer，并为显式 CAD、隐式 CAD、机器人描述文件和 G-code 文件返回评审链接。
当需要可视化评审 `.step`、`.stp`、`.implicit.js`、`.implicit.mjs`、`.glb`、`.stl`、
`.3mf`、`.gcode`、`.dxf`、`.urdf`、`.srdf` 或 `.sdf` 文件时使用，尤其是在从 CAD、
implicit-cad、G-code、URDF、SRDF 或 SDF 生成技能交接（handoff）后使用。

- 目录：`cad-viewer/`
- 作用：为其他技能提供可视化审查和交接链接

### step-parts

从 step.parts 查找、评估并下载常见可采购 CAD 零件（part），包括具名的现货执行器
（actuator）、舵机（servo）、电机、电子板、连接器、螺丝、螺栓、螺母、垫圈、轴承（bearing）、
支柱（standoff）以及其他目录元件。当 Codex 需要在创建简化的占位几何体之前搜索托管的
step.parts 目录、解析模糊的零件（part）名称/标准/别名/尺寸、选择匹配的零件、获取规范的
.step 文件、校验校验和，或使用 step.parts API/OpenAPI/目录端点进行标准零件（part）发现时
使用本技能。

- 目录：`step-parts/`
- 作用：装配体设计时检索现货标准件

### gcode

通过编排真实的切片器 CLI，从 3D 网格（mesh）文件生成、检查、试运行（dry-run）并静态验证
（validation）纯 FDM `.gcode`。当 Codex 需要将 `.stl`、`.obj`、未切片的 `.3mf`、`.ply`、
`.glb` 或 `.gltf` 切片为带打印机配置的 G-code、发现本地切片器后端、检查网格（mesh）是否已
准备好切片、或在任何打印机特定的交接（handoff）之前验证（validation）生成的 G-code 时使用。

- 目录：`gcode/`
- 核心流程：mesh -> 切片器 CLI -> `.gcode` -> 静态验证

### bambu-labs

对已验证（validation）的普通 `.gcode` 文件进行 dry-run、上传，并谨慎地从本地 Bambu Lab
发起打印作业，使用 Bambu LAN FTPS/MQTT 交接（handoff）。

- 目录：`bambu-labs/`
- 作用：Bambu Lab 打印机的 dry-run、上传和谨慎启动打印

### sendcutsend

审查 DXF 和 STEP/STP 上传文件，用于 SendCutSend.com 订单，基于其下单指南、目录和规格。仅用于
SendCutSend.com 预检报告，覆盖上传就绪性、所选材料/SKU/厚度/服务可用性，以及针对激光切割、
CNC 路由、折弯、攻丝、锪孔（countersink）、硬件压装和表面处理的专项检查。

- 目录：`sendcutsend/`
- 作用：SendCutSend.com 订单上传前的预检报告

### implicit-cad

创建、编辑、渲染并对浏览器原生 implicit CAD `.implicit.js` 和 `.implicit.mjs` 文件进行快照
（snapshot），使用 GLSL 有符号距离场、着色器图元、平滑布尔运算、TPMS 场以及直接由 CAD Viewer
进行 raymarch 渲染。实验性。

- 目录：`implicit-cad/`
- 核心契约：`.implicit.js` / `.implicit.mjs` 定义 SDF 模型

## 目录结构

```
skills_zh/
├── README.md                  # 本文件
├── TRANSLATION_GUIDE.md       # 翻译规范
├── bambu-labs/
│   ├── SKILL.md
│   └── references/
├── cad/
│   ├── SKILL.md
│   └── references/            # 9 个参考文档
├── cad-viewer/
│   ├── SKILL.md
│   └── references/
├── dxf/
│   └── SKILL.md
├── gcode/
│   ├── SKILL.md
│   └── references/
├── implicit-cad/
│   ├── SKILL.md
│   └── scripts/packages/implicitjs/README.md
├── sdf/
│   ├── SKILL.md
│   └── references/            # 12 个参考文档
├── sendcutsend/
│   ├── SKILL.md
│   └── references/
├── srdf/
│   ├── SKILL.md
│   └── references/            # 8 个参考文档
├── step-parts/
│   ├── SKILL.md
│   └── references/
└── urdf/
    ├── SKILL.md
    └── references/            # 6 个参考文档
```

## 技能间如何配合

### cad-viewer 是所有技能的统一可视化出口

几乎每个技能在完成工作后，都会把生成的文件路径交接（handoff）给 `$cad-viewer`，由它启动
或复用本地 CAD Viewer 并返回实时查看器链接。这是整个技能库的不可跳过环节——可视化验证
（validation）被视为与确定性检查同等重要。

```
cad / urdf / srdf / sdf / dxf / gcode / implicit-cad / step-parts / sendcutsend / bambu-labs
  │
  └──> $cad-viewer（启动 Viewer、返回查看链接、可选 MoveIt2 控件）
```

cad-viewer 自身不引用其他技能，它是纯粹的消费方：接收文件路径，提供可视化审查。

### cad 是几何生成的核心

cad 技能是 STEP-first 工作流的起点，其他多个技能依赖它产生的几何：

- **cad -> dxf**：当 DXF 是 3D 零件（part）的 2D 投影时，先用 `$cad` 生成并验证
  （validation）STEP 几何，然后在同一源码中添加 `gen_dxf()`，从内存中的 STEP/实体拓扑
  （topology）派生 DXF 轮廓，而非重复几何公式。
- **cad -> step-parts**：装配体（assembly）设计中，当遇到命名的现货执行器（actuator）、
  舵机（servo）、电机等可采购元件时，先搜索 `$step-parts` 获取规范 .step 文件，再导入到
  cad 中像任何编写的 part 一样使用。
- **cad -> sendcutsend**：sendcutsend 在预检时优先用 `$cad` 做 STEP/STP/DXF 几何检查、测量
  和验证，然后补充 SendCutSend 特有的材料/SKU/服务可用性检查。
- **cad -> gcode**：cad 可导出 STL/3MF 网格（mesh），这些网格是 gcode 切片的输入。

### 机器人描述的三件套：urdf -> srdf -> sdf

这三个技能共享相似的生成器契约（`gen_*()`）和设计清册（ledger）理念，但职责分明：

```
urdf（机器人结构：连杆/关节/惯性/网格）
  │
  ├──> srdf（MoveIt2 规划语义：规划组/末端执行器/禁用碰撞/组状态）
  │      └──> cad-viewer（可选本地 MoveIt2 服务器，交互式 IK/路径规划）
  │
  └──> sdf（仿真器模型/世界：物理/传感器/光源/插件/Gazebo）
         └──> cad-viewer（静态结构审查）
```

- **urdf** 定义机器人本体结构，是 srdf 和 sdf 的上游。
- **srdf** 不能独立存在，它依附于一个已验证（validation）的 URDF，为其添加 MoveIt2 规划语义。
  srdf 还会通过 cad-viewer 的本地 `moveit2_server` 提供交互式 IK 和路径规划控件。
- **sdf** 独立于 urdf/srdf，面向仿真器（如 Gazebo），但同样引用 mesh 和几何，这些通常来自 cad。

### 制造链：cad -> gcode -> bambu-labs

```
cad（生成 STEP，导出 STL/3MF 网格）
  │
  └──> gcode（网格 -> 切片器 CLI -> 带打印机配置的 .gcode -> 静态验证）
         │
         └──> bambu-labs（dry-run -> 上传 -> 谨慎启动本地 Bambu Lab 打印）
```

gcode 明确声明它只生成纯 `.gcode`，不创建 Bambu `.gcode.3mf` 归档，也不联系打印机。
bambu-labs 接收已验证（validation）的纯 `.gcode`，负责 FTPS/MQTT 交接和打印启动。

### sendcutsend 的双重依赖

sendcutsend 既是 cad 的下游（审查 cad 生成的 DXF/STEP），也直接引用 cad-viewer：

```
cad（生成 DXF/STEP 上传候选）
  │
  └──> sendcutsend（下单指南/目录/规格预检）
         ├── 用 $cad 做几何检查和测量
         └── 交接给 $cad-viewer 获取查看器链接
```

### implicit-cad 的独立性

implicit-cad 是实验性技能，使用 GLSL 有符号距离场（SDF）而非 BREP 几何。它独立于 cad 的
build123d 工作流，但仍通过 cad-viewer 进行渲染和快照（snapshot）。

### 配合关系总览

```
                    step-parts（检索标准件 .step）
                         │
                         v
    cad（STEP 生成核心）<──> dxf（2D 投影图纸）
      │  │  │
      │  │  └──> sendcutsend（上传预检）──> cad-viewer
      │  │
      │  └──> gcode（切片）──> bambu-labs（打印）
      │                          │
      v                          v
    STL/3MF 网格              cad-viewer
      │
      v
  urdf（机器人结构）
      │
      ├──> srdf（MoveIt2 规划语义）──> cad-viewer（+ MoveIt2 服务器）
      │
      └──> sdf（仿真器模型/世界）──> cad-viewer

  implicit-cad（SDF 实验）──> cad-viewer
```

所有技能最终都向 cad-viewer 交接，由它提供统一的可视化验证层。

## 源项目

- 原项目：[earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)
- 中文翻译基于 `skills/` 目录，保留相同的目录结构和 Markdown 结构
- CAD/机器人技术术语保留英文原文，采用中英对照形式（如"装配体（assembly）"）
