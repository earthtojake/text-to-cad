# STEP 生成

当从 build123d Python 源码或从直接 STEP/STP 目标生成或重新生成 STEP/STP 产物（artifact）时阅读本文件。

## 工具

启动器位于 CAD 技能目录：

```bash
python scripts/step [--kind {part|assembly}] targets... [flags]
```

仅使用显式目标路径；目标路径从命令 cwd 解析，除非为绝对路径。不要依赖目录范围的生成。

普通生成的 Python 目标写入同级 `.step` 输出。仅对单个普通生成的 Python 目标使用 `-o`/`--output`，或使用 `SOURCE.py=OUTPUT.step` 位置参数对进行每目标自定义输出。配对输出路径从命令 cwd 解析，仅对生成的 Python 源码有效，而非直接 STEP/STP 输入。不要在 `gen_step()` 返回值中放入输出路径；CLI 拥有输出路径。

## 生成的 Python 源码

这是从零设计或修改已生成模型时的默认路径。生成的 build123d 源码定义：

```python
def gen_step():
    ...
    return step_ready_shape_or_labeled_compound
```

生成的 Python 目标从源码元数据和 `gen_step()` 返回值推断其类型；直接传入源码路径：

```bash
python scripts/step path/to/part.py
python scripts/step path/to/part.py -o path/to/custom.step
python scripts/step path/to/a.py=out/a.step path/to/b.py=out/b.step
python scripts/step path/to/assembly.py
```

直接传入已生成的装配体（assembly） `.step` 会将其视为导入的原生 STEP，并丢失源码级装配体（assembly）组合；请传入 `.py` 装配体源码。对于生成的 build123d 装配体（assembly），在 Python 源码中优先使用 `cadpy.assembly.AssemblyHelper`，以便在 STEP 导出之前保留原生标签、命名的配合（mating）参考系（frame）和源码级关系（见 `positioning.md`）。

## 直接 STEP/STP 导入

当不存在生成器（导入或下载的 STEP）或用户明确将 STEP/STP 文件指定为目标时，使用直接 STEP/STP 目标。然后从 STEP 文件本身生成 GLB/拓扑（topology）产物（artifact）：

```bash
python scripts/step --kind part path/to/imported.step
```

直接目标支持与生成器目标相同的网格（mesh）附带附带产物（sidecar）标志；阅读 `supported-exports.md` 了解 STL 和 3MF 附带附带产物（sidecar）。

## 查看器产物（artifact）

每次 `scripts/step` 运行还会作为正常构建的一部分写入隐藏的相邻 GLB/拓扑（topology）产物（artifact）。它们为 CAD Viewer 审查、`$cad-viewer` 工作流（workflow）和 `scripts/inspect` 引用提供支持，在 STEP 工作流（workflow）中不是可选的。

## 生成之后

- 确认进程成功且 STEP 文件存在且非空。
- 按照 `inspection-and-validation.md` 运行基线检查和任何规格驱动的检查：

```bash
python scripts/inspect refs path/to/model.step --facts --planes --positioning
```
