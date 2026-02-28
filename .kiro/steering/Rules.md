# 核心架构规范 (CAM gRPC 原型系统)

## 1. 项目背景与技术栈
本项目是一个跨语言、分布式的 CAM 计算架构原型。底层 C++ 核心算法被封装为微服务，前端使用 Python 进行轻量化交互与展示。
* **通信框架**：gRPC + Protocol Buffers (Protobuf 3)
* **服务端**：Modern C++ (推荐 C++17), CMake
* **算法核心**：C++ 动态链接库 (Mock DLL / SO)
* **客户端**：Python 3.10+, numpy, pythonocc-core

## 2. 核心约束：gRPC 几何数据传输优化（绝对强制）
由于 CAM 领域（如精确的 B-Rep 拓扑或离散网格、刀轨点集）数据量巨大，Protobuf 处理海量对象数组时存在严重的序列化/反序列化性能瓶颈。
* **禁止使用对象数组**：在 `.proto` 文件中，**绝对禁止**使用 `repeated Point3d` 等结构体数组来传输坐标集。
* **强制使用原生 bytes**：所有的几何输入数据和计算输出的刀轨点集序列（XYZ连续排列），必须在 Protobuf 中定义为 `bytes` 字段（例如 `bytes raw_vertices`）。配合 `int32 point_count` 标明点的数量。

## 3. C++ 端开发规范 (Server & Mock DLL)
* **Mock DLL 接口定义**：必须使用 `extern "C"` 导出纯 C 接口，以便 gRPC 服务端动态或静态加载。
    * 签名示例：`void GenerateMockToolpath(double x_min, double x_max, double y_min, double y_max, double z_max, double** out_points, int* out_count)`
* **Zero-copy 解析（零拷贝）**：C++ gRPC 服务端在接收到 `bytes` 数据后，不要进行逐点反序列化，而是直接将 `bytes` 对应的内存空间（如 `string::data()`）强转为 `double*` 或 `float*`，直接传递给计算逻辑。
* **内存管理**：将 DLL 计算返回的 `double*` 数组封装回 Protobuf 的 `bytes` 响应时，务必通过内存拷贝（如 `set_raw_vertices(const void* data, size_t size)`）完成，并确保正确释放 DLL 中 `new/malloc` 分配的内存，防止内存泄漏。

## 4. Python 端开发规范 (Client)
* **序列化与反序列化**：必须使用 `numpy` 库处理几何与刀轨数据。
    * 发送前：将坐标数组转换为特定数据类型的 numpy 数组（如 `np.float64`），然后强制使用 `numpy_array.tobytes()` 转换为原生字节流。
    * 接收后：收到服务端的 `bytes` 响应后，强制使用 `np.frombuffer(response.raw_vertices, dtype=np.float64)` 将其还原为可操作的浮点数组，再交由 PythonOCC 进行渲染。
* **代码风格**：保持极简，核心目标是验证跨语言的二进制数据传递闭环与 3D 渲染，不需要过度封装 GUI。