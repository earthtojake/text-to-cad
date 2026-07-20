# 检查与 validation

每当用户要求几何事实、参考、尺寸、mating、diff 或 frame 检查时，以及对于每个生成的 STEP artifact，请阅读此文件。

## 原则

确定性几何检查决定通过/失败；强制的 snapshot 审查（参见 `snapshot-review.md`）捕获确定性检查未编码的语义错误。根据用户规范调整确定性检查：用户指定的每个尺寸、clearance 或关系——包括从技术图纸中获取的尺寸——必须用 `measure`、`align` 或 `frame` 进行验证（validation）。无论规范如何，facts/planes/positioning 基线对每个生成的 artifact 都会运行。

## 工具

启动器位于 CAD 技能目录中：

```bash
python scripts/inspect {refs|diff|frame|measure|align|worker|batch} ...
```

检查目标从命令 cwd 解析；传递 cwd 相对目标路径。常用数据输出标志：`--format json|text`（默认为机器可读）、`--quiet`、`--verbose`。

接受的目标形式：

```text
path/to/entry
path/to/entry.step
```

Selector ref 是传递给命令的 STEP/CAD 条目目标的局部引用。它们不包含文件路径：

```text
#o1.2
#o1.2.f1
#f1
```

将 selector ref 作为 `#...` token 传递。STEP/CAD 文件路径或条目目标是单独的 CLI 参数。

## Validation 序列

1. 生成完成且 STEP/STP 文件存在。
2. `refs --facts --planes --positioning` 确认比例、标签、主要平面和就绪放置的参考。对每个生成的 artifact 运行此项。
3. 规范驱动检查：对每个用户指定的尺寸、offset 或 clearance 使用 `measure`；对应 flush 或居中的接口使用 `align`；对方向和实例放置期望使用 `frame`；对可能影响无关几何体的修改使用 `diff`。
4. 按照 `snapshot-review.md` 对主要 STEP/STP 进行 snapshot，然后在每个视觉问题成为 validation 声明之前将其转换为确定性几何检查。

## 参考发现

紧凑的 facts 和 planes：

```bash
python scripts/inspect refs path/to/model.step \
  --facts --planes --positioning
```

详细的 selector 检查：

```bash
python scripts/inspect refs path/to/model.step '#selector' \
  --detail --positioning
```

仅在需要时的 topology 枚举：

```bash
python scripts/inspect refs path/to/model.step --topology
```

平面选项：

```bash
--plane-coordinate-tolerance FLOAT
--plane-min-area-ratio FLOAT
--plane-limit INT
```

对正常 validation 使用较低的平面限制和紧凑的 facts。仅在 selector 发现、复杂调试或当特征无法通过 facts/planes/measurements 验证（validation）时使用 topology 枚举；在大模型上可能开销较大。

## 测量检查

使用 `measure` 进行边界距离、clearance、offset、part 间距、板厚、孔到面距离和对齐验证（validation）。

```bash
python scripts/inspect measure path/to/model.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis x
```

尽可能推断轴，但对确定性检查指定 `x`、`y` 或 `z`。

## 对齐检查

当两个导出的 STEP 参考应 flush 或居中时使用 `align`。它返回所选 ref 之间的平移 delta；在 build123d 源码中应用任何所需修正（参见 `positioning.md`），重新生成，并重新检查。

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

## Frame 检查

使用 `frame` validation 实例变换和所选参考的世界 frame：

```bash
python scripts/inspect frame path/to/model.step '#selector'
```

Frame 输出对 assembly、part 局部到世界转换和放置调试有用。

## Diff 检查

对于修改任务，比较前后 artifact：

```bash
python scripts/inspect diff path/to/before.step path/to/after.step --planes
```

当修复、特征添加或源码编辑可能影响无关几何体时使用 diff。

## Validation 报告内容

仅报告实际运行或直接由工具输出支持的检查。如果检查了重要的 selector，则在拥有的 CAD Viewer 链接旁边返回局部 selector ref。

使用此结构：

```text
Validation:
- STEP generation: passed/partial/failed
- Solids/assembly: <counts and labels>
- Bounding box: <dimensions and units>
- Major planes/refs: <summary>
- Positioning: <frame/measure/align results if relevant>
- Feature checks: <holes, cutouts, bosses, etc.>
- Visual review: `$cad-viewer` viewer link returned; CAD `scripts/snapshot` PNG/GIF included or skipped with reason; follow-up geometry checks for any visual findings
```

不要声称：

- 结构安全
- 工艺认证
- 公差合规
- 超出几何可行性的可制造性

除非明确执行了相关分析或制造数据。
