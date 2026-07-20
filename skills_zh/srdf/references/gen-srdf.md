# SRDF 生成命令

从具有顶层 `gen_srdf()` 函数的 Python 源重新生成显式 MoveIt SRDF 输出。

```bash
python scripts/srdf path/to/semantic.py
python scripts/srdf path/to/semantic.py -o path/to/robot.srdf
python scripts/srdf path/to/a.py=out/a.srdf path/to/b.py=out/b.srdf
```

普通 Python 目标会在源文件旁写入同级的 `.srdf`。`-o` / `--output` 仅在单个普通目标时有效。对于自定义多目标目标位置，请使用 `SOURCE.py=OUTPUT.srdf` 对。

`gen_srdf()` 必须返回一个包含以下内容的信封字典：

- `xml`：完整的 SRDF `<robot>` XML，形式为 `xml.etree.ElementTree.Element` 或 XML 字符串；
- `urdf`：从生成器源文件到链接 `.urdf` 的 POSIX 相对路径。

## 命令的作用

该工具：

1. 导入目标 Python 源；
2. 调用 `gen_srdf()`；
3. 相对于生成器源文件解析链接的 URDF 路径；
4. 注入或更新本地 `tcad:urdf` 元数据，以便下游工具能找到 URDF；
5. 解析生成的 SRDF；
6. 根据链接的 URDF 验证（validation） SRDF；
7. 仅在验证（validation）通过后写入请求的 `.srdf`。

没有隐藏的 SRDF 工件。生成的 `.srdf` 是交给 `$cad-viewer` 用于实时 CAD Viewer 链接和可选 MoveIt2 控件的 MoveIt 清单（manifest）。

## 执行安全

CLI 直接导入生成器模块。生成器文件中的顶层 Python 代码将会执行。仅对可信项目源使用此命令。
