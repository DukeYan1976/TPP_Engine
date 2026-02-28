# Mock CAM Library

C++ 动态链接库，模拟底层 CAM 刀轨计算 API。

## 功能

提供纯 C 接口，生成简单的"之"字形（Zig-Zag）三维刀轨点阵：

```c
// 生成刀轨点集
void GenerateMockToolpath(
    double x_min, double x_max, 
    double y_min, double y_max, 
    double z_max,
    double** out_points,  // 输出：连续的 X,Y,Z 坐标数组
    int* out_count        // 输出：点数量
);

// 释放内存
void FreeMockToolpath(double* points);
```

## 实现细节

- 生成 10x10 点阵（共 100 个点）
- 奇数行从左到右，偶数行从右到左，形成"之"字形路径
- 内存在堆上动态分配为连续的 `double` 数组（X, Y, Z 交替排列）
- 提供独立的内存释放接口，避免跨模块内存管理问题

## 编译

```bash
mkdir build && cd build
cmake ..
make
```

**输出：**
- macOS: `libmock_cam.dylib`
- Linux: `libmock_cam.so`
- Windows: `mock_cam.dll`

## 使用示例

```cpp
#include "mock_cam.h"

double* points = nullptr;
int count = 0;

GenerateMockToolpath(0, 100, 0, 100, 50, &points, &count);

// 使用 points[0], points[1], points[2] 为第一个点的 X, Y, Z
// ...

FreeMockToolpath(points);
```

## 跨平台支持

- Windows: 使用 `__declspec(dllexport/dllimport)`
- Unix/macOS: 使用 `__attribute__((visibility("default")))`
- CMake 自动处理平台差异
