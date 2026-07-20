# URDF 生成

从具有顶层 `gen_urdf()` 函数的 Python 源码重新生成显式 URDF 输出。

```bash
python scripts/urdf path/to/assembly.py
python scripts/urdf path/to/assembly.py -o path/to/robot.urdf
python scripts/urdf path/to/a.py=out/a.urdf path/to/b.py=out/b.urdf
```

纯 Python 目标会在源文件旁写入同级 `.urdf`。`-o`/`--output` 仅对单个纯目标有效。使用 `SOURCE.py=OUTPUT.urdf` 对来自定义多目标输出位置。

`gen_urdf()` 必须是顶层零参数函数，返回根 `xml.etree.ElementTree.Element`、完整的 URDF XML 字符串或其唯一字段为 `xml` 的已接受封装。参见 `references/generator-contract.md`。

相对源目标和 CLI 输出路径从当前工作目录解析。

## 默认验证（validation）行为

生成命令在接受输出前验证生成的 URDF。本技能中没有单独的仅验证（validation）命令。

生成失败应视为模型或源码问题，而非手动编辑生成 `.urdf` 的理由。修复生成器源码，然后重新生成显式目标。

生成时验证（validation）旨在捕获紧凑的机器人描述问题，例如：

- XML 格式错误或根元素错误；
- 连杆（link）或关节（joint）名称缺失或重复；
- 无效的父/子引用；
- 多根、断开的图或环；
- 可疑的关节（joint）限位、轴、原点、几何、网格（mesh）引用或惯性参数（inertial）（运行时支持时）。

## 边界

本工具仅运行 `gen_urdf()`。它不重新生成 CAD、网格（mesh）/导出、GLB/拓扑（topology）、渲染、SDF、SRDF、MoveIt2 或仿真器输出。

如果 URDF 视觉/碰撞（collision）网格（mesh）引用依赖于已更新的 CAD 或网格（mesh）输出，请先用所属的 CAD 或网格（mesh）工作流（workflow）单独重新生成那些显式目标，再重新生成受影响的 URDF。

创建或修改生成的 `.urdf` 文件后，当可用时将显式路径交接（handoff）给 `$cad-viewer` 以获取实时查看器链接。

## 失败处理

当生成时验证（validation）失败时：

1. 检查报告的连杆（link）、关节（joint）、网格（mesh）引用或惯性参数（inertial）字段；
2. 更新源生成器、设计清册（ledger）或引用资产；
3. 重新生成相同的显式 URDF 目标；
4. 不要直接修补生成的 `.urdf`，除非任务明确为取证目的，且该修补不会被当作源真相。
