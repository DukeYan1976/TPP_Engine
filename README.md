# TPP_Engine - CAM 刀路计算系统

基于 gRPC 的跨语言 CAM 刀路计算原型系统。

## 项目结构

```
TPP_Engine/
├── cam_service.proto          # gRPC 服务定义
├── cam_service_pb2.py         # Protobuf 生成文件
├── cam_service_pb2_grpc.py    # gRPC 生成文件
├── cpp_server/                # C++ 服务端
├── mock_cam/                  # Mock 算法库
├── python_client/             # Python 客户端
│   ├── gui_client.py         # GUI 主程序
│   ├── cam_calculator.py     # 计算接口
│   ├── motion_script_generator.py  # 脚本生成器
│   └── client.py             # 命令行客户端
└── docs/                      # 文档
    └── 程序脚本设计和生产规范0.a.md
```

## 快速开始

### 1. 启动服务端
```bash
cd cpp_server/build
./cam_server
```

### 2. 启动GUI客户端
```bash
cd python_client
python gui_client.py
```

## 主要功能

- ✅ STEP 模型加载与显示
- ✅ 行切/环切刀路计算
- ✅ 3轴/3+轴模式支持
- ✅ 刀轴方向可视化
- ✅ 工件坐标系设置
- ✅ 运动脚本生成（MotorCortex MVP）

## 输出格式

### 运动脚本 (.py)
- 文件名：`ms_3ax_MMdd_HHmm.py` 或 `ms_5ax_MMdd_HHmm.py`
- 默认目录：`MotorCortex_MVP/scripts/CAMpaths/`
- 格式：MotorCortex MVP 可执行脚本

### 文本格式 (.txt)
- 文件名：`tp_3ax_MMdd_HHmm.txt` 或 `tp_5ax_MMdd_HHmm.txt`
- 格式：坐标和法线数据

## 技术栈

- **通信**：gRPC + Protobuf
- **服务端**：C++17, CMake
- **客户端**：Python 3.10+, PyQt5, PythonOCC
- **算法**：Mock DLL (C++)

## 核心约束

- 几何数据使用 `bytes` 传输（零拷贝）
- 禁止使用 Protobuf 对象数组
- 所有坐标数据使用 numpy 处理

## 参考文档

- [程序脚本设计和生产规范](docs/程序脚本设计和生产规范0.a.md)
- [架构规范](.kiro/steering/Rules.md)
