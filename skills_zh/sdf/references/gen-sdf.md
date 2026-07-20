# SDF 生成命令

使用 SDF 启动器从带有顶层 `gen_sdf()` 函数的 Python 源文件重新生成显式 SDFormat 输出。

```bash
python scripts/sdf path/to/model.py
python scripts/sdf path/to/model.py -o path/to/robot.sdf
python scripts/sdf path/to/a.py=out/a.sdf path/to/b.py=out/b.sdf
```

普通 Python 目标在其源文件旁写入同级 `.sdf` 文件。`-o` / `--output` 仅对单个普通目标有效。使用 `SOURCE.py=OUTPUT.sdf` 对可实现自定义多目标输出位置。

相对源目标和 CLI 输出路径从当前工作目录解析。当从技能目录之外运行时，为启动器路径添加前缀，以便源文件和目标文件仍能从预期工作区解析。

## 命令的功能

该工具应：

1. 导入目标 Python 源文件；
2. 调用顶层零参数 `gen_sdf()`；
3. 规范化返回的 SDF XML 或信封（envelope）；
4. 解析生成的 XML；
5. 运行内置的轻依赖校验；
6. 如果请求且可用，可选地运行外部 `gz sdf --check`；
7. 仅在必需检查通过后写入请求的 `.sdf`；
8. 打印结构化警告和假设。

该命令**不**重新生成几何（geometry）、mesh、GLB/拓扑（topology）输出、渲染资产、robot-description 文件、规划元数据或仿真器资源包。在重新生成引用它们的 SDF 之前，先使用其所属工作流（workflow）重新生成这些内容。

## 可选外部检查

如果实现，推荐标志为：

```bash
python scripts/sdf path/to/model.py --gz-check auto
python scripts/sdf path/to/model.py --gz-check required
python scripts/sdf path/to/model.py --gz-check never
python scripts/sdf path/to/model.py --strict
```

- `auto`：当 `gz` 可用时运行 `gz sdf --check`；否则报告该检查为跳过并继续。
- `required`：如果 `gz` 不可用或 `gz sdf --check` 退出码非零则失败。
- `never`：跳过外部检查。

如果外部检查器需要路径，先写入临时文件。在内置校验和所有必需外部检查通过之前，不要覆盖目标。

## 失败行为

如果校验失败，不写入新生成的有效载荷。现有输出文件可能是陈旧的；修复 Python 源文件并重新生成。

错误应是阻塞的。警告和假设应被报告，但不应导致生成失败，除非用户或 CI 明确要求严格行为。

## 执行安全

启动器导入生成器模块。生成器文件中的顶层 Python 代码可能会执行。仅对本命令用于受信任的项目源文件。未来的子进程运行器可能会减少意外副作用，但无法使不受信任的 Python 变得安全。
