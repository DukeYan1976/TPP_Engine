#!/usr/bin/env python3
"""测试脚本：验证已知bug"""

import grpc
import numpy as np
import sys
sys.path.append('..')

from cam_service_pb2 import SurfaceCalculationRequest
from cam_service_pb2_grpc import CamCalculationServiceStub

def test_contour_shrink_bug():
    """Bug: 环切模式收缩步长计算错误
    
    问题：当UV参数范围差异很大时（如U=[0,1], V=[0,80]），
    使用min_range会导致收缩不均匀
    """
    print("=" * 60)
    print("测试 Bug #1: 环切模式收缩步长计算")
    print("=" * 60)
    
    # 模拟参数
    u_min, u_max = 0.0, 1.0
    v_min, v_max = 0.0, 80.0
    num_paths = 5
    
    u_range = u_max - u_min  # 1.0
    v_range = v_max - v_min  # 80.0
    min_range = min(u_range, v_range)  # 1.0
    
    shrink_step = min_range / (2.0 * (num_paths + 1))
    
    print(f"UV范围: U=[{u_min}, {u_max}], V=[{v_min}, {v_max}]")
    print(f"U范围: {u_range}, V范围: {v_range}")
    print(f"min_range: {min_range}")
    print(f"shrink_step: {shrink_step:.6f}")
    print()
    
    print("各层收缩后的边界:")
    for layer in range(num_paths):
        shrink = layer * shrink_step
        u0 = u_min + shrink
        u1 = u_max - shrink
        v0 = v_min + shrink
        v1 = v_max - shrink
        
        print(f"  Layer {layer}: U=[{u0:.4f}, {u1:.4f}], V=[{v0:.4f}, {v1:.4f}]")
        
        # 检查问题
        if u1 <= u0:
            print(f"    ❌ BUG: U方向已收缩到零或负值!")
        if v1 <= v0:
            print(f"    ❌ BUG: V方向已收缩到零或负值!")
    
    print()
    print("问题分析:")
    print("  使用min_range作为收缩基准会导致:")
    print("  - U方向(范围小)收缩过快，可能提前到零")
    print("  - V方向(范围大)收缩太慢，浪费空间")
    print()
    print("建议修复:")
    print("  应该分别计算U和V的收缩步长:")
    print(f"    shrink_step_u = {u_range / (2.0 * (num_paths + 1)):.6f}")
    print(f"    shrink_step_v = {v_range / (2.0 * (num_paths + 1)):.6f}")
    print()

def test_raster_boundary_bug():
    """Bug: 行切模式边界处理
    
    问题：当计算的u或v超过max时，会被限制为max，
    导致最后一行/列可能有重复点
    """
    print("=" * 60)
    print("测试 Bug #2: 行切模式边界重复点")
    print("=" * 60)
    
    u_min, u_max = 0.0, 1.0
    v_min, v_max = 0.0, 1.0
    step_u = 0.15
    step_v = 0.15
    
    u_steps = int((u_max - u_min) / step_u) + 1
    v_steps = int((v_max - v_min) / step_v) + 1
    
    print(f"UV范围: U=[{u_min}, {u_max}], V=[{v_min}, {v_max}]")
    print(f"步长: step_u={step_u}, step_v={step_v}")
    print(f"计算步数: u_steps={u_steps}, v_steps={v_steps}")
    print()
    
    print("U方向采样点:")
    u_values = []
    for j in range(u_steps):
        u = u_min + j * step_u
        if u > u_max:
            u = u_max
        u_values.append(u)
        print(f"  j={j}: u={u:.4f}")
    
    # 检查重复
    if len(u_values) != len(set(u_values)):
        print("  ❌ BUG: 发现重复的U值!")
    
    print()
    print("问题分析:")
    print(f"  最后一个点: u = {u_min} + {u_steps-1} * {step_u} = {u_min + (u_steps-1) * step_u:.4f}")
    print(f"  超过u_max({u_max})，被限制为{u_max}")
    print(f"  如果前面已有u={u_max}的点，就会重复")
    print()
    print("建议修复:")
    print("  使用 min(u, u_max) 并检查是否已达到边界")
    print()

def test_grpc_connection():
    """测试gRPC连接和错误处理"""
    print("=" * 60)
    print("测试 Bug #3: gRPC连接错误处理")
    print("=" * 60)
    
    try:
        # 尝试连接到不存在的服务器
        channel = grpc.insecure_channel('localhost:50052')  # 错误端口
        stub = CamCalculationServiceStub(channel)
        
        request = SurfaceCalculationRequest(
            step_data=b"dummy",
            step_u=0.1,
            step_v=0.1,
            toolpath_mode=0,
            num_paths=5
        )
        
        # 设置超时
        response = stub.CalculateSurfaceToolpath(request, timeout=2.0)
        print("  ✓ 连接成功")
        
    except grpc.RpcError as e:
        print(f"  ❌ gRPC错误: {e.code()}")
        print(f"     详情: {e.details()}")
        print()
        print("问题: Python客户端缺少错误处理")
        print("建议: 添加try-except捕获grpc.RpcError")
    except Exception as e:
        print(f"  ❌ 其他错误: {e}")
    
    print()

if __name__ == '__main__':
    test_contour_shrink_bug()
    test_raster_boundary_bug()
    test_grpc_connection()
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
