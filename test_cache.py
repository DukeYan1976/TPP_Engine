#!/usr/bin/env python3
"""测试模型缓存功能"""

import sys
sys.path.append('python_client')
from cam_calculator import CamCalculator

# 读取测试文件
with open('python_client/testparts/as1-oc-214.stp', 'rb') as f:
    step_data = f.read()

print(f"模型大小: {len(step_data)} bytes")

calculator = CamCalculator()
calculator.connect()

# 第一次计算 - 应该上传数据
print("\n=== 第一次计算（应该上传数据）===")
points1 = calculator.calculate_toolpath(
    step_data, 
    toolpath_mode=0, 
    num_paths=5, 
    step_u=1.0, 
    step_v=1.0,
    face_index=0
)
print(f"刀位点数: {len(points1)}")

# 第二次计算 - 应该使用缓存
print("\n=== 第二次计算（应该使用缓存）===")
points2 = calculator.calculate_toolpath(
    step_data, 
    toolpath_mode=0, 
    num_paths=10, 
    step_u=1.0, 
    step_v=1.0,
    face_index=0
)
print(f"刀位点数: {len(points2)}")

# 第三次计算 - 应该使用缓存
print("\n=== 第三次计算（应该使用缓存）===")
points3 = calculator.calculate_toolpath(
    step_data, 
    toolpath_mode=1, 
    num_paths=8, 
    step_u=1.0, 
    step_v=1.0,
    face_index=1
)
print(f"刀位点数: {len(points3)}")

calculator.close()
print("\n✓ 测试完成，请查看服务端日志确认缓存命中")
