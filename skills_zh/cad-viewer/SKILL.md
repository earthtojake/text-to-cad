---
name: cad-viewer
description: 启动或复用 CAD Viewer，并为显式 CAD、隐式 CAD、机器人描述文件和 G-code 文件返回评审链接。当需要可视化评审 `.step`、`.stp`、`.implicit.js`、`.implicit.mjs`、`.glb`、`.stl`、`.3mf`、`.gcode`、`.dxf`、`.urdf`、`.srdf` 或 `.sdf` 文件时使用，尤其是在从 CAD、implicit-cad、G-code、URDF、SRDF 或 SDF 生成技能交接（handoff）后使用。
---

# CAD Viewer

来源：维护于 [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)。
以已安装的本地技能文件作为运行时真相来源；仓库链接仅用于溯源和发布评审。

使用本技能可在 CAD Viewer 中打开既有或新生成的 CAD、隐式 CAD、机器人描述文件、DXF 或普通 FDM G-code 文件，并交回实时评审链接。预期输入为一个或多个显式文件路径。

## 启动 Viewer

通过 `npm run agent:start` 启动或复用一个本地 CAD Viewer，将绝对产物（artifact）目录作为 `--dir` 传入。`agent:start` 启动器负责端口选择、兼容服务器复用、目录激活以及 `?dir=` 查询参数。开发模式（dev-mode）的 Viewer 仅在 git 身份匹配时才会被复用；dist bundle 版本的 Viewer 在其 viewer 版本匹配时可跨 git 分支复用。它通过 Viewer 的轻量级目录激活 API 激活被复用的服务器，无需 agent 手动探测端口或触发目录扫描。直接使用 `agent:start` 打印的 Viewer URL，然后仅为待评审产物（artifact）添加 `file=` 查询值。

将 `--dir` 选为包含模型产物（artifact）和附带附带产物（sidecar）的绝对目录，通常是 `<repo>/models` 或消费项目中等效的模型目录。`file=` 的值必须相对于该 `--dir`。不要手动选择端口、探测服务器、改写 `?dir=`，也不要为了切换目录而启动一个单独的 Viewer。

在本技能目录下运行：

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --dir <absolute-model-root>
```

使用打印的 Viewer URL 并追加 `file=`：

```bash
http://127.0.0.1:<printed-port>/?dir=/absolute/project/models&file=path/to/model.step
```

如果候选端口被非 Viewer 进程或其他工作树（worktree）的 Viewer 占用，启动器会自动继续。在沙箱化的 agent 环境中，可能会出现 `EPERM` 或 `EACCES` 等本地绑定或探测失败；请使用所需权限/提权后重新运行同一命令。

## 链接

- 在返回任何 `file=` 链接之前，解析 `<dir>/<file>` 并确认产物（artifact）存在。传入生成的产物（artifact）（例如 `.step`），而非其生成器源码（例如 `.py`）。如果解析出的路径缺失，不要返回链接，而应报告问题并指向正确的生成产物（artifact）路径。
- 每个请求的文件返回一个 Viewer URL。
- 每个绝对目录 `--dir` 仅启动/复用一次 Viewer，然后为每个请求的文件追加 `file=<path>`。文件路径必须相对于 `--dir`。
- 对于仅目录的评审链接，返回 `agent:start` 打印的 URL，不添加 `file=`。
- 除非用户要求，否则不要停止已存在的 Viewer 服务器。
- 如果 Viewer 启动失败，报告该失败，并继续执行归属技能的非 GUI 验证（validation）或产物（artifact）。

## Claude Preview

viewer 的端口是动态的——它在启动时选择，在不同工作树之间可能不同。要与 Claude Preview 工具集成，请在 `agent:start` 命令中添加 `--json`：

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --dir <absolute-model-root> --json
```

启动器在人类可读的行之后，向 stdout 写入一行 JSON 结果。通过取 stdout 中以 `{` 开头的最后一行来解析它：

```json
{"url":"http://127.0.0.1:<port>/?dir=<absolute-model-root>","port":<port>,"action":"reuse"}
```

当复用了既有服务器且已立即就绪时，`action` 为 `"reuse"`；当生成了新的服务器进程且可能仍在初始化时，`action` 为 `"start"`。对于 `"start"` 结果，在将 `url` 值传给 Claude Preview 工具之前，请对基础 URL（例如 `http://127.0.0.1:<port>/__cad/server`）探测 `GET /__cad/server`，直到其返回 HTTP 200。

## 参考文档

- 当用户要求修改、调试或迭代 CAD Viewer 源码时，阅读 `references/development.md`。
- 当需要支持的文件类型、Viewer 控件或文件特定的功能细节时，阅读 `references/viewer-features.md`。
- 仅当用户明确需要可选的 SRDF MoveIt2 IK 或路径规划控件时，阅读 `references/moveit2-server.md`。
