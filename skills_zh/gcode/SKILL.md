---
name: gcode
description: 通过编排真实的切片器 CLI，从 3D 网格（mesh）文件生成、检查、试运行（dry-run）并静态验证（validation）纯 FDM `.gcode`。当 Codex 需要将 `.stl`、`.obj`、未切片的 `.3mf`、`.ply`、`.glb` 或 `.gltf` 切片为带打印机配置的 G-code、发现本地切片器后端、检查网格（mesh）是否已准备好切片、或在任何打印机特定的交接（handoff）之前验证（validation）生成的 G-code 时使用。
---

# G-code

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
将已安装的本地技能文件作为运行时的事实来源；仓库链接仅用于溯源和发布审查。

使用此技能从网格（mesh）文件生成纯 `.gcode`。它不依赖特定打印机，且从不上传、启动或打包打印作业。

## 工作流（workflow）

1. 确认输入是受支持的网格（mesh）：`.stl`、`.obj`、未切片的 `.3mf`、`.ply`、`.glb` 或 `.gltf`。
2. 要求显式的打印机/profile 封装 JSON。不要捏造真实打印机的 profile。
3. 当后端未知时，发现切片器后端：

```bash
python scripts/gcode_tool.py discover
```

4. 检查输入：

```bash
python scripts/gcode_tool.py inspect --input path/to/model.stl --json
```

5. 在执行前试运行（dry-run）切片器命令：

```bash
python scripts/gcode_tool.py slice \
  --input path/to/model.stl \
  --output /tmp/model.gcode \
  --profile path/to/profile.json \
  --backend auto \
  --dry-run
```

6. 仅在试运行（dry-run）命令和 profile 适当后才执行：

```bash
python scripts/gcode_tool.py slice \
  --input path/to/model.stl \
  --output /tmp/model.gcode \
  --profile path/to/profile.json \
  --backend auto \
  --execute
```

7. 验证（validation）生成的 G-code：

```bash
python scripts/gcode_tool.py validate \
  --gcode /tmp/model.gcode \
  --profile path/to/profile.json \
  --json
```

## CAD Viewer 交接（handoff）

在完成创建或修改纯 `.gcode` 的 G-code 工作后，当该技能已安装时，你必须始终将显式文件路径交接（handoff）给 `$cad-viewer`。`$cad-viewer` 必须在 CAD Viewer 尚未运行时启动它，并返回相关已创建或已更新文件的链接；预览仅用于诊断，不能替代此技能的静态验证（validation）。如果 `$cad-viewer` 不可用或启动失败，应报告该情况，而不是静默省略交接（handoff）。

## Profile 契约

每次切片都需要一个封装 profile JSON，包含绝对的原生切片器 profile 路径：

```json
{
  "backend": "orcaslicer",
  "native_config": "/absolute/path/to/native-slicer-profile",
  "machine": {
    "name": "Example Printer",
    "bed_size_mm": [180, 180],
    "z_height_mm": 180,
    "motion_bounds_mm": {
      "x": [0, 180],
      "y": [0, 180],
      "z": [0, 180]
    }
  },
  "filament": {
    "type": "PLA",
    "nozzle_temp_c": 220,
    "bed_temp_c": 65
  }
}
```

封装提供验证（validation）边界和后端选择。`machine.motion_bounds_mm` 是可选的；省略它以使用默认的 `0..bed_size` 和 `0..z_height` 边界，或者在起始/结束 G-code 有意使用可打印区域之外的安全擦拭/排料位置时，从原生打印机 profile 设置它。原生切片器 profile 仍然是详细工艺、打印机和耗材行为的来源。

对于 OrcaSlicer，当真实 profile 被拆分到机器、工艺和耗材 JSON 文件时，使用 `native_settings` 和 `native_filaments`。为保持兼容性，将 `native_config` 保留为指向主原生 profile 的绝对路径：

```json
{
  "backend": "orcaslicer",
  "native_config": "/absolute/path/to/machine-or-process.json",
  "native_settings": [
    "/absolute/path/to/machine.json",
    "/absolute/path/to/process.json"
  ],
  "native_filaments": [
    "/absolute/path/to/filament.json"
  ],
  "machine": {
    "name": "Example Printer",
    "bed_size_mm": [180, 180],
    "z_height_mm": 180
  },
  "filament": {
    "type": "PLA",
    "nozzle_temp_c": 220,
    "bed_temp_c": 65
  }
}
```

## 后端与输入

首选的切片器后端顺序是 `orcaslicer`、`prusa-slicer`，然后是 `curaengine`。当没有首选后端可用时，优先安装 OrcaSlicer；在 macOS 上使用 `brew install --cask orcaslicer`，然后重新运行 `discover`。辅助工具会同时检查 `PATH` 和常见的 `/Applications/OrcaSlicer.app` cask 位置。Bambu Studio 可能会被发现报告为可用，但不作为首选，因为其 CLI 导出路径在 macOS 上表现不稳定。

将 `.stl`、`.obj` 和未切片的 `.3mf` 直接传递给切片器。在执行时使用可选的 `trimesh` 将 `.ply`、`.glb` 和 `.gltf` 转换为临时 STL；如果 `trimesh` 不可用，请要求用户安装它或提供 `.stl`、`.obj` 或未切片的 `.3mf`。

在 v1 中拒绝 `.step`、`.stp`、`.dxf`、`.svg`、`.urdf` 和 `.sdf`。在使用此技能之前，使用现有的 CAD/渲染工作流（workflow）将其转换为受支持的网格（mesh）格式。

当后端行为、profile 预期或源链接相关时，阅读 `references/slicer-backends.md`。

## 验证（validation）

在将生成的 G-code 交接（handoff）给打印机特定的工作流（workflow）之前，始终进行验证（validation）。验证（validation）器会检查非空内容、温度命令、运动命令、挤出移动、XYZ 边界和未知命令警告。

在解读验证（validation）输出或判断某个警告是否可接受时，阅读 `references/gcode-validation.md`。

## Bambu 边界

此技能仅生成纯 `.gcode`。它不创建 Bambu `.gcode.3mf` 归档，也不联系打印机。对于 Bambu 上传/启动工作流（workflow），将已验证（validation）的纯 `.gcode` 交接（handoff）给 `$bambu-labs`。让 `$bambu-labs` 选择打印机特定的 LAN 交接（handoff），例如 A1 Mini 模板项目或显式启用的 bambox 项目包。
