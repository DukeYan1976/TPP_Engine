# GUI客户端开发文档

**开发日期**: 2026-02-28  
**版本**: v1.0

---

## 概述

基于PyQt5和PythonOCC开发的图形化CAM刀轨计算客户端，提供交互式STEP文件加载、面选择和刀轨计算功能。

---

## 架构设计

### 文件结构

```
python_client/
├── gui_client.py          # Qt GUI主程序
├── cam_calculator.py      # gRPC调用封装
├── client.py              # 命令行客户端（保留）
├── start_gui.sh           # 启动脚本
└── README.md              # 使用说明
```

### 架构分层

```
┌─────────────────────────────────────┐
│  Qt GUI Layer (gui_client.py)      │
│  - 用户交互                         │
│  - 3D可视化                         │
│  - 参数控制                         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Business Logic (cam_calculator.py) │
│  - gRPC调用封装                     │
│  - 数据转换                         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  gRPC Communication                 │
│  - Protobuf序列化                   │
│  - bytes数据传输                    │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  C++ Server (cam_server)            │
│  - Mock CAM算法                     │
└─────────────────────────────────────┘
```

---

## 核心功能

### 1. STEP文件加载

**实现**: `load_step_file()`

- 使用Qt文件对话框选择文件
- STEPControl_Reader解析
- 提取所有面（TopExp_Explorer）
- 3D显示（半透明灰色）

### 2. 面选择

**实现**: `on_face_selected()`

- 注册OCC选择回调
- 自动选择最大面
- 高亮显示（蓝色半透明）
- 显示UV参数范围

### 3. 参数控制

**UI组件**:
- 刀路模式：QRadioButton（行切/环切）
- 起始方向：QRadioButton（U向/V向）
- 刀路数：QSlider（3-20）

**参数计算**:
```python
# 行切模式
if V向:
    step_v = (v_max - v_min) / (num_paths - 1)
    step_u = (u_max - u_min) / 20.0
else:  # U向
    step_u = (u_max - u_min) / (num_paths - 1)
    step_v = (v_max - v_min) / 20.0

# 环切模式
step_u = 1.0
step_v = 1.0
```

### 4. 后台计算

**实现**: `ToolpathWorker` (QThread)

- 避免UI冻结
- 异步gRPC调用
- 信号通知完成/错误

### 5. 刀轨显示

**实现**: `display_toolpath()`

- 点集转换为OCC边（BRepBuilderAPI_MakeEdge）
- 构建线框（BRepBuilderAPI_MakeWire）
- 绿色加粗显示（线宽3.0）

---

## 默认参数

```python
DEFAULT_PARAMS = {
    'toolpath_mode': 0,      # 0=行切, 1=环切
    'start_direction': 'V',  # V向（横向扫描）
    'num_paths': 10,         # 10条刀路
    'step_u': 0.05,          # U方向步长（自动计算）
    'step_v': None,          # V方向步长（自动计算）
}
```

---

## 关键技术点

### 1. OCC与Qt集成

```python
from OCC.Display.backend import load_backend
load_backend('pyqt5')
from OCC.Display.qtDisplay import qtViewer3d

# 创建3D视图
self.viewer = qtViewer3d(central_widget)
```

### 2. 面选择回调

```python
self.viewer._display.register_select_callback(self.on_face_selected)
```

### 3. 线程安全

- gRPC调用在QThread中执行
- 使用pyqtSignal传递结果
- UI更新在主线程

### 4. 内存管理

- numpy数组零拷贝（frombuffer）
- OCC对象自动管理
- gRPC channel正确关闭

---

## 对现有架构的影响

✅ **无影响**
- Protobuf定义：未修改
- C++ Server：未修改
- gRPC接口：未修改
- bytes传输：保持一致

✅ **仅扩展**
- 新增GUI客户端
- 封装gRPC调用
- 保留命令行客户端

---

## 测试建议

### 功能测试
1. 加载不同STEP文件
2. 选择不同大小的面
3. 测试所有参数组合
4. 验证刀轨显示正确性

### 边界测试
1. 极小/极大刀路数
2. 异常STEP文件
3. 服务器断开连接
4. 大文件加载性能

### 用户体验测试
1. 响应速度
2. 错误提示清晰度
3. 操作流畅性

---

## 已知限制

1. **面选择**: 当前自动选择最大面，未来可支持手动选择任意面
2. **参数预览**: 未实现参数修改后的实时预览
3. **刀轨编辑**: 不支持刀轨后处理编辑
4. **多面加工**: 不支持同时选择多个面

---

## 未来改进方向

1. 添加刀轨导出功能（G-code）
2. 支持多面批量计算
3. 参数预设保存/加载
4. 刀轨仿真动画
5. 加工时间估算
6. 碰撞检测可视化

---

## 依赖版本

- Python: 3.9-3.13
- PyQt5: 5.15+
- pythonocc-core: 7.7+
- grpcio: 1.50+
- numpy: 1.20+

---

## 启动方式

```bash
# 方式1：直接运行
cd python_client
python gui_client.py

# 方式2：使用启动脚本
./python_client/start_gui.sh
```

---

## 故障排查

### 问题1：无法连接gRPC服务器
**解决**: 确保C++ server在 localhost:50051 运行
```bash
cd cpp_server/build
./cam_server
```

### 问题2：STEP文件加载失败
**解决**: 检查文件格式是否为标准STEP（.stp/.step）

### 问题3：面选择无响应
**解决**: 确保已成功加载STEP文件，查看状态提示

### 问题4：刀轨计算超时
**解决**: 减少刀路数或增加步长，检查服务器日志
