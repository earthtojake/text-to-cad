---
name: dxf
description: 从 Python ezdxf 源码生成、重新生成并验证（validation） 2D DXF 图纸。用于 DXF 文件、`gen_dxf()` 源码、2D 轮廓、外形、模板、垫片、面板、展开图、激光/等离子/水刀切割排版，以及 CAD 几何的 2D 图纸导出。
---

# DXF 生成与验证（validation）

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
使用已安装的本地技能文件作为运行时的事实来源；仓库链接仅用于溯源和发布审查。

## 目的

从自然语言需求或 CAD 几何创建或修改 2D DXF 图纸，生成经过验证（validation）的 `.dxf` 产物（artifact），并返回已检查的输出。DXF 源码是定义 `gen_dxf()` 并返回 `ezdxf` 文档的 Python 文件；输出路径由 CLI 拥有。

支持两种源码形式：

- **独立制图**：仅定义 `gen_dxf()` 的 Python 源码。用于纯 2D 输出——垫片、面板、模板、切割排版——背后没有 3D 模型。
- **CAD 投影**：添加到同时定义 `gen_step()` 的 CAD 生成器源码中的 `gen_dxf()`。当 DXF 是 3D 零件（part）的图纸或轮廓时使用；先用 `$cad` 创建并验证（validation） STEP 几何，然后在同一源码文件中添加投影。

## 何时使用此技能

当用户请求 DXF 文件、2D 图纸、轮廓、外形、模板、垫片、面板、展开图，或激光、等离子、水刀、CNC 路由的切割排版时，使用此技能。

对于 DXF 所派生自的 3D 零件（part）或装配体（assembly），使用 `$cad`。对于 SendCutSend 专属的上传预检，使用 `$sendcutsend`。

## 默认值

除非用户另有指定，否则使用以下默认值：

- 单位：毫米；在文档上显式设置（`doc.units = ezdxf.units.MM`）。
- 几何位于模型空间中，比例为 1:1。
- 切割轮廓是闭合多段线或闭合的直线/圆弧环；开放轮廓仅用于雕刻或参考几何。
- 对于有 CAD 支撑的零件（part），优先从同一生成器脚本中的实际 STEP/实体拓扑（topology）派生 DXF 切割轮廓：构建 3D 形状，选择/投影真实的平面，将其展开为平面坐标，并从这些投影面线框发出闭合轮廓。仅当没有可靠的 3D 拓扑（topology）可投影时，才使用手绘参数化外形。
- 图层承载意图：将切割几何和弯折/折叠线放在不同图层上，并在弯折图层名称中包含“bend”，以便下游工具将其归类为弯折而非切割。
- DXF 图层是图纸结构，而非 STEP 零件（part）/装配体（assembly）结构。

## 工具

启动器位于 DXF 技能目录中：

```bash
python scripts/dxf targets... [flags]
```

使用活动项目的 Python 解释器；将 `python` 视为解释器占位符，并使用 `--help` 查看完整接口。目标路径从命令的当前工作目录解析；从拥有产物（artifact）的工作区运行，使用相对于 cwd 的目标路径。除非用户另有要求，否则将 DXF 输出及其 Python 生成器保持在同一目录中且具有相同的基本名。

DXF 目标是定义以下内容的 Python 源码：

```python
def gen_dxf():
    ...
    return document
```

普通生成的 Python 目标会写入同级的 `.dxf` 输出。仅对单个普通生成的 Python 目标使用 `-o`/`--output`，或使用 `SOURCE.py=OUTPUT.dxf` 位置参数对来为每个目标指定自定义输出。不要将输出路径放入 `gen_dxf()` 的返回值中。

`scripts/dxf` 是一个生成器；它不会检查现有的 `.dxf` 文件。对于现有 DXF 的检查，使用 `ezdxf` 进行实体/图层检查，使用 `$cad-viewer` 进行可视化审查。

## 工作流（workflow）

1. 将请求转化为简短的任务摘要：列出尺寸、孔和槽、图层、单位、输出路径和验证（validation）目标。
2. 对于 CAD 投影，先用 `$cad` 生成并验证（validation） STEP 几何，然后在同一源码中添加或更新 `gen_dxf()`。尽可能从内存中的 STEP/实体拓扑（topology）派生 DXF，而非重复几何公式，使 DXF 始终是被导出零件（part）的直接投影/展开。
3. 编写或编辑 Python 源码，将有意义的尺寸作为命名参数。
4. 仅对显式的 Python 源码目标运行 `scripts/dxf`；不要进行全目录范围的生成。

```bash
python scripts/dxf path/to/source.py
python scripts/dxf path/to/source.py -o path/to/output.dxf
python scripts/dxf path/to/a.py=out/a.dxf path/to/b.py=out/b.dxf
```

5. 确定性地验证（validation）生成的 DXF，然后交接（handoff）并报告。

## 验证（validation）

使用有针对性的 `ezdxf` 检查来验证（validation）生成的文件，而非肉眼查看：按类型和图层统计实体数量、切割轮廓的闭合标志、图纸范围，以及用户指定的每一项尺寸。

```python
import ezdxf

doc = ezdxf.readfile("path/to/output.dxf")
msp = doc.modelspace()
profiles = [e for e in msp.query("LWPOLYLINE") if e.closed]
holes = msp.query('CIRCLE[layer=="0"]')
```

仅报告实际运行的检查。

## 交接（handoff）

创建或修改 `.dxf` 产物（artifact）后，当 `$cad-viewer` 技能已安装时，你必须始终将显式文件路径交给 `$cad-viewer`，并在最终响应中包含其实时查看器链接。如果 `$cad-viewer` 不可用或启动失败，请报告此情况并依赖 `ezdxf` 检查，而非默默地省略交接（handoff）。

最终响应应包括生成的文件、返回的查看器链接、实际运行的验证（validation）以及所做的假设。
