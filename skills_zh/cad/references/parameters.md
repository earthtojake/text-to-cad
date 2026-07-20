# CAD 参数

当用户要求参数化或动画化 STEP 模型，或设计/审查 CAD 源码参数、`.step.js` sidecar 参数、CAD Viewer 控件或动画控件时，请阅读此文件。

## 原则

参数是模型契约的一部分。好的参数使设计 intent 明确，映射到命名的几何体或运动，保持在有效范围内，并为用户和 LLM 提供足够的上下文来预测更改它会带来什么影响。

优先选择保留机制或 part 约束的参数逻辑，而非仅从一个相机角度看起来合理的逻辑。

## 参数简报

在编码之前，编写一个简洁的内部参数简报：

- 每个参数控制什么几何体或运动。
- 单位、默认值、最小/最大值、步长，以及值是否无量纲。
- 每个参数影响哪些命名特征、datum、枢轴、轴、面或局部 selector ref。
- 哪些值是独立输入，哪些是从约束派生的。
- 什么 validation 证明参数正确。

对于 assembly 和机构，在创建控件之前识别固定枢轴、移动枢轴、连杆（link）长度、齿轮比、轴、joint 限制和分支选择。

## 命名

使用描述 intent 的 snake_case 语义名称，与 build123d Python 源码约定匹配：

- 优先使用 `wall_thickness`、`bearing_clearance`、`hinge_angle_deg`、`lid_open`、`gear_ratio`、`link_travel`。
- 避免使用 `offset2`、`magic_scale`、`fix_angle`、`slider_a` 等名称，除非源码模型本身使用有意义的匹配术语。
- 仅在值可能有歧义时在名称中编码单位，如 `_deg`、`_sec` 或 `_mm` 后缀。
- 保持 sidecar 参数 id 与其镜像的 Python 源码参数对齐，并保持源码常量、manifest 特征 id、UI 标签和注释足够对齐，以便 LLM 能将控件追溯到几何体。
- 模块 schema 字段名（如 `schemaVersion`、`manifest.step.path` 和 `durationSeconds`）由 step-module schema 固定；snake_case 约定适用于您定义的参数和特征 id。

对于 STEP sidecar，强烈优先在 module manifest 中使用显式目标链接：

```js
export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/path/to/model.step"
    }
  }
};
```

`manifest.step.path` 必须是工作区相对路径，绝不能是绝对路径、URL 或带 `..` 段的路径。此链接是供人类和工具使用的来源凭据，而非新鲜度契约；不要向 STEP 参数模块添加哈希或陈旧检查。当 sidecar 位于其 STEP 文件旁边时，保持命名为 `.<step-stem>.step.js`，以便现有查看器在 `manifest.step.path` 缺失时可以回退到同文件名约定。

## 默认值和边界

默认值应产生一个有用、有效的模型或 pose。边界应保护模型免受不可能、自相交或误导状态的影响。

- 尽可能使用物理有效范围：joint 限制、正尺寸、可制造的壁厚、合理的 clearance。
- 即使 UI 已声明 `min` 和 `max`，也要在代码中进行 clamp。
- 使 `step` 匹配底层模型的有用精度，而不仅仅是 UI。
- 对真正的二元状态使用布尔值，对离散模式使用 select，对仅样式值使用颜色，仅对有序量使用数字。
- 在有用时保持调试参数可用，但如果它们不代表真实的设计自由度，则将其标记为检查控件。

## 派生，不要漂移

从真实约束计算依赖值：

- 使用枢轴、轴、中心、边界和测量的连杆（link）长度，而不是目测的平移。
- 围绕正确的局部 datum 或 joint 组合 assembly 变换，而不是围绕视觉中心（除非那是实际的设计 datum）。
- 对于连杆（link）机构，从固定枢轴和连杆（link）长度求解运动学。不要通过不可能的中间点进行插值。
- 对于齿轮，保留 pitch-circle 关系、齿数和角度比，而不是凭视觉调整旋转。
- 对于重复特征，从数量、pitch、半径和阵列轴派生位置。

如果参数更改了源码级 CAD 生成器，请重新生成 STEP 并 validation 导出的几何体。如果 STEP sidecar 仅更改查看器时的呈现，请在标签/描述中说明（当歧义重要时）。

## 特征和 Ref

命名特征是参数和几何体之间的桥梁。

- 显式标记源码 part 和 assembly 子件。
- 用稳定的局部 ref（如 `#o1.2`）暴露 sidecar `manifest.features`；在 `manifest.step.path` 中保留文件标识。
- 优先使用特征 id 如 `lid`、`hinge_pin`、`input_gear`、`lower_rocker`，而非将实例 id 作为公共名称。
- 在代码中，按特征角色分组常量和变换，使逻辑读起来像机构。
- 当参数针对特定面、边、part、枢轴或 assembly 子件时，解析并检查 ref。

## 动画

动画参数应驱动最小的真实自由度，并派生其他所有内容。

- 尽可能为机构使用一个归一化的 travel 参数，然后从中派生所有依赖变换。
- 使循环精确：最终 pose 必须等于初始 pose，或者动画应通过周期函数 ping-pong。
- 不要在不兼容的运动学分支之间混合。仅在物理有效的切线、过中心或奇异 pose 处切换分支。
- 在整个动画中保持铰链中心、mating 面、齿轮接触、皮带路径和滑块轴重合。
- 将样式控件与机构控件分开：颜色、可见性、高亮、clip/explode、速度、播放/暂停和 scrub 不应改变机械真相。
- 默认保留源码 STEP/GLB 材质颜色。仅当用户明确要求重新着色、呈现样式或诊断颜色编码时，才覆盖颜色、添加颜色控件或分配查看器时颜色样式。
- 对非显然的运动学选择使用注释，尤其是分支选择、符号约定、datum 原点和派生比。

对于 STEP sidecar，使用 JavaScript 进行实时 CAD Viewer 交互和 Three.js 钩子。使用 Python/build123d 作为重新生成几何体的真相源。Python 可以生成 `.step.js` 模块，但 CAD Viewer 控件不应暗示重新生成（除非该工作流（workflow）存在）。

## 控件

暴露使模型可理解的控件，而非每个常量。

- 数字尺寸：当范围有界且交互时，使用滑块加数字输入；当范围宽广或精度密集时，使用数字输入。
- 角度和归一化 travel：带有明确最小/最大值和单位的滑块。
- 可见性、启用和可选细节：开关。
- 离散模式：select 或分段控件。
- 颜色：仅当明确请求查看器样式时使用颜色控件；否则保留导入的材质颜色。
- 动画：播放/暂停、scrub、循环、重置和速度控件。

使用简洁的标签和描述。好的描述说明什么会改变以及什么保持约束。

## Validation

在代表性值处 validation 参数行为：

- 默认值。
- 最小和最大值。
- 中间 travel。
- 边界或分支切换 pose。
- 涉及用户报告失败的值。

首先使用确定性检查：

- `scripts/inspect refs --facts --planes --positioning` 用于比例、标签、frame 和主要 datum。
- `scripts/inspect frame`、`measure` 或 `align` 用于枢轴、轴、mating 面和距离。
- 在可行时对派生尺寸或 joint 限制使用源码级断言。

使用 CAD `scripts/snapshot` 审查进行视觉语义，遵循 `snapshot-review.md` 进行数据包大小和 PNG 与 GIF 模式选择：

- 审查多个参数 pose，对运动/动画审查使用 GIF。
- 当涉及查看器时呈现时，比较 sidecar 启用与禁用。
- 检查断开的铰链、漂移的枢轴、碰撞（collision）、不可能的分支混合和循环跳跃。
- 在将视觉问题称为已修复之前，将其转换为测量或显式几何事实。

## 常见失败模式

- 违反真实连杆（link）长度或 mating 约束的目测关键帧。
- 控制视觉变换但命名为几何参数的 UI 参数。
- 通过无效中间几何体在两个有效 pose 之间插值。
- 围绕 part 的边界框中心而非其铰链、mate 或局部 frame 变换 part。
- 让调试比例或 offset 在真实设计包络外创建碰撞（collision）。
- 在 sidecar `manifest.step.path` 中使用绝对路径、URL、父目录转义或陈旧重命名的 STEP 路径。
- 用颜色、透明度、相机角度或分解间距隐藏几何问题。
