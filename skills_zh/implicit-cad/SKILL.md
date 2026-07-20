---
name: implicit-cad
description: 创建、编辑、渲染并对浏览器原生 implicit CAD `.implicit.js` 和 `.implicit.mjs` 文件进行快照（snapshot），使用 GLSL 有符号距离场、着色器图元、平滑布尔运算、TPMS 场以及直接由 CAD Viewer 进行 raymarch 渲染。实验性。
---

# Implicit CAD

当需要让 implicit CAD 模型直接作为浏览器 JS 模块在 CAD Viewer 中运行时，请使用此技能。其主要产物（artifact）是 `.implicit.js` 或 `.implicit.mjs` 文件。

此技能为实验性。除非用户明确要求 implicit 模型，否则**始终**优先使用传统的 STEP 优先 CAD 工作流（workflow）。

## 文件格式

一个 implicit CAD 文件是一个 ES 模块，导出一个 `implicit.js/0.1.0` 对象。其 schema 的真相来源位于打包包中的 `scripts/packages/implicitjs/src/lib/implicitCad/schema.js`；`scripts/lib/implicit-cad.mjs` 将其重新导出为 `SCHEMA`，供辅助模块编写时使用。

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "rounded capsule block",
  glsl: `
float sdf(vec3 p) {
  float sphere = implicit_sphere(p, vec3(0.0), 22.0);
  float block = implicit_box_centered(p, vec3(34.0, 18.0, 18.0), vec3(0.0));
  return implicit_union_round(sphere, block, 3.0);
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.20, 0.55, 0.95), vec3(0.95, 0.45, 0.20), smoothstep(-15.0, 20.0, p.z));
}
`,
};
```

模型也可以声明 params 和 animations。参数定义使用 implicitjs 控件 schema：`number`、`boolean`、`enum`/`select`、`color`、`string` 和 `button`。number、boolean、color 和 button 参数会自动成为同名的 GLSL uniform；不要另外添加单独的 `uniforms` 对象。`bounds` 是可选的，省略时会从 SDF 估算；仅当自动估算过宽、过慢或遗漏了异常场时，才添加显式 bounds。`bounds` 和 `render` 可以是 JavaScript 函数，接收 `{ ...params, params, animation, animationState, elapsedSec, progress, t }`。

内置 GLSL 辅助函数使用 `implicit_*` 命名空间，例如 `implicit_sphere`、`implicit_box_centered` 和 `implicit_union_round`。

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "breathing orb",
  params: {
    radius: {
      type: "number",
      label: "Radius",
      min: 12,
      max: 34,
      default: 22,
      unit: "mm",
    },
  },
  animations: {
    breathe: {
      label: "Breathe",
      duration: 3,
      update({ progress, set }) {
        set("radius", 18 + Math.sin(progress * Math.PI) * 10);
      },
    },
  },
  render: { steps: 224, epsilon: 0.004 },
  glsl: `
float sdf(vec3 p) {
  return length(p) - radius;
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.10, 0.58, 0.95), vec3(1.0, 0.34, 0.12), smoothstep(-18.0, 18.0, p.z));
}
`,
};
```

不要将此技能中的打包辅助文件复制出去。如果辅助函数有用，请在编写时使用 `scripts/lib/implicit-cad.mjs`，或者将独立的 GLSL 直接写入最终的 `.implicit.js`/`.implicit.mjs` 模块。

## 编写工作流（workflow）

1. 编写一份自然语言的建模说明，包含尺寸、坐标假设、程序化颜色意图以及视觉检查项。
2. 创建或编辑用户指定的 `.implicit.js`/`.implicit.mjs` 模块。
3. 在有用时使用 `scripts/lib/implicit-cad.mjs` 辅助函数进行图元和场组合：
   - 图元：`sphere`、`circle`、`boxCentered`、`plane`、`lineSegment`、`torus`、`axis`、`cylinder`、`cylinderCapped`、`capsule`、`cone`、`coneCapped`、`coneCapsule`
   - 布尔/混合：`unionSharp`、`intersectSharp`、`unionRound`、`intersectRound`、`unionChamfer`、`intersectChamfer`、`unionExp`、`intersectExp`、`unionLpNorm`、`intersectLpNorm`、`unionRvachev`、`intersectRvachev`、`difference`
   - 修饰符/点阵：`shell`、`rotateAxis`、`repeatCentered`、`remapCylindrical`、`cubicGrid`、`squareHoneycomb`、`squareHoneycombReinforced`、`squareDiagonalHoneycomb`、`octetHoneycomb`、`hexagonalHoneycomb`、`triangularHoneycomb`
   - TPMS 场：`tpmsGyroid`、`tpmsSchwarz`、`tpmsDiamond`、`tpmsLidinoid`、`tpmsNeovius`、`tpmsSplitP`、`tpmsIwp`
   - 着色器包装：`distanceFunction` 生成 `float sdf(vec3 p)`，`colorFunction` 生成 `vec3 color(vec3 p, vec3 normal)`
4. 为尺寸、开关、调色板、模式切换和动画探索添加可选的 `params` 和 `animations`。在 GLSL 中直接使用参数名；运行时会声明匹配的 uniform。
5. 当模型受益于局部材质变化时，添加可选的程序化颜色 `vec3 color(vec3 p, vec3 normal)`。颜色值保持在 0..1 RGB 范围内。
6. 首先依赖自动 SDF bounds。当动画、周期性、平移或非常薄的模型需要更紧凑或更可靠的取景/导出采样时，再添加显式 bounds。
7. 在可见几何、颜色、参数、动画、bounds、render 或影响导出的更改之后，运行下面的轻量级视觉验证（validation）流程。
8. 当需要为下游查看器、切片器或文件交接（handoff）提供网格（mesh）产物（artifact）时，运行 `node scripts/export.mjs --input <model.implicit.js> --format glb`。

## 视觉验证（validation）

将此技能的快照（snapshot）工具用作快速视觉检查，而非确定性导入/导出验证（validation）的替代品。保持数据包小而聚焦。

对于简单的静态编辑，一张图片即可：

```bash
node scripts/snapshot.mjs --input models/implicit-cad/<model>.implicit.js --output /tmp/implicit-review/<model>.png
```

对于拓扑（topology）、周期性、薄特征、布尔混合、对象同一性、颜色或疑似取景问题，在一次 CLI 调用中渲染一个小数据包，以便复用浏览器、模块和运行时模型：

```bash
node scripts/snapshot.mjs --job - <<'JSON'
{
  "input": "models/implicit-cad/<model>.implicit.js",
  "mode": "view",
  "render": { "sizeProfile": "simple", "frameMargin": 1.55 },
  "graphics": { "modelColors": true, "detail": 1.2, "shadows": true, "ambientOcclusion": true },
  "outputs": [
    { "path": "/tmp/implicit-review/<model>-iso.png", "camera": "iso" },
    { "path": "/tmp/implicit-review/<model>-front.png", "camera": "front" },
    { "path": "/tmp/implicit-review/<model>-top.png", "camera": "top" },
    { "path": "/tmp/implicit-review/<model>-right.png", "camera": "right" }
  ]
}
JSON
```

在 job 级别添加 `implicitParameters` 用于单一参数状态，或当审查目的是比较参数变体时添加到各个输出上。当模型接近边缘时，将 `render.frameMargin` 设为 `1.5` 左右；如果快照（snapshot）仍然显得被裁剪，首先检查源 `bounds` 是否正在裁剪 raymarch 本身。

对于动画，仅当运动是请求的一部分时才创建短 GIF：

```bash
node scripts/snapshot.mjs --job - <<'JSON'
{
  "input": "models/implicit-cad/<model>.implicit.js",
  "mode": "animate",
  "outputs": [{ "path": "/tmp/implicit-review/<model>-animation.gif" }],
  "implicitAnimation": { "activeId": "<animation-id>", "durationSeconds": 3, "fps": 12 }
}
JSON
```

审查生成的 PNG/GIF，检查居中取景、无上下/侧边裁剪、预期的轮廓和拓扑（topology）、可见的参数差异、GLSL 定义的颜色、无意外孔洞/间隙，以及对于所请求图形设置足够平滑的边缘。如果快照（snapshot）揭示了不匹配，修复 implicit 源或 bounds，并仅重新运行相关的数据包。

## 交接（handoff）

在完成创建或修改 `.implicit.js`、`.implicit.mjs`、`.glb`、`.stl` 或 `.3mf` 产物（artifact）的 implicit CAD 工作后，当 `$cad-viewer` 技能已安装时，你**必须始终**将显式文件路径交接（handoff）给 `$cad-viewer`。`$cad-viewer` 必须在尚未运行时启动 CAD Viewer，并返回相关创建或更新文件的链接；将这些实时查看器链接包含在最终响应中。如果 `$cad-viewer` 不可用或启动失败，请报告该情况，而不是静默省略交接（handoff）。

当生成了验证（validation）快照（snapshot）时，还应在最终响应中包含已保存的 PNG/GIF 快照（snapshot）。如果没有适用的快照（snapshot），或快照（snapshot）生成失败，请说明原因并报告仍然运行的确定性验证（validation）。

## 快照（snapshot）工具

从此技能目录运行：

```bash
node scripts/snapshot.mjs --input <model.implicit.js> --output <snapshot.png>
node scripts/snapshot.mjs --input <model.implicit.js> --output <orbit.gif> --mode orbit
node scripts/snapshot.mjs --job <render-job.json>
node scripts/snapshot.mjs --job - --json
node scripts/snapshot.mjs --help
```

使用 `node scripts/snapshot.mjs --help` 获取完整的当前命令接口。该工具会在输出扩展名前追加一个 UTC 时间戳。JSON job 可以是单个 job、一个包含多个 `outputs` 的 job、一个原始 job 数组，或 `{ "jobs": [...] }`；对于审查数据包，优先使用多输出 job，因为它避免了为每个相机重建相同的产物（artifact）。

## 导出工具

从此技能目录运行：

```bash
node scripts/export.mjs --input <model.implicit.js> --format glb
node scripts/export.mjs --input <model.implicit.js> --output <mesh.stl> --resolution <resolution>
node scripts/export.mjs --input <model.implicit.js> --format 3mf --params '<parameter-json>' --json
node scripts/export.mjs --help
```

支持的导出格式为 `glb`、`stl` 和 `3mf`。导出器在声明的 bounds 内对 implicit SDF 进行采样并提取三角网格（mesh）。如果省略 `--output`，网格（mesh）会使用相同的词干写入源文件旁边，例如 `<model>.implicit.js` 对应 `<model>.glb`。使用 `node scripts/export.mjs --help` 获取完整的当前命令接口。
