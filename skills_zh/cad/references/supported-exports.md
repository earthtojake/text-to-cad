# 支持的导出

当用户请求从 CAD 几何生成 STL、3MF 或原生 GLB 输出时阅读本文件。对于 2D DXF 输出，使用 `$dxf` 技能；DXF 使用单独的 `gen_dxf()` 源码约定。

## 策略

STL、3MF 和原生 GLB 是网格（mesh）附带附带产物（sidecar），而非 STEP 的替代品。先生成并验证（validation）STEP，然后从同一次 `scripts/step` 运行导出请求的附带附带产物（sidecar）。不要将附带附带产物（sidecar）渲染视为 CAD 验证（validation）；按标准工作流（workflow）检查并快照（snapshot）主要 STEP。

原生 GLB 附带附带产物（sidecar）是用于外部工具的普通 glTF 2.0 二进制文件：Y 轴向上、米为单位、不含 CAD Viewer 的 `STEP_topology` 扩展。不要将它们与隐藏的 `.<name>.step.glb` CAD Viewer 拓扑（topology）产物（artifact）混淆。

## 工具

使用 `scripts/step` 配合（mating）生成的 Python 源码：

```bash
python scripts/step path/to/model.py \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

当存在生成器时，使用生成器形式。仅当生成器不可用或用户明确将该文件指定为目标时才使用直接 STEP/STP 目标：

```bash
python scripts/step --kind part path/to/model.step \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

附带附带产物（sidecar）路径必须是相对的 `.stl`、`.3mf` 或 `.glb` 路径，并在 STEP 输出旁边解析。

## 网格（mesh）公差

默认网格（mesh）密度为 `0.02` 线性偏转和 `0.05` 角度偏转。

当默认网格（mesh）密度不适合零件（part）时使用这些标志：

```bash
--mesh-tolerance FLOAT
--mesh-angular-tolerance FLOAT
```

对小型曲面零件（part）或视觉保真度使用更紧的公差。当文件大小重要时，对大型简单几何使用更松的公差。

## 工作流（workflow）

1. 用请求的附带附带产物（sidecar）标志从 `gen_step()` 生成 STEP。
2. 对 STEP 运行 facts/planes/positioning 检查。
3. 报告 STEP 和请求的附带附带产物（sidecar）文件。

示例：

```bash
python scripts/step models/bracket.py \
  --stl meshes/bracket.stl \
  --glb meshes/bracket.glb \
  --mesh-tolerance 0.2 \
  --mesh-angular-tolerance 0.2

python scripts/inspect refs models/bracket.step --facts --planes --positioning
```

## 报告

```text
Files:
- STEP: /absolute/project/models/bracket.step
- STL: /absolute/project/models/meshes/bracket.stl
- GLB: /absolute/project/models/meshes/bracket.glb

Validation:
- STEP geometry validated; STL/3MF/native GLB generated as requested sidecars.
- Primary STEP/STP snapshot packet run/skipped and why.
```
