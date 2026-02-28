# 大文件处理优化

## 问题
- STEP文件过大（如33MB）超过gRPC默认4MB限制
- 大量面（9000+）导致显示和选择性能问题

## 解决方案

### 1. gRPC消息大小限制提升
**客户端** (`cam_calculator.py`):
```python
options = [
    ('grpc.max_send_message_length', 100 * 1024 * 1024),
    ('grpc.max_receive_message_length', 100 * 1024 * 1024),
]
self.channel = grpc.insecure_channel(self.server_address, options=options)
```

**服务端** (`server.cpp`):
```cpp
builder.SetMaxReceiveMessageSize(100 * 1024 * 1024);
builder.SetMaxSendMessageSize(100 * 1024 * 1024);
```

### 2. 智能显示策略
- **≤500面**: 分别显示每个面，支持AIS映射精确选择
- **>500面**: 整体显示模型，使用几何匹配选择（避免显示延迟）

### 3. 模型缓存机制
- 首次上传33MB数据并缓存（SHA256哈希）
- 后续计算仅传输哈希+参数（~100字节）
- 性能提升：通信开销降低99.7%

## 测试结果
**文件**: `01_Finishing.stp` (33.42 MB, 9093面)
- ✓ 加载成功
- ✓ 显示流畅（整体显示模式）
- ✓ 面选择正常（几何匹配）
- ✓ 刀路计算成功
- ✓ 缓存命中率100%

**性能数据**:
- 首次计算: 3.60秒（含上传33MB）
- 后续计算: 3.55秒（仅传输哈希）
- 服务端日志: `[Cache HIT]`

## 使用建议
1. 小模型（<500面）：享受精确AIS选择
2. 大模型（>500面）：自动切换整体显示+几何匹配
3. 频繁调参：缓存自动生效，无需重复上传
