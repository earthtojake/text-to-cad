# build123d 建模模式

当编写或修复 build123d Python 源码时阅读本文件。

## 建模目标

创建有效的 STEP 就绪 BREP 模型，而非可视化网格（mesh）。优先采用闭合实体、显式标签和稳定的参数化尺寸。定义 `gen_step()` 返回 STEP 就绪形状或带标签复合体；CLI 拥有输出路径（见 `step-generation.md`）。

## 设计策略

在编写几何代码之前决定零件（part）的构造方式：

- **选择使规格尺寸成为直接参数的构造方式。** 轮廓驱动的形状采用一个闭合草图加 `extrude`/`revolve`/`sweep`/`loft`；积木加特征式零件（part）采用基础实体加减特征。优先选择能让用户的控制尺寸作为命名参数出现而非派生值的构造方式。
- **在建模前决定零件（part）还是装配体（assembly）。** 单独制造、采购或可移动的实体应归入带标签的装配体（assembly）（见 `positioning.md`）；整体制造意图采用单一融合实体。避免无标签的实体复合体——没有实例标签的多实体输出在检查和查看器审查中会丢失可追溯性。
- **在雕塑之前从功能基准（datum）选取原点和方向。** 在配合（mating）接口、安装平面或对称轴上建模；零件（part）类型原点默认值见 `positioning.md`。
- **安排操作顺序，使脆弱步骤排在最后，失败局部化。** 基础实体 -> 主要添加 -> 减特征 -> 壳体 -> 穿壁孔 -> 圆角（fillet）和倒角（chamfer）最后。圆角（fillet）是最易失败的操作，且每个布尔操作都会使选择器（selector）失效，因此推迟它们。组织源码使每个特征都是一个命名步骤——每个特征一个函数或一个独立的中间变量——这样失败的操作精确指向一个特征，参数修改只触及一个明显位置。
- **让布尔工具超长。** 将切割工具延伸过其进入和退出的面；对于贯穿切割，大约超出两面各 1 mm。重合或共面的工具/目标面是典型的内核失败。在一次组合操作中切割重复或阵列特征。
- **在生成之前检查比例是否合理。** 将预期包围盒与真实世界物体比较，壁厚与整体尺寸比较，特征位置与边缘和相邻特征比较。数量级和碰撞（collision）错误会通过几何验证（validation）但在视觉审查中失败。

## 拓扑（topology）栈

按此顺序思考：

```text
Vertex -> Edge -> Wire -> Face -> Shell -> Solid -> Compound
```

对于装配体（assembly），一致使用这些仓库拓扑（topology）术语：

- **实例（Occurrence）**：装配体（assembly）树中的已放置节点。一个实例拥有父节点、变换、路径和面向用户的角色，如 `lid` 或 `m3_screw:front_left`。
- **形状（Shape）**：实例内导出的几何/实体。形状行拥有拓扑（topology）；面和边属于形状，而形状属于实例。
- **面/边**：由形状拥有的可选拓扑（topology）。不要假设任意面或边具有持久的意图标签；按实例、形状、序号、曲面/曲线类型和测量几何来检查它们。

检查拓扑（topology）时，遵循 `assembly occurrence -> shape/body -> faces -> edges`。每个面/边行应能通过 `occurrenceId` 和 `shapeId` 双向追溯。

对于正常 STEP 输出，返回以下之一：

- 有效的 `Solid`
- 有效实体的复合体
- 带标签的装配体（assembly）复合体

避免返回松散的线、开放的面或构造曲面，除非用户明确请求。

## 参数优先

将有意义的尺寸放入命名变量：

```python
width = 80.0
depth = 50.0
thickness = 6.0
hole_diameter = 4.5
hole_offset_x = 30.0
hole_offset_y = 17.5
```

避免将重要数字埋在几何调用内部。

## 坐标系

声明或注释约定：

```text
Origin: center of primary part or chosen mating datum
XY: main base/sketch plane
+Z: up/extrusion direction
```

有意识地使用 `Location`、`Plane` 和 `Axis`。对于定位敏感任务和源码级装配体（assembly）关系，阅读 `positioning.md`。

## 构建器上下文

使用与几何匹配的上下文：

```python
with BuildLine() as path:
    ...

with BuildSketch() as profile:
    ...

with BuildPart() as part:
    ...
```

典型流程：

```text
curves/paths -> sketches/profiles -> solids/features -> labels -> STEP
```

## 选择实践

尽可能避免脆弱的拓扑（topology）顺序。按以下方式选择：

- 轴或法线
- 位置或边界位置
- 平面分组
- 特征意图
- 稳定的构造平面
- 已检查的局部选择器（selector）引用，用于下游验证（validation）

对于源码操作，优先采用稳健的选择器（selector），如按轴或位置的顶/底，而非任意列表索引。

## 装配体（assembly）和定位

对于装配体（assembly），保持本文件聚焦于 BREP 建模模式和标签。使用 `positioning.md` 作为以下内容的唯一真相源：

- 零件（part）局部坐标约定
- 何时使用 `cadpy.assembly.AssemblyHelper`、build123d 关节（joint）或显式 `Location` 变换
- `connect_to()` 行为
- CLI `inspect align` 作为只读选择器（selector）对对齐验证（validation）
- 参考系（frame）、测量和定位报告期望

## 标签和装配体（assembly）

用原生 build123d 标签为每个导出的零件（part）和装配体（assembly）子项打标签。通过 `cadpy.assembly` 助手优先采用简洁的意图标签：

```python
from cadpy.assembly import AssemblyHelper, label_shape

asm = AssemblyHelper("electronics_enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

boss = label_shape(Cylinder(radius=3.0, height=12.0), "m3_boss", "front_left")
```

不要用拓扑（topology）类别作为标签前缀，如 assembly、component、feature、datum、mate 或 hardware。装配体（assembly）树和拓扑（topology）检查已经暴露了这些结构类别。将标签用于拓扑（topology）无法可靠推断的意图：角色、放置、接口、重复或配合（mating）目的。当特征作为 `Compound` 中的带标签子形状保留时，特征标签在 STEP 导出中最能存活；被布尔减去或融合的特征历史应由源码参数、命名基准（datum）和验证（validation）引用表示，而非假设持久的特征标签。

为检查打标签：

- 为根装配体（assembly）打标签。
- 为每个导出的零件（part）、子装配体（subassembly）/模块和重复组件实例打标签。
- 使用实例标签表示装配体（assembly）角色和放置，尤其是重复零件（part）：`m3_screw:front_left`、`m3_screw:rear_right`。
- 在有用时为保留的导出几何/实体角色使用形状标签。
- 仅当该几何作为子形状导出时才使用特征/基准（datum）标签。
- 使用命名的配合（mating）基准（datum）表示源码级定位意图，然后验证（validation）导出的 STEP 拓扑（topology）和实例参考系（frame）。

实例和形状标签通过 STEP 名称导出，并在可用时在 `STEP_topology` 中呈现。查看器使用实例标签作为装配体（assembly）/树引用，使用形状标签作为形状引用。面和边从 `occurrenceId` 和 `shapeId` 继承其上下文；除非存在经显式测试的支持，否则不要承诺持久的面/边意图标签。

对于重复零件（part），保持实例标签、变换或关节（joint）连接显式，并在生成后检查参考系（frame）/定位。

## 常见失败模式

- 圆角（fillet）半径大于局部边几何。
- 开放草图轮廓产生无效或缺失的面。
- 面选择器（selector）在布尔或圆角（fillet）后发生变化。
- 零件（part）原点任意，后续对齐检查变得模糊。
- 源码级关节（joint）被当作持久的 STEP 约束，而非一次性源码放置操作。
- 关节（joint）标签缺失、重复或附加到错误的局部基准（datum）。
- `.connect_to()` 固定了关系的错误一侧，移动了本应保持固定的零件（part）。

当生成或验证（validation）失败时使用 `repair-loop.md`。
