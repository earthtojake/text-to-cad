# implicitjs

`implicitjs` 是一个用于浏览器原生 implicit CAD 模型的独立 JavaScript 运行时。它定义了 `.implicit.js` 模型 schema，构建 GLSL raymarch 着色器，使用 Three.js 渲染模型，在 CPU 上评估 SDF，生成无头 PNG/GIF 快照（snapshot），对网格（mesh）进行采样，检查网格（mesh）质量，并导出 STL、3MF 和 GLB 产物（artifact）。

该包与 UI 框架无关。应用程序提供自己的编辑器、目录、侧边栏、持久化和产品工作流（workflow）；`implicitjs` 提供模型、渲染、快照（snapshot）和导出逻辑。

## 安装

```bash
npm install implicitjs
```

对等使用需要一个现代的 ESM JavaScript 环境。渲染 API 需要兼容 Three.js 的 WebGL 支持。无头快照（snapshot）CLI 使用 Playwright。

## 模型格式

一个 implicit 模型是一个导出 `implicit.js/0.1.0` 对象的 ES 模块。`glsl` 字符串必须提供 `float sdf(vec3 p)`。它还可以提供 `vec3 color(vec3 p, vec3 normal)` 用于程序化颜色。

```js
const GLSL = `
float sdf(vec3 p) {
  return implicit_sphere(p, vec3(0.0), radius);
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.0, 0.65, 1.0), vec3(1.0, 0.3, 0.8), normal.z * 0.5 + 0.5);
}
`;

export default {
  schema: "implicit.js/0.1.0",
  name: "parametric sphere",
  units: "mm",
  params: {
    radius: { type: "number", label: "Radius", min: 5, max: 50, default: 22, unit: "mm" }
  },
  bounds: ({ params }) => {
    const r = params.radius + 2;
    return [[-r, -r, -r], [r, r, r]];
  },
  render: { steps: 192 },
  glsl: GLSL
};
```

number、boolean、color 和 button 参数会自动成为同名的 GLSL uniform。在 GLSL 中直接使用参数名；不需要单独的 `uniforms` 对象。

`bounds` 是可选的，可以从 SDF 估算，但对于异常场、薄特征、周期性模型、动画尺寸变化或导出密集的工作流（workflow），建议使用显式 bounds。

编写的 GLSL 可以使用 `implicit_*` 命名空间中的内置辅助函数，例如 `implicit_sphere`、`implicit_box_centered`、`implicit_cylinder_capped`、`implicit_line_segment2`、`implicit_union_round` 和 `implicit_intersect_round`。

## 公共 API

常用导入：

```js
import {
  loadImplicitModuleFromSource,
  normalizeImplicitModel,
  renderImplicitToDataUrl,
  snapshotImplicitCadModel,
  exportImplicitModel,
  exportImplicitAnimatedGlb
} from "implicitjs";
```

有用的子路径导出：

- `implicitjs/model`：schema 规范化和参数化运行时模型。
- `implicitjs/loader`：加载 `.implicit.js` 模块或源字符串。
- `implicitjs/render`：Three.js 着色器和相机辅助函数。
- `implicitjs/snapshot`：浏览器 PNG 快照（snapshot）辅助函数。
- `implicitjs/mesh`：SDF 网格（mesh）采样。
- `implicitjs/meshQuality`：网格（mesh）质量检查。
- `implicitjs/export`：STL/3MF/GLB 导出 API。
- `implicitjs/sdfEvaluator`：兼容 GLSL 的 CPU SDF 评估器。

## 渲染

```js
import * as THREE from "three";
import { loadImplicitModuleFromSource, renderImplicitToDataUrl } from "implicitjs";

const model = await loadImplicitModuleFromSource(source);
const pngDataUrl = await renderImplicitToDataUrl(THREE, model, {
  width: 1200,
  height: 900,
  camera: "iso",
  render: { frameMargin: 1.45 },
  graphics: { modelColors: true, detail: 1.2 }
});
```

相机预设包括 `iso`、`front`、`back`、`left`、`right`、`top` 和 `bottom`。相机也可以是包含 `position`、`target`、`up`、`direction`、`preset` 和 `zoom` 的 JSON 对象。

## 快照（snapshot）

从包检出目录运行：

```bash
npm run snapshot -- --input examples/model.implicit.js --output /tmp/model.png
npm run snapshot -- --input examples/model.implicit.js --output /tmp/model.gif --mode orbit
```

Orbit GIF job 默认以 6 fps 持续 12 秒，以实现更平稳的审查旋转，而不会增加默认渲染帧数。
需要时在 JSON job 中使用 `orbit.fps` 和 `orbit.durationSeconds` 进行覆盖。

快照（snapshot）CLI 也接受 JSON job。单个 job 可以包含多个输出，`--job` 可以加载一个 job、一个 job 数组，或 `{ "jobs": [...] }`。
渲染审查数据包时，优先使用一个多输出 job，因为可以复用浏览器、模块和运行时模型。

```bash
npm run snapshot -- --job - <<'JSON'
{
  "input": "examples/model.implicit.js",
  "render": { "frameMargin": 1.55 },
  "outputs": [
    { "path": "/tmp/model-iso.png", "camera": "iso" },
    { "path": "/tmp/model-front.png", "camera": "front" },
    { "path": "/tmp/model-top.png", "camera": "top" }
  ]
}
JSON
```

每个输出路径在其扩展名前会收到一个 UTC 时间戳。

## 导出

```js
import { exportImplicitModel, exportImplicitAnimatedGlb } from "implicitjs/browser";

const glb = await exportImplicitModel(model, {
  format: "glb",
  resolution: 96,
  params: { radius: 24 }
});

const animated = await exportImplicitAnimatedGlb(model, {
  animationId: "breathe",
  params: { radius: 24 },
  frames: 24,
  resolution: 72
});
```

从包检出目录运行：

```bash
npm run export -- --input examples/model.implicit.js --format glb --output /tmp/model.glb
npm run export -- --input examples/model.implicit.js --format stl --resolution 96
npm run export -- --input examples/model.implicit.js --format 3mf --params '{"radius":24}'
```

导出会在模型 bounds 内对其 SDF 进行采样。更高的分辨率会产生更密集的网格（mesh）并花费更长时间。

## 包结构

- `src/index.js`：公共包入口。
- `src/browser.js`：面向浏览器的入口。
- `src/common/`：共享的相机、参数、主题、渲染选项和无头快照（snapshot）辅助函数。
- `src/lib/implicitCad/`：schema、模型规范化、加载、着色器渲染、CPU 评估、网格（mesh）采样、网格（mesh）质量和导出器。
- `src/lib/viewer/`：着色器使用的内部渲染呈现默认值。
- `scripts/`：快照（snapshot）、导出、导出验证（validation）和测试 CLI。

测试文件以 `*.test.js` 形式位于其覆盖模块的旁边。

## 开发

```bash
npm test
npm run verify:exports -- --input examples/model.implicit.js
```

保持包的可复用性和 UI 无关性。适用于模型规范化、渲染、快照（snapshot）、CPU 采样、网格（mesh）导出、图形设置、参数和动画的运行时行为应属于此包。产品特定的 UI 状态、目录、编辑器、文件表、路由和持久化应位于消费应用程序中。
