[English](README.md) | **简体中文** | [日本語](README.ja.md)

<div align="center">

<img src="assets/text-to-cad-demo.gif" alt="CAD 技能生成并预览 CAD 几何体的演示" width="100%">

<br>

<pre>
 ██████╗ █████╗ ██████╗       ███████╗██╗  ██╗██╗██╗     ██╗     ███████╗
██╔════╝██╔══██╗██╔══██╗      ██╔════╝██║ ██╔╝██║██║     ██║     ██╔════╝
██║     ███████║██║  ██║      ███████╗█████╔╝ ██║██║     ██║     ███████╗
██║     ██╔══██║██║  ██║      ╚════██║██╔═██╗ ██║██║     ██║     ╚════██║
╚██████╗██║  ██║██████╔╝      ███████║██║  ██╗██║███████╗███████╗███████║
 ╚═════╝╚═╝  ╚═╝╚═════╝       ╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚══════╝
</pre>

面向 CAD、机器人和硬件设计代理的技能库

[文档](https://www.cadskills.xyz) | [演示](https://demo.cadskills.xyz)

[![加入 Discord](https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5FGB9DwJYU)
[![GitHub stars](https://img.shields.io/github/stars/earthtojake/text-to-cad?style=for-the-badge&logo=github&label=Stars)](https://github.com/earthtojake/text-to-cad/stargazers)
[![许可证：MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![关注 @earthtojake](https://img.shields.io/badge/Follow-%40earthtojake-000000?style=for-the-badge&logo=x)](https://x.com/earthtojake)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](skills/cad/requirements.txt)
[![STEP](https://img.shields.io/badge/STEP-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![STL](https://img.shields.io/badge/STL-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![3MF](https://img.shields.io/badge/3MF-Export-4A5568?style=for-the-badge)](skills/cad/SKILL.md)
[![URDF](https://img.shields.io/badge/URDF-Robots-6B46C1?style=for-the-badge)](skills/urdf/SKILL.md)
[![SDF](https://img.shields.io/badge/SDF-Simulation-6B46C1?style=for-the-badge)](skills/sdf/SKILL.md)
[![SRDF](https://img.shields.io/badge/SRDF-MoveIt2-6B46C1?style=for-the-badge)](skills/srdf/SKILL.md)

</div>

# CAD 技能

CAD Skills 是一个代理技能库，用于从本地项目文件生成、检查、查找、
切片和交付 CAD 及机器人描述
文件。

## 🧰 技能

安装该技能库，即可为代理提供面向 CAD、制造、
机器人描述文件、仿真和本地审查的专用工作流。

| 技能         | 简介                                                                                                                                                  | 源文件                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CAD          | 根据自然语言或图像请求创建和编辑 CAD 模型，以 STEP 为主要输出，并可选择导出为 STL、3MF 和 GLB。                                                       | [skills/cad](skills/cad/SKILL.md)                   |
| CAD Viewer   | 在本地浏览器中预览 CAD、G-code 和机器人文件。                                                                                                         | [skills/cad-viewer](skills/cad-viewer/SKILL.md)     |
| step.parts   | 查找螺钉、轴承、电机和连接器等现成的 STEP 零件。                                                                                                     | [skills/step-parts](skills/step-parts/SKILL.md)     |
| DXF          | 从 Python 源文件或 CAD 几何体创建轮廓、模板、垫片和切割排版等二维 DXF 图纸。                                                                           | [skills/dxf](skills/dxf/SKILL.md)                   |
| URDF         | 编写包含 link、joint、limit、inertial 和 mesh 的机器人结构文件。                                                                                       | [skills/urdf](skills/urdf/SKILL.md)                 |
| SRDF         | 为 URDF 添加 MoveIt 规划组、末端执行器、姿态和碰撞规则。                                                                                              | [skills/srdf](skills/srdf/SKILL.md)                 |
| SDF          | 创建包含 frame、物理属性、传感器和灯光的仿真器模型与世界。                                                                                            | [skills/sdf](skills/sdf/SKILL.md)                   |
| SendCutSend  | 在上传到 SendCutSend 前检查 DXF 和 STEP 文件。                                                                                                        | [skills/sendcutsend](skills/sendcutsend/SKILL.md)   |
| G-code       | 使用真实的切片器 CLI，将支持的网格文件切片为经过验证、带打印机配置的 FDM `.gcode`。                                                                    | [skills/gcode](skills/gcode/SKILL.md)               |
| Bambu Labs   | 对经过验证的 `.gcode` 执行试运行、上传，并谨慎启动本地 Bambu Lab 打印任务。                                                                            | [skills/bambu-labs](skills/bambu-labs/SKILL.md)     |
| Implicit CAD | 使用 GLSL 有符号距离场和 CAD Viewer 光线步进渲染创建浏览器原生的隐式 CAD 模型。此功能为实验性质。                                                       | [skills/implicit-cad](skills/implicit-cad/SKILL.md) |

## 💻 安装

用于生产环境时，请从 `main` 分支安装或克隆；该分支包含
提供商安装程序所需的已生成技能和插件输出。

### 技能

使用 Skills CLI 安装 CAD Skills：

```bash
npx skills install earthtojake/text-to-cad
```

这是首选安装方式。它会为支持的代理
直接安装各个技能。

### 插件

Codex 和 Claude Code 也支持提供商原生的插件安装方式：

```bash
# Codex
codex plugin marketplace add earthtojake/text-to-cad
codex plugin add cad@text-to-cad
```

```bash
# Claude Code
claude plugin marketplace add earthtojake/text-to-cad
claude plugin install cad@text-to-cad
```

如果新安装的技能没有出现，请重启或重新加载代理。本地
开发时，请从 `develop` 创建分支、向 `develop` 提交 PR，并使用
[CONTRIBUTING.md](CONTRIBUTING.md) 中的符号链接工作流。

## 📸 截图

<table>
  <tr>
    <td width="33%">
      <a href="./assets/text-to-cad-demo.gif">
        <img src="./assets/text-to-cad-demo.gif" alt="CAD 技能在 CAD Viewer 中显示生成几何体的演示" width="100%">
      </a>
      <a href="./skills/cad/SKILL.md"><strong>CAD</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/urdf-demo.gif">
        <img src="./assets/urdf-demo.gif" alt="URDF 技能在 CAD Viewer 中显示机器人描述输出的演示" width="100%">
      </a>
      <a href="./skills/urdf/SKILL.md"><strong>URDF</strong></a>
    </td>
    <td width="33%">
      <a href="./assets/srdf-moveit2-demo.gif">
        <img src="./assets/srdf-moveit2-demo.gif" alt="SRDF MoveIt2 技能在 CAD Viewer 中显示逆运动学的演示" width="100%">
      </a>
      <a href="./skills/srdf/SKILL.md"><strong>SRDF / MoveIt2</strong></a>
    </td>
  </tr>
</table>

## 🧪 基准测试

该仓库通过 Git LFS 存储 `assets/**` 和 `benchmarks/**` 中的大型资源，并将这些目录排除在默认 LFS 拉取之外，以免轻量克隆下载 GIF 资源。基准测试 Markdown 仍作为普通 Git 文件保存，便于查看差异。若只需在本地下载基准测试资源，请运行：

```bash
git lfs pull --include="benchmarks/**"
```

<table>
  <thead>
    <tr>
      <th>#</th>
      <th>目标</th>
      <th>提示词</th>
      <th>输出</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>1</td>
      <td><a href="benchmarks/01-rectangular-calibration-block.md">带四个孔的矩形校准块</a></td>
      <td>创建一个居中的 100 × 60 × 20 mm 块体，带四个直径 8 mm 的竖直通孔。仅在顶部外周添加 2 mm 倒角。</td>
      <td><img src="benchmarks/benchmark_01_rectangular_calibration_block.gif" alt="矩形校准块环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>2</td>
      <td><a href="benchmarks/02-circular-flange.md">带螺栓孔阵列的圆形法兰</a></td>
      <td>创建直径 80 mm、厚 10 mm 的圆形法兰，并带直径 30 mm 的中心通孔。在直径 60 mm 的螺栓分布圆上添加六个直径 6 mm 的通孔，并为外侧圆边添加圆角。</td>
      <td><img src="benchmarks/benchmark_02_circular_flange.gif" alt="圆形法兰环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>3</td>
      <td><a href="benchmarks/03-l-bracket.md">带加强筋和两个孔向的 L 形支架</a></td>
      <td>使用底板和后部竖板创建 L 形支架。添加竖直底板孔、水平后板孔、两个三角加强筋，以及底板与后板连接处的圆角过渡。</td>
      <td><img src="benchmarks/benchmark_03_l_bracket.gif" alt="L 形支架环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>4</td>
      <td><a href="benchmarks/04-stepped-shaft-keyway.md">带键槽的阶梯轴</a></td>
      <td>沿 X 轴创建一根长 120 mm、各段直径为 20/30/20 mm 的阶梯轴。为两端添加倒角，并在中段顶部添加浅矩形键槽。</td>
      <td><img src="benchmarks/benchmark_04_stepped_shaft_keyway.gif" alt="阶梯轴环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>5</td>
      <td><a href="benchmarks/05-open-top-electronics-enclosure.md">带凸台的顶部开放式电子设备外壳</a></td>
      <td>创建壁厚和底厚均为 3 mm 的中空顶部开放式外壳。添加四个带居中盲孔的内部支柱，并为外侧竖直角添加 2 mm 圆角。</td>
      <td><img src="benchmarks/benchmark_05_open_top_electronics_enclosure.gif" alt="顶部开放式电子设备外壳环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>6</td>
      <td><a href="benchmarks/06-clevis-bracket-lightening-cutouts.md">带减重开孔的航空风格叉形支架</a></td>
      <td>创建一个对称叉形支架，包含底板、两个圆头耳板、底座安装孔和水平耳板通孔。添加三角形减重开孔、加强肋和圆滑过渡。</td>
      <td><img src="benchmarks/benchmark_06_clevis_bracket_lightening_cutouts.gif" alt="叉形支架环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>7</td>
      <td><a href="benchmarks/07-radial-engine-cylinder.md">带散热片的星形发动机风格气缸</a></td>
      <td>创建一个竖直发动机气缸造型，包含中央缸筒、12 个散热片、底部法兰和顶盖。添加倾斜 35 度的火花塞凸台及同轴通孔。</td>
      <td><img src="benchmarks/benchmark_07_radial_engine_cylinder.gif" alt="星形发动机风格气缸环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>8</td>
      <td><a href="benchmarks/08-centrifugal-impeller.md">带后弯叶片的离心叶轮</a></td>
      <td>创建包含后盖板、轮毂和通孔的离心叶轮。添加 12 个融合的后弯叶片，使其从根部到尖端扫过约 45 度。</td>
      <td><img src="benchmarks/benchmark_08_centrifugal_impeller.gif" alt="离心叶轮环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>9</td>
      <td><a href="benchmarks/09-spiral-staircase.md">带螺旋扶手的旋转楼梯</a></td>
      <td>创建一座微型旋转楼梯，包含中央立柱、底盘和 20 个逐级升高的楔形踏步。添加一圈螺旋扶手，并在踏步外端设置竖直栏杆柱。</td>
      <td><img src="benchmarks/benchmark_09_spiral_staircase.gif" alt="旋转楼梯环绕动画" width="220"></td>
    </tr>
    <tr>
      <td>10</td>
      <td><a href="benchmarks/10-planetary-gear-stage.md">简化的行星齿轮级</a></td>
      <td>创建一个扁平行星齿轮组件，包含独立的太阳轮、行星轮、齿圈、行星架和销轴实体。使用简化的梯形齿，并将三个行星轮布置在太阳轮周围半径 42 mm 的圆周上。</td>
      <td><img src="benchmarks/benchmark_10_planetary_gear_stage.gif" alt="行星齿轮级环绕动画" width="220"></td>
    </tr>
  </tbody>
</table>

## 🛠️ 贡献

开发工作基于 `develop` 分支进行；请向 `develop` 而不是 `main` 提交 PR。
有关本地贡献工作流、技能链接和验证指南，请参阅
[CONTRIBUTING.md](CONTRIBUTING.md)。
