# 自由曲面刀轨生成功能

**日期**: 2026-02-28  
**功能**: 支持 STEP 文件中自由曲面的刀轨计算

## 核心设计决策

### 1. 最大面选择策略
**问题**: STEP 文件可能包含多个面，如何选择加工对象？

**决策**: 自动选择面积最大的面进行刀轨计算

**原因**:
- 演示模型更换后的自适应计算能力
- 最大面通常是主加工面
- 简化用户交互，无需手动选择

**实现**: 使用 `BRepGProp::SurfaceProperties` 计算面积，遍历所有面并比较

### 2. 参数空间采样
**问题**: 如何在任意曲面上生成均匀刀轨？

**决策**: 在 U/V 参数空间进行等距采样，使用 Face 的参数范围而非 Surface 的参数范围

**原因**:
- 参数空间采样保证路径连续性
- 适用于所有类型的曲面（BSpline、NURBS、解析曲面）
- B-spline 曲面的 Surface 参数域可能无界（如 `[-2e+100, 2e+100]`），导致整数溢出
- Face 的参数范围是实际有效的裁剪范围

**实现**: 
```cpp
// 使用 BRepTools::UVBounds 而非 GeomAdaptor_Surface 的参数范围
Standard_Real u_min, u_max, v_min, v_max;
BRepTools::UVBounds(face, u_min, u_max, v_min, v_max);
surface->D0(u, v, pnt);  // 参数 -> 3D 点
```

### 3. 之字形路径生成
**问题**: 如何减少空行程？

**决策**: V 方向递增，U 方向奇偶行反向扫描

**原因**:
- 减少刀具抬起次数
- 保持路径连续性
- 符合常见的行切加工策略

### 4. STEP 数据传输
**问题**: 如何通过 gRPC 传输文件？

**决策**: 使用 `bytes` 类型传输完整文件内容

**原因**:
- 避免服务端文件系统依赖
- 支持远程计算场景
- 保持接口简洁

**实现**:
```python
with open(step_file, 'rb') as f:
    step_data = f.read()
request = SurfaceCalculationRequest(step_data=step_data, ...)
```

## 技术要点

### OpenCASCADE 集成
- **STEP 解析**: `STEPControl_Reader::ReadStream`
- **面积计算**: `BRepGProp::SurfaceProperties`
- **曲面提取**: `BRep_Tool::Surface`
- **参数求值**: `GeomAdaptor_Surface::Value(u, v)`

### 内存管理
- 保持与现有 API 一致：堆分配 + 配对释放
- `GenerateSurfaceToolpath` 分配，`FreeMockToolpath` 释放
- 避免跨模块内存管理问题

### 可视化增强
- 完整模型（灰色半透明）
- 最大面高亮（蓝色）
- 刀轨路径（红色）
- 清晰展示选择逻辑

## 文件修改清单

- `cam_service.proto` - 新增 `CalculateSurfaceToolpath` RPC
- `mock_cam/mock_cam.h` - 新增 `GenerateSurfaceToolpath` 接口
- `mock_cam/mock_cam.cpp` - 实现曲面刀轨算法
- `mock_cam/CMakeLists.txt` - 添加 OpenCASCADE 依赖
- `cpp_server/server.cpp` - 实现新 RPC 方法
- `python_client/client.py` - 支持 STEP 文件输入和双模式运行

## 使用示例

```bash
# 长方体模式（默认）
python client.py

# 曲面模式
python client.py model.step
```

## 未来优化方向

- 支持用户自定义 U/V 步长
- 支持多面并行计算
- 优化大文件传输（流式传输）
- 支持更复杂的刀轨策略（环切、螺旋等）
