# G-code 验证（validation）

`scripts/gcode_tool.py validate` 仅执行静态检查。它不模拟挤出物理、固件状态、加速度限制或切片器特定的语义。

## 必要检查

验证（validation）失败的情况：

- 文件为空。
- 不存在 `G0`、`G1`、`G2` 或 `G3` 运动命令。
- 不存在挤出移动。
- 不存在喷嘴或热床温度命令。
- 解析的绝对 `X`、`Y` 或 `Z` 移动超出封装 profile 的运动边界。

验证（validation）发出警告的情况：

- 遇到未知或不支持的 G-code 命令。
- 使用了相对定位；在相对模式激活期间跳过边界检查。

警告不会重写或删除命令。将它们视为审查提示，尤其是在将 G-code 发送到不熟悉的固件之前。

## 边界策略

验证（validation）器假定使用绝对定位，直到出现 `G91`，并在 `G90` 之后恢复绝对边界检查。这避免了相对运动块的误判硬失败，同时仍能捕获明显的超出热床的绝对移动。

封装 profile 提供可打印边界：

- `machine.bed_size_mm[0]`：最大 `X`
- `machine.bed_size_mm[1]`：最大 `Y`
- `machine.z_height_mm`：最大 `Z`

默认情况下，运动边界为 `X=0..bed_size_mm[0]`、`Y=0..bed_size_mm[1]` 和 `Z=0..z_height_mm`。如果原生打印机 profile 有意使用安全的热床外擦拭、排料或维护位置，请使用显式的 `x`、`y` 和/或 `z` `[min, max]` 范围设置 `machine.motion_bounds_mm`。仅从真实的打印机/profile 来源执行此操作，而不是作为消除未知 G-code 警告的手段。

## 解读结果

`ok: true` 表示文件通过了这些静态检查。这并不意味着 G-code 可以安全地在真实硬件上打印。仍需审查：

- 打印机/profile 匹配。
- 耗材和温度设置。
- 起始和结束 G-code。
- 热床原点和坐标系。
- 任何未知命令警告。
