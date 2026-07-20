# 切片器后端

使用真实的切片器 CLI 进行网格（mesh）到 G-code 的工作。不要依赖 Bambu Studio 作为此技能的默认后端。

## 后端顺序

1. `orcaslicer`
2. `prusa-slicer`
3. `curaengine`

如果没有安装首选后端，请先安装 OrcaSlicer，而不是将缺失的切片器视为面向用户的阻碍。在 macOS 上：

```bash
brew install --cask orcaslicer
```

安装后，重新运行 `scripts/gcode_tool.py discover`。辅助工具会检查 `PATH`、后端特定的环境变量，以及常见的 macOS 应用 bundle 位置，例如 `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`。

`scripts/gcode_tool.py discover` 检查 PATH 和后端特定的环境变量：

- `ORCASLICER_BIN`
- `PRUSASLICER_BIN`
- `CURAENGINE_BIN`

Bambu Studio 也可能被报告为可用，但不作为首选。它被有意排除在默认后端选择之外，因为本地 Bambu CLI 导出路径之前在生成 `.gcode.3mf` 期间发生过崩溃。

## Profile 预期

每次切片都需要一个封装 profile JSON。封装必须包含：

- `backend`：`orcaslicer`、`prusa-slicer` 或 `curaengine` 之一。
- `native_config`：主原生切片器配置/profile 文件的绝对路径。
- `machine.bed_size_mm`：以毫米为单位的 `[宽度, 深度]`。
- `machine.z_height_mm`：以毫米为单位的最大 Z 行程。
- `machine.motion_bounds_mm`：可选的每轴运动限制，用于有意移动到可打印区域之外的原生起始/结束 G-code。
- `filament.type`、`filament.nozzle_temp_c` 和 `filament.bed_temp_c`。

封装不是完整的切片器 profile。原生配置对于详细的打印机、工艺和耗材设置具有权威性。

对于拆分到原生机器、工艺和耗材 JSON 文件的 OrcaSlicer profile，添加：

- `native_settings`：传递给 `--load-settings` 的字符串或绝对路径列表。
- `native_filaments`：传递给 `--load-filaments` 的字符串或绝对路径列表。

如果省略 `native_settings`，则 `native_config` 将作为唯一的设置文件传递。

## 命令格式

对于 OrcaSlicer：

```bash
OrcaSlicer --load-settings machine.json\;process.json --load-filaments filament.json --outputdir /tmp/out --slice 0 input.stl
```

对于 PrusaSlicer：

```bash
prusa-slicer --load profile.ini --export-gcode --output output.gcode input.stl
```

对于 CuraEngine：

```bash
CuraEngine slice -j profile.json -l input.stl -o output.gcode
```

始终先运行试运行（dry-run），并在 `--execute` 之前检查发出的命令。

## 输入处理

- `.stl`、`.obj` 和未切片的 `.3mf` 直接传递给所选切片器。
- `.ply`、`.glb` 和 `.gltf` 在 `--execute` 期间使用 `trimesh` 转换为临时 STL。
- 包含 `Metadata/plate_N.gcode` 的已切片 Bambu 3MF 文件已经是打印作业；不要重新切片它们。
- `.step`、`.stp`、`.dxf`、`.svg`、`.urdf` 和 `.sdf` 不在此技能范围内。请先将它们转换为受支持的网格（mesh）。

## 源链接

- FullControl 程序化 G-code 背景：https://github.com/FullControlXYZ/fullcontrol
- bambox Bambu 打包参考：https://pypi.org/project/bambox/
- trimesh 网格（mesh）格式支持：https://trimesh.org/formats.html
- CuraEngine 切片背景：https://github.com/Ultimaker/CuraEngine/wiki/Slicing
