# 修复循环

当生成、导出、检查、定位、snapshot 审查、CAD Viewer 设置或文档 validation 失败时，请阅读此文件。

## 循环

1. 阅读失败命令输出。
2. 对失败进行分类。
3. 做出最小的负责任的源码或命令更改。
4. 重新运行失败的命令。
5. 重新运行任何依赖的 validation 检查。
6. 报告剩余风险或故意偏差。

## 失败类别和修复

### 源码导入或语法失败

可能原因：

- 无效的 Python 语法
- 缺少导入
- 错误的 build123d 符号
- 函数未命名为 `gen_step()`
- 预期函数之外的可执行代码有副作用

修复：

- 更正导入和语法
- 确保 `gen_step()` 返回 STEP 就绪的形状或 compound
- 将输出路径保留在 CLI 命令中，而非 `gen_step()` 内部

### 无效或缺少几何体

可能原因：

- 开放草图
- 减法轮廓在目标之外
- 零厚度
- 布尔操作失败
- 构造几何体用作导出几何体

修复：

- 关闭意图成为面的轮廓
- 验证（validation）尺寸为正
- 当意图为贯穿切割时使减法工具穿过
- 简化失败特征并增量重建

### Fillet 或 chamfer 失败

可能原因：

- 半径/长度超过局部几何体
- 所选边包含微小或非预期边
- 布尔操作创建了复杂的边 topology

修复：

- 减小半径/长度
- 更窄地筛选所选边
- 在模型中稍后应用 fillet
- 按特征 intent 分割边组

### 错误比例或边界框

可能原因：

- 单位不匹配
- 直径/半径错误
- 挤出方向或量错误
- part 未按假设居中
- 直接导入的 STEP 使用意外单位

修复：

- 检查参数值
- 检查 facts 和 planes
- 测量关键范围
- 更正源码尺寸或导入处理

### 缺少特征

可能原因：

- 错误的 `Mode.ADD`/`Mode.SUBTRACT`
- 特征轮廓不在目标内
- blind cut 太浅
- 先前操作后 selector 改变

修复：

- 确认特征模式
- 对贯穿切割增加切割长度
- 检查 topology 或 planes
- 重新生成并测量/检查特征特定 ref

### Selector 脆弱性

可能原因：

- 任意索引选择
- fillet 或布尔后 topology 改变
- 相似面/边无法区分

修复：

- 按轴、平面、位置、法线或检查的参考选择
- 使用 `refs --facts --planes --positioning` 重新发现稳定参考
- 如有需要，添加构造 datum 或简化操作

### 定位或 joint 不匹配

可能原因：错误的 part 局部原点或 datum、反转的 `AssemblyHelper` 固定/移动顺序、`.connect_to()` 移动错误的 part、反转的 joint 轴、对称放置中的符号错误、参数更改后未重新计算的显式 `Location`，或当意图是 part 局部 datum 时在世界坐标中定义的 joint。

修复：

- 检查 `refs --positioning`，然后对相关 selector 进行 `frame` 和 `align`
- 验证（validation）源码级 `AssemblyHelper` 目标顺序、joint 标签和 `joint_location` 定义
- 从 `positioning.md`（源码级定位修正）中的列表应用最小的源码修正
- 从 Python 源码重新生成 assembly 并重新运行失败的检查

### CAD Viewer 启动或链接失败

可能原因：

- Node/npm 不可用
- CAD Viewer 应用未构建或无法启动
- 活动 Viewer URL 缺少项目的绝对 `?dir=`
- 返回的链接缺少绝对 `file=` 路径或指向 `?dir=` 之外

修复：

- 用相同的绝对 `?dir=`（针对项目）和每个 artifact 的绝对 `file=` 路径重新运行 `$cad-viewer`
- 每个请求的文件返回一个有文档记录的 Viewer 链接
- 如未解决，报告启动失败并依赖 CLI facts/measurements 加 snapshot 进行 validation

### CAD `scripts/snapshot` 失败

可能原因：

- 目标输入路径错误、缺少或不是 STEP/STP 文件或同词干 Python 生成器
- 相邻 CAD Viewer GLB/topology artifact 缺失
- 无效的渲染标志

修复：

- 先生成 STEP，然后对主要 `.step`/`.stp` artifact 进行 snapshot
- 仅使用更简单的支持 snapshot 作业重试，从单个 `view` 输出开始，再进行 wireframe 显示或 `section`
- 按照 `snapshot-review.md` 选择模式和包大小

## 修复后 diff

当修复可能影响无关几何体时使用 `diff`：

```bash
python scripts/inspect diff path/to/before.step path/to/after.step --planes
```

## 报告失败的修复

如果检查无法在当前环境中修复，报告：

```text
- what failed
- what was tried
- which artifact is still usable
- which validation claims cannot be made
- what the next source-level correction should be
```
