# SDF 参考系（frame）与位姿（pose）语义

在编辑任何 SDF `<pose>`、`<frame>`、`<joint>`、`<axis>`、`<visual>`、`<collision>`、传感器（sensor）或插件（plugin）放置之前使用本参考。

## 核心位姿（pose）规则

典型的 SDF 位姿（pose）为：

```xml
<pose relative_to="some_frame">x y z roll pitch yaw</pose>
```

或者，使用四元数旋转时：

```xml
<pose rotation_format="quat_xyzw" relative_to="some_frame">x y z qx qy qz qw</pose>
```

需牢记的规则：

- 前三个值是位置。
- 使用默认 `rotation_format="euler_rpy"` 时，位姿（pose）有六个值：`x y z roll pitch yaw`。
- 使用 `rotation_format="quat_xyzw"` 时，位姿（pose）有七个值：`x y z qx qy qz qw`。
- 欧拉角默认为弧度。`degrees="true"` 是合法的 SDF，但在生成的源文件中应避免使用，除非目标明确要求。
- `relative_to` 命名位姿（pose）所表达的参考系（frame）。
- 如果省略 `relative_to`，SDF 应用元素特定的默认值，通常是父 XML 元素的参考系（frame）。这可能是合法的，但容易被误读。对于非平凡的生成位姿（pose），优先使用显式 `relative_to`。
- 嵌套作用域可使用 `::`，例如 `outer_model::inner_model::sensor_frame`。

## 关节（joint）位姿（pose）和轴

对于 SDF 关节（joint）：

- `<parent>` 命名父参考系（frame）或 `world`。
- `<child>` 命名子参考系（frame）；`world` 不能作为子级。
- 关节（joint）位姿（pose）默认值容易被误解。当关节（joint）参考系（frame）明显不是子连杆（link）参考系（frame）时，使用显式 `<pose relative_to="...">`。
- `<axis><xyz>...</xyz></axis>` 是单位轴向量。
- 轴在关节（joint）参考系（frame）中表达，除非轴的 `expressed_in` 属性指定了其他参考系（frame）。
- `axis2` 用于多轴关节（joint），如 `revolute2` 和 `universal`。
- 轴向量应为有限、非零且归一化的。

在设计台账（design ledger）中记录预期的正向运动。示例："正向 shoulder_pan 从 +Z 方向观察时逆时针旋转连杆（link）（arm）。"

## visual 和 collision 位姿（pose）

`<visual>` 或 `<collision>` 的位姿（pose）将该几何（geometry）所有者相对于其父参考系（frame）放置，除非 `relative_to` 另有说明。在普通模型级（model-level）使用中，该父级是连杆（link）参考系（frame）。

不要用 visual 偏移来掩盖错误的连杆（link）或关节（joint）参考系（frame）。如果 mesh 因 mesh 资产原点不是连杆（link）参考系（frame）而需要偏移，请在几何（geometry）表中记录该事实。

## 命名参考系（frame）

当某个可复用变换（transform）有意义时使用 `<frame>`：

```xml
<frame name="camera_optical_frame" attached_to="camera_link">
  <pose relative_to="camera_link">0 0 0 -1.57079632679 0 -1.57079632679</pose>
</frame>
```

参考系（frame）对传感器（sensor）、插件（plugin）、工具参考系（frame）、嵌套模型（model）和重复放置逻辑很有用。它们也使生成的 SDF 更可审计。

`attached_to` 和 `relative_to` 是不同的：

- `attached_to` 表示参考系（frame）随什么移动。
- `relative_to` 表示参考系（frame）的位姿（pose）数值如何表示。

`attached_to` 链不应循环，并应最终解析到一个连杆（link）、模型（model）、世界（world）、关节（joint）或其他合法参考系（frame）目标。

## LLM 护栏

不要仅凭文字推断以下任何内容：

- 关节（joint）轴的符号；
- 轴所表达的参考系（frame）；
- RPY 顺序或单位；
- mesh 原点约定；
- `relative_to` 参考系（frame）；
- 嵌套作用域引用；
- 传感器（sensor）光学参考系（frame）变换（transform）；
- 插件（plugin）参考系（frame）/topic 语义。

当数据缺失时，要么请求源数据，要么编写一个显式标注的假设。

## 有用的官方参考

- SDFormat 位姿（pose）语义：`https://sdformat.org/tutorials?tut=pose_frame_semantics`
- SDFormat 位姿（pose）字段：`https://sdformat.org/spec/1.12/world/`
- SDFormat 关节（joint）元素：`https://sdformat.org/spec/1.12/joint/`
