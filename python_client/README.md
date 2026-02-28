# Python CAM Client

## 安装依赖

### 方法 1：使用 Conda（推荐）

`pythonocc-core` 在 Python 3.13 下需要通过 conda 安装：

```bash
conda install -c conda-forge pythonocc-core -y
pip install grpcio PyQt5
```

### 方法 2：使用兼容的 Python 版本

如果使用 pip，需要 Python 3.9-3.12：

```bash
pip install grpcio numpy pythonocc-core PyQt5
```

## 运行说明

### 1. 启动服务端

```bash
cd ../cpp_server/build
./cam_server
# 输入 exit 可退出服务
```

### 2. 运行客户端

**长方体模式**（默认）：
```bash
python client.py
```

**曲面模式**（STEP 文件）：
```bash
python client.py path/to/model.step
```

## 功能说明

### 长方体模式
- 生成 100x100x50 的长方体
- 提取 Bounding Box 并通过 gRPC 请求刀轨计算
- 显示灰色半透明长方体 + 红色"之"字形刀轨

### 曲面模式
- 读取 STEP 文件并解析所有面
- 自动选择面积最大的面
- 在该面上生成等距"之"字形刀轨（U/V 步长 5.0）
- 可视化显示：
  - 灰色半透明完整模型
  - 蓝色高亮最大面
  - 红色刀轨线条

## 数据传输

使用 `numpy.frombuffer` 零拷贝还原点集数据：
```python
vertices = np.frombuffer(response.raw_vertices, dtype=np.float64)
points = vertices.reshape((response.point_count, 3))
```

## 常见问题

### 1. pythonocc-core 安装失败
**错误**: `ERROR: No matching distribution found for pythonocc-core`

**原因**: pythonocc-core 不支持 Python 3.13，且 PyPI 上版本有限

**解决**: 使用 conda 安装（见上方方法 1）

### 2. 显示后端错误
**错误**: `incompatible backend_str specified: qt-pyqt5`

**原因**: PythonOCC 后端名称应为 `pyqt5` 而非 `qt-pyqt5`

**解决**: 代码已修正为 `init_display('pyqt5')`

### 3. macOS 段错误
**错误**: `zsh: segmentation fault python client.py`

**原因**: macOS 上默认显示后端不稳定

**解决**: 
- 安装 PyQt5: `pip install PyQt5`
- 使用 `pyqt5` 后端（代码已配置）

### 4. 弃用警告
**警告**: `DeprecationWarning: Call to deprecated function brepbndlib_Add`

**解决**: 代码已更新为 `brepbndlib.Add(box, bbox)`

## 依赖说明

- `grpcio`: gRPC Python 库
- `numpy`: 高效数组操作，用于 `frombuffer` 还原二进制数据
- `pythonocc-core`: OpenCASCADE Python 绑定，用于几何建模和可视化
- `PyQt5`: Qt5 显示后端，提供稳定的 3D 渲染窗口
