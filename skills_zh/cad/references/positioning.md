# 定位逻辑、joint 与 mating

当几何体具有 mating 接口、重复特征、assembly 子件、轴、datum、运动或用户指定的对齐时，请阅读此文件。这是 assembly 定位、part 局部原点、build123d joint、显式 `Location` 变换、CLI `inspect align` 以及定位报告内容的权威参考。

## 核心规则

定位在源码中编写，并在生成后进行 validation。不要通过视觉拖拽或编辑导出的 STEP 几何体来定位 part。使用 build123d 参数、局部坐标系、`Location` 变换、`Plane`/`Axis` datum、`cadpy.assembly.AssemblyHelper` 关系、适当时的源码级 `Joint` 对象，以及带标签的 assembly 子件。

## 术语

仔细使用以下术语：

- **AssemblyHelper** 是来自 `cadpy.assembly` 的首选生成脚本包装器。它记录语义关系，如 `face_to_face`、`coaxial`、`revolute` 和 `linear`，然后用原生 build123d joint 实现这些关系。
- **build123d joint** 是源码级对象，如 `RigidJoint`、`RevoluteJoint`、`LinearJoint`、`CylindricalJoint` 和 `BallJoint`。它们附加到 `Solid` 或 `Compound` 对象上，可以用 `connect_to()` 重新定位 part。
- **CLI `inspect align`** 是一个 selector 对验证（validation）工具。它计算 STEP/CAD 条目中所选局部参考之间的只读平移 delta。它不编辑源码、不修补导出的 STEP 文件，也不代表已编写的 mate 特征。这是定义该区别的唯一位置；本技能其余部分均假定此区别成立。
- **Mating intent** 是设计关系：flush、居中、coaxial、offset、铰链式、滑块式，或其他由 datum 驱动的关系。

在适当的情况下，使用 `AssemblyHelper` 和 build123d joint 来表达和计算源码 assembly 放置，然后使用 CLI 检查来 validation 生成的 STEP。

## 首选 assembly 结构

对于 assembly，优先使用 mate/joint 驱动的结构，而非任意变换：

```text
root component
-> part-local coordinate systems
-> named datums / joint locations
-> AssemblyHelper semantic relationships backed by native build123d joints
-> labeled Compound assembly with verbose native labels
-> refs/measure/frame/align validation
```

数值 `Location(...)` 通常应对应于一个明确的 datum、offset、clearance、螺钉轴、面接触或 joint 关系。

将一个功能单元——一个轴承（bearing）、一个齿轮箱级、一套紧固件——在放置、推理或作为单元重复时，用 `asm.add_module(name, children)` 分组为一个子 assembly 节点；这样嵌套实例引用（如 `#o1.12.1`）就能保持有意义。

## Part 局部定位

对于每个 part，在建模前定义一个局部坐标系约定：

```text
- Origin: center, base datum, mounting interface, or functional axis.
- XY plane: main sketch/base plane unless another datum is dominant.
- +Z: extrusion/up direction.
- Named dimensions: offsets, hole spacing, boss spacing, clearances.
- Datum features: mating faces, screw axes, centerlines, locating tabs, rails.
```

良好的默认值：

- 对称的独立 part：原点在实体中心。
- 板：原点在轮廓中心；厚度沿 Z 方向。
- Enclosure：原点在轮廓中心；base/lid mating 面由 Z 参数控制。
- 轴/旋钮/轴对称 part：原点在旋转轴上。
- Mating 适配板：原点在主安装 datum 或螺栓孔阵中心。

## Part 内部特征放置

使用命名参数和局部坐标：

```python
hole_offset_x = 30
hole_offset_y = 17.5
hole_positions = [
    (-hole_offset_x, -hole_offset_y),
    ( hole_offset_x, -hole_offset_y),
    (-hole_offset_x,  hole_offset_y),
    ( hole_offset_x,  hole_offset_y),
]

with Locations(*hole_positions):
    Hole(radius=hole_diameter / 2)
```

避免在几何体调用中使用不可追溯的放置常量。将所有有意义的 offset 放入参数中。

## AssemblyHelper 模式

为生成的 assembly 脚本使用 `AssemblyHelper`。它保持面向 LLM 的代码聚焦于 intent，同时仍使用原生 build123d 标签、`Joint` 对象和 `Compound` assembly。

```python
from build123d import *
from cadpy.assembly import AssemblyHelper

base_height = 30.0
lid_thickness = 3.0
gasket_gap = 0.5

asm = AssemblyHelper("enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

base_seat = asm.rigid_frame(
    base,
    "lid_seat",
    Location((0, 0, base_height / 2)),
)
lid_underside = asm.rigid_frame(
    lid,
    "underside",
    Location((0, 0, -lid_thickness / 2)),
)

asm.face_to_face(base_seat, lid_underside, offset=gasket_gap)

def gen_step():
    return asm.build()
```

固定的目标列在前面，移动的目标列在后面。在上面的示例中，base 保持固定，lid 移动。helper 在源码中记录该关系，并在底层调用原生 build123d `connect_to()`；导出的 STEP 包含已解析的静态放置和原生 assembly 标签，而非持久的外部约束。

有意识地使用 helper 标签：

```python
standoff = asm.feature(Cylinder(radius=3.0, height=12.0), "m3_standoff", "front_left")
hinge_axis = asm.rigid_frame(lid, "hinge_axis", Location((0, -25, 0)))
```

Assembly 标签命名根实例。`asm.add()` 标记子组件实例及其导出的形状上下文。对于重复的硬件或库 part，使用角色/位置标签，如 `front_left` 和 `rear_right`，这样 STEP topology 和查看器选择在导出后仍可追溯。

当被标记的几何体保持为 `Compound` 中的子形状时，特征标签保存得最好。对布尔减去或融合的特征历史上的标签不是可靠的 STEP 特征历史。

使用与原生 build123d joint 输入匹配的 frame 方法：`rigid_frame()` 和 `ball_frame()` 接受一个 `Location`；`revolute_frame()`、`linear_frame()` 和 `cylindrical_frame()` 接受一个 `Axis` 加上可选的原生范围/参考参数。

## 导入的组件

对于购买或下载的 part（参见 `$step-parts`），导入 STEP 文件并像任何编写的 part 一样添加它：

```python
from build123d import import_step

servo = asm.add(import_step("models/parts/sg90_servo.step"), "servo")
```

导入的几何体不是在此处编写的，因此不要假定其原点或方向。从检查的几何体推导 mating frame：对导入的 part 运行 `refs --facts --planes --positioning` 和 `measure`，然后从测量的面、轴和螺栓孔阵定义 `asm.rigid_frame(...)` 位置。像 validation 编写的 mate 一样 validation 结果 mate。

## 何时使用 build123d joint

当 assembly intent 作为 part datum 之间的关系比作为原始变换更清晰时，使用 `AssemblyHelper`/build123d joint：

- lid 到 base、cover 到 frame、bracket 到 rail、flange 到 pipe、销到孔、轴到轴承（bearing）
- 铰链、滑块、螺钉式、圆柱、球/万向节，或其他运动定位的 assembly
- 重复或库组件中已暴露 joint 的
- 一个 dimension 的变化应重新计算 part 放置的源码 assembly

当直接 `Location(...)` 变换是参数化且有文档记录时，对于简单静态布局是可以接受的，例如一排相同的 spacer 或视觉分解图。

原始 build123d joint 对于 `AssemblyHelper` 未覆盖的高级情况是可以接受的，但保留相同的固定优先方向性：在固定/根 joint 上调用 `connect_to()`，并将移动 part 的 joint 作为 `other` 传入。`connect_to()` 是一个源码生成操作。它为生成的模型重新定位移动 part；它不是导出 STEP 文件中的持久外部约束。

## Joint 类型选择

使用表达源码级关系的最简单 joint：

- `RigidJoint` / `asm.rigid_frame()`：固定放置、面对面贴合、安装 datum、具有已知接口的导入组件。
- `RevoluteJoint` / `asm.revolute_frame()`：铰链或旋转 pose；用 `Axis` 定义，并用角度参数驱动以获得静态 STEP pose。
- `LinearJoint` / `asm.linear_frame()`：滑块、锁扣、伸缩组件；用 `Axis` 定义，并用位置参数驱动。
- `CylindricalJoint` / `asm.cylindrical_frame()`：组合轴向平移和旋转，如螺钉式或销在槽中的关系。
- `BallJoint` / `asm.ball_frame()`：万向节或球形方向关系；用 `Location` 和角度范围定义。

当只有最终静态放置重要且不存在有意义的 joint datum 时，使用显式 `Location` 变换并进行 validation。

## Assembly 定位工作流（workflow）

1. 选择固定/根组件。
2. 在建模子件放置之前，定义 part 局部 frame 和 datum。
3. 识别功能 datum，如 mating 面、螺钉轴、铰链轴、滑动轴、定位凸耳、垫圈 offset 或接触面。
4. 用 `asm.rigid_frame()`、`asm.revolute_frame()`、`asm.linear_frame()` 或其他 helper frame 方法为每个子件命名源码级 joint 或 mating datum。
5. 在改善源码清晰度的地方使用 `AssemblyHelper` 关系方法，否则使用参数化的 `Location` 变换。
6. 用 `asm.build()` 构建带标签的 `Compound` assembly。
7. 通过 Python 源码生成 assembly，而不是重新导入生成的 STEP（参见 `step-generation.md`）：

```bash
python scripts/step path/to/assembly.py
python scripts/inspect refs path/to/assembly.step --facts --planes --positioning
```

## CLI 对齐 validation

生成后，从 `refs --positioning` 返回的局部 selector ref 中选择移动和目标 ref，并计算 delta：

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

对共面面对齐使用 `--mode flush`。对中心线、面中心或对称对齐使用 `--mode center`（在所选参考支持时）。如果返回的 delta 超出公差，应用源码级修正（见下文），重新生成，并重新运行检查。

## Frame validation

使用 `frame` 检查实例或 selector 的世界 frame：

```bash
python scripts/inspect frame path/to/assembly.step '#selector'
```

在以下情况下使用：

- 子件方向错误
- mating 面在世界坐标中 offset
- 轴应与 X/Y/Z 对齐
- 重复的 part 应共享方向
- 下游任务需要稳定的坐标系

## 测量 validation

使用 `measure` 进行标量检查：

```bash
python scripts/inspect measure path/to/assembly.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis z
```

示例：

- lid 底面到 base 顶面对于 flush 接触应为 0 mm
- 两个螺钉轴应具有匹配的 X/Y 位置
- bracket 安装面应距 datum 面指定距离
- spacer 高度应等于请求的 offset

## 源码级定位修正

当定位检查失败时，在源码中修复以下之一：

- 子件 `Location` 平移
- 子件 `Location` 旋转
- `AssemblyHelper` 关系固定/移动顺序或 offset
- build123d joint 位置或轴
- part 局部原点约定
- 特征 offset 参数
- 草图平面
- 工作平面选择
- assembly 层次结构
- 对称放置符号

然后重新生成。不要直接修补导出的 STEP。

## 报告定位

在最终回复中，仅报告已运行的检查：

```text
Positioning/joints:
- source used RigidJoint lid_seat -> underside
- base/lid Z mate flush, delta 0.00 mm
- screw boss axis alignment: checked in XY by measurement
- lid occurrence frame: +Z up, origin at assembly centerline
```

如果不存在定位敏感的特征，则说：

```text
Positioning: not applicable beyond centered part-local origin.
```

如果某个 mate 或对齐是预期的但未检查，则说 `not checked`；不要暗示成功。
