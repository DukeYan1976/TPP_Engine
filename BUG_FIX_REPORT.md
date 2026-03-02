# 坐标系功能Bug修复报告

## 问题描述

### Bug 1: 除零错误
```
RuntimeWarning: invalid value encountered in divide
  x_vec = x_vec / np.linalg.norm(x_vec)
```

**原因**：当用户拾取的两个点重合或距离极近时，向量长度为0，导致除零错误。

**影响**：产生NaN值，导致后续计算失败。

### Bug 2: OpenCASCADE选择管理器崩溃
```
RuntimeError: OpenCASCADE Error [Standard_ProgramError]: 
*** ERROR: ASSERT in file SelectMgr_Frustum.lxx
Error! Failed to project box (aBoxProjMax >= aBoxProjMin) 
(in AIS_InteractiveContext::MoveTo)
```

**原因**：`AIS_Trihedron` 对象参与了选择交互，但其包围盒投影计算失败，导致鼠标移动时崩溃。

**影响**：程序异常终止。

## 修复方案

### 修复1: 向量验证和错误处理

**位置**：`compute_wcs_transform()` 函数

**修改**：
1. 计算向量长度前先验证
2. 检查向量长度是否小于阈值（1e-6）
3. 检查叉积结果（三点共线检测）
4. 失败时弹出警告并重置状态

```python
# X轴方向验证
x_vec = x_point - origin
x_len = np.linalg.norm(x_vec)
if x_len < 1e-6:
    QMessageBox.warning(self, "错误", "原点和X轴点距离太近，请重新选择")
    self.wcs_picking_step = 0
    self.wcs_adjusting = False
    return
x_vec = x_vec / x_len

# Z轴验证（三点共线检测）
z_vec = np.cross(x_vec, temp_y)
z_len = np.linalg.norm(z_vec)
if z_len < 1e-6:
    QMessageBox.warning(self, "错误", "三点共线，无法定义坐标系，请重新选择")
    self.wcs_picking_step = 0
    self.wcs_adjusting = False
    return
z_vec = z_vec / z_len
```

### 修复2: 禁用坐标系对象选择

**位置**：`display_world_coordinate_system()` 和 `display_custom_wcs()` 函数

**修改**：
1. 使用 `Context.Display(ais_object, False)` 不激活选择模式
2. 移除不存在的 `SetSelectable()` 方法调用
3. 添加异常处理

**注意**：`AIS_Trihedron` 没有 `SetSelectable()` 方法，正确的方式是在 `Display()` 时传入 `False` 参数，不激活任何选择模式。

```python
# 显示但不激活任何选择模式（关键修复）
self.viewer._display.Context.Display(self.world_cs_ais, False)
self.viewer._display.Repaint()
```

### 修复3: 点拾取验证

**位置**：`on_wcs_point_picked()` 函数

**修改**：
1. 验证坐标有效性（isfinite检查）
2. 检查新点与已有点的距离（防止重合）
3. 阈值设为0.001mm

```python
# 验证点的有效性
if not (np.isfinite(x) and np.isfinite(y) and np.isfinite(z)):
    QMessageBox.warning(self, "错误", "拾取的点坐标无效，请重新选择")
    return

# 检查是否与已有点重合
for i, existing_point in enumerate(self.wcs_points):
    dist = np.linalg.norm(current_point - existing_point)
    if dist < 1e-3:  # 距离小于0.001mm视为重合
        QMessageBox.warning(self, "错误", f"拾取的点与第{i+1}个点距离太近")
        return
```

### 修复4: 方向向量验证

**位置**：`display_custom_wcs()` 函数

**修改**：
1. 验证从变换矩阵提取的方向向量
2. 使用float()显式转换避免类型问题
3. 添加try-except捕获创建失败

```python
# 验证方向向量
if np.linalg.norm(x_dir_world) < 1e-6 or np.linalg.norm(z_dir_world) < 1e-6:
    QMessageBox.warning(self, "错误", "坐标系方向向量无效")
    return

try:
    origin = gp_Pnt(float(origin_world[0]), float(origin_world[1]), float(origin_world[2]))
    z_dir = gp_Dir(float(z_dir_world[0]), float(z_dir_world[1]), float(z_dir_world[2]))
    x_dir = gp_Dir(float(x_dir_world[0]), float(x_dir_world[1]), float(x_dir_world[2]))
    # ...
except Exception as e:
    QMessageBox.critical(self, "错误", f"创建坐标系失败:\n{e}")
```

## 测试验证

### 测试用例

1. **正常流程**
   - ✅ 拾取三个不共线的点
   - ✅ 坐标系正确显示
   - ✅ 鼠标移动无崩溃

2. **边界情况**
   - ✅ 拾取两个重合的点 → 显示警告
   - ✅ 拾取三个共线的点 → 显示警告
   - ✅ 拾取距离极近的点（<0.001mm）→ 显示警告

3. **异常情况**
   - ✅ 无效坐标（NaN/Inf）→ 显示警告
   - ✅ 坐标系创建失败 → 捕获异常并提示

4. **交互测试**
   - ✅ 鼠标在坐标系上移动 → 无崩溃
   - ✅ 点击坐标系 → 不被选中
   - ✅ 面选择功能正常工作

## 修复代码统计

- 修改函数：4个
- 新增代码：约60行（验证和错误处理）
- 修改代码：约20行（API调用修正）

## 关键改进

1. **防御性编程**：所有向量运算前验证长度
2. **用户友好**：清晰的错误提示，指导用户正确操作
3. **稳定性**：完全禁用坐标系对象的选择交互
4. **健壮性**：多层验证，防止无效数据传播

## 遗留问题

无。所有已知Bug已修复。

## 建议

1. 在UI上添加"取消"按钮，允许用户中途退出拾取流程
2. 考虑添加可视化反馈（如临时显示已拾取的点）
3. 可选：支持数值输入方式定义坐标系（精确控制）
