# CAD 简介

当将用户请求——散文、参考图像、技术图纸或其组合——转换为 CAD 简介时阅读本文件。简介是内部笔记脚手架；不要要求用户填写，也不要要求用户提供 JSON。如果用户自愿提供 JSON，提取相同信息但继续以散文笔记和 build123d 源码进行工作流（workflow）。

## 目标

在编写源码或运行工具之前，将请求转换为可操作的建模简介。每种输入模态都汇入同一个简介；下游工作流（workflow）不变。

简介应回答：

- 正在建模的是什么，是零件（part）、装配体（assembly）、修改、检查任务还是次要输出请求？
- 指定了哪些尺寸和单位，哪些缺失尺寸是可推断的？
- 需要哪些特征？
- 哪些面、轴、原点、关节（joint）或接口控制定位？
- 请求了哪些输出文件？
- 报告成功之前必须验证（validation）什么？

当输入冲突时，有尺寸的来源优先于图像比例。当两个有尺寸的来源冲突——散文说一个值，图纸标注说另一个——标记冲突，而非默默选择。

## 参考图像

没有说明尺寸的图像是设计意图，而非规格：

- 从一个说明的尺寸或画面中的已知物体建立比例；如果两者都不存在且配合（mating）关系重要，那就是需要提出的一个澄清问题。
- 从图像估算剩余比例，并将其作为假设记录，与任何其他推断值一样。
- 在简介中区分复刻（"对这零件（part）建模"）与启发（"类似这样的东西"）；复刻提高保真度期望，启发留有自由度。
- 对于复刻，规划从参考图像视角拍摄的快照（snapshot），并在视觉审查时与图像进行比较。

## 技术图纸

图纸是有尺寸的契约。系统地提取它：

- 先读标题栏和注释：单位、投影约定、版本、免责声明。
- 识别哪个视图是哪个——前/上/侧、剖视图、详图、轴测图——以及在提取数字之前每个视图映射到哪些模型轴。信任标注和视图标签，而非布局约定。剖视图是内部特征的真相源：孔径、沉孔（counterbore）和盲孔（blind hole）深度、壁截面。
- 将每个尺寸标注转换为命名参数和验证（validation）目标。倍数（`4X`）、`TYP.` 以及螺纹/沉孔（counterbore）/锪孔（countersink）标注展开为特征加检查。
- 绝不从图像上量取未标注的几何。在受约束时从说明的尺寸推导；否则假设并报告。
- 跨视图交叉检查特征；当视图不一致时，优先采用有尺寸的视图并标记冲突。
- 图纸驱动模型的成功标准：每个图纸尺寸在生成后要么通过 `measure`/`refs` 验证（validation），要么明确报告为未验证（validation）。

## 简介格式

使用简洁的 Markdown 笔记，而非面向用户的结构化模式：

```text
CAD brief:
- Model: <part or assembly name>
- Task type: <new part, assembly, modification, inspection, secondary output>
- Inputs: <reference images or drawing views used; omit when prose-only>
- Units: <explicit or assumed>
- Coordinate convention: <origin, base plane, up axis>
- Overall dimensions: <width/depth/height or equivalent>
- Functional features: <holes, slots, ribs, bosses, pockets, shells, text, etc.>
- Manufacturing assumptions: <only when relevant>
- Positioning/mating: <interfaces, datums, child placements, joints, alignment rules>
- Paths: <generator .py, STEP target, secondary outputs if requested>
- Validation targets: <bbox, solid count, labels, spec-driven measurements, refs>
- Assumptions: <only meaningful inferred choices>
```

## 示例：简单零件（part）

用户说：

```text
Make a 100 mm by 60 mm by 6 mm mounting plate with rounded corners, four M4 clearance holes 10 mm in from the corners, and a 20 by 12 mm rectangular cutout in the center.
```

Agent 简介：

```text
CAD brief:
- Model: mounting_plate, single STEP part.
- Units: millimeters.
- Origin: center of plate; base plane XY; +Z is thickness direction.
- Body: rounded rectangular plate, 100 × 60 × 6 mm.
- Corner radius: not specified; assume 3 mm.
- Holes: four 4.5 mm M4 clearance through-holes, 10 mm in from each corner.
- Cutout: centered rectangular through-cut, 20 × 12 mm.
- Validation: one positive-volume solid, bbox 100 × 60 × 6 mm, four holes, one center cutout, label mounting_plate.
```

## 示例：装配体（assembly）

用户说：

```text
Design a two-piece enclosure, 120 by 80 by 35 mm, with a lid that sits on top and four screw bosses aligned between base and lid.
```

Agent 简介：

```text
CAD brief:
- Model: enclosure assembly with base and lid.
- Units: millimeters.
- Assembly origin: center of enclosure footprint; +Z upward.
- Base: hollow lower shell, exterior 120 × 80 mm footprint; height derived from total height minus lid thickness.
- Lid: separate plate on top; assume 3 mm lid thickness unless user gave another value.
- Bosses: four aligned screw bosses; assume M3 unless unspecified dimensions make this unsafe.
- Positioning: base top face and lid bottom face are mating datums; screw axes must align; native build123d joints may be used if they clarify reusable mount points or motion.
- Validation: labeled base and lid children, bbox near 120 x 80 x 35 mm, aligned hole/boss axes.
```

## 澄清策略

仅当缺失信息影响配合（mating）、安全、合规或使零件（part）无法建模时，才提出一个聚焦问题。否则按假设继续并报告。

提问时机：

- 物理对象未提供尺寸，且提供的图像中不存在比例参考。
- 描述了配合（mating）接口但配合（mating）几何未指定。
- 零件（part）是安全关键、承重、承压、医疗或合规约束的。
- 请求的输出依赖于缺失的源文件或缺失的导入几何。

不提问时机：

- 默认间隙孔（clearance hole）标准足够。
- 可以安全假设装饰性圆角（fillet）半径。
- 原点/方向可以选择并报告。
- 用户请求的是概念性首轮 CAD 模型。

## 成功标准

当简介包含足够信息来定义以下内容时，即可进行建模：

- 源文件路径和 STEP 目标路径
- 单位和局部坐标系
- 命名参数
- 特征计划和标签
- 预期包围盒或关键测量值
