# URDF 参考系（frame）语义

在编辑原点、轴、视觉放置、碰撞（collision）放置或惯性参数（inertial）时使用本参考。大多数 URDF 生成错误是参考系（frame）错误。

## 核心语义

URDF 将机器人表示为由关节（joint）连接的连杆（link）树。

对于关节（joint）：

- `<parent link="...">` 命名父连杆（link）。
- `<child link="...">` 命名子连杆（link）。
- `<origin xyz="..." rpy="...">` 是从父连杆（link）参考系（frame）到关节（joint）参考系（frame）的变换。
- 子连杆（link）参考系（frame）与关节（joint）参考系（frame）重合。
- 对于可动关节（joint），`<axis xyz="...">` 在关节（joint）参考系（frame）中表达，而非自动在世界参考系（frame）或视觉网格（mesh）参考系（frame）中。

对于连杆（link）子元素：

- `<visual><origin ...>` 在连杆（link）参考系（frame）中表达。
- `<collision><origin ...>` 在连杆（link）参考系（frame）中表达。
- `<inertial><origin ...>` 是在连杆（link）参考系（frame）中表达的质心/惯性参数（inertial）参考系（frame）。

这些原点是独立的。网格（mesh）可以相对于其连杆（link）参考系（frame）偏移，质心也可以有不同的偏移。

## 单位和角度

使用：

- 长度用米；
- 质量用千克；
- 角度用弧度；
- 时间用秒；
- 右手坐标系，除非项目记录了例外。

不要在生成的 URDF 中以度存储 revolute 限位。在输出前将度转换为弧度。

不要对 `continuous` 关节（joint）使用有限上下限，除非项目有意不使用 URDF continuous 关节（joint）语义。

## 关节（joint）轴检查清单（manifest）

对于每个非固定关节（joint），确认：

1. 轴存在；
2. 轴向量有三个有限数字；
3. 向量非零；
4. 向量已归一化或由辅助代码有意归一化；
5. 向量在关节（joint）参考系（frame）中表达；
6. 正向运动已记录。

示例：

```xml
<joint name="shoulder_pan_joint" type="revolute">
  <parent link="base_link" />
  <child link="shoulder_link" />
  <origin xyz="0 0 0.24" rpy="0 0 0" />
  <axis xyz="0 0 1" />
  <limit lower="-3.14159" upper="3.14159" effort="40" velocity="2" />
</joint>
```

这意味着子连杆（link）参考系（frame）在 `base_link` 中位于 `z = 0.24`，正向关节（joint）运动绕关节（joint）/子参考系（frame）的 +Z 旋转。

## 视觉和碰撞（collision）放置检查清单（manifest）

对于每个视觉或碰撞（collision）块，确认：

1. 原点相对于所属连杆（link）参考系（frame）；
2. 网格（mesh）缩放将网格（mesh）源单位转换为米；
3. 视觉和碰撞（collision）几何有意相同或有意不同；
4. 碰撞（collision）几何对于预期的物理/规划消费者足够简单；
5. 网格（mesh）路径从生成的 URDF 位置稳定可访问，或使用预期的 package URI。

示例：

```xml
<link name="forearm_link">
  <visual>
    <origin xyz="0 0 0" rpy="0 0 0" />
    <geometry>
      <mesh filename="package://robot_description/meshes/forearm.stl" scale="0.001 0.001 0.001" />
    </geometry>
  </visual>
  <collision>
    <origin xyz="0.12 0 0" rpy="0 1.57079632679 0" />
    <geometry>
      <cylinder radius="0.035" length="0.24" />
    </geometry>
  </collision>
</link>
```

这将视觉网格（mesh）放置在连杆（link）参考系（frame）处，并在同一连杆（link）参考系（frame）中使用偏移的简化碰撞（collision）圆柱体。

## 惯性参数（inertial）放置检查清单（manifest）

对于每个带惯性参数（inertial）数据的物理连杆（link），确认：

1. 质量为正且有限；
2. 惯性参数（inertial）原点是连杆（link）参考系（frame）中的质心；
3. 惯性张量值使用 SI 单位；
4. 张量值对应所声明的惯性参数（inertial）参考系（frame）；
5. 近似值已记录。

不要从视觉或碰撞（collision）原点推断惯性参数（inertial）原点，除非源数据证明它们重合。
