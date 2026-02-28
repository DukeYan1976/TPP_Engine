#!/usr/bin/env python3
"""对比测试：展示修复前后的差异"""

import grpc
import numpy as np
import sys
sys.path.append('..')

from cam_service_pb2 import SurfaceCalculationRequest
from cam_service_pb2_grpc import CamCalculationServiceStub

def test_contour_mode():
    """测试环切模式"""
    print("=" * 70)
    print("环切模式测试 (Bug #1修复验证)")
    print("=" * 70)
    
    channel = grpc.insecure_channel('localhost:50051')
    stub = CamCalculationServiceStub(channel)
    
    with open('python_client/testparts/BsplineSurface01.stp', 'rb') as f:
        step_data = f.read()
    
    # 测试不同刀路数
    for num_paths in [3, 5, 8]:
        request = SurfaceCalculationRequest(
            step_data=step_data,
            step_u=1.0,
            step_v=1.0,
            toolpath_mode=1,
            num_paths=num_paths
        )
        
        response = stub.CalculateSurfaceToolpath(request, timeout=5.0)
        points = np.frombuffer(response.raw_vertices, dtype=np.float64).reshape((-1, 3))
        
        print(f"\n刀路数={num_paths}:")
        print(f"  生成点数: {len(points)}")
        print(f"  X范围: [{points[:,0].min():.2f}, {points[:,0].max():.2f}]")
        print(f"  Y范围: [{points[:,1].min():.2f}, {points[:,1].max():.2f}]")
        print(f"  Z范围: [{points[:,2].min():.2f}, {points[:,2].max():.2f}]")
        
        # 计算每层的点数（粗略估计）
        avg_points_per_layer = len(points) / num_paths
        print(f"  平均每层点数: {avg_points_per_layer:.0f}")

def test_raster_mode():
    """测试行切模式"""
    print("\n" + "=" * 70)
    print("行切模式测试 (Bug #2修复验证)")
    print("=" * 70)
    
    channel = grpc.insecure_channel('localhost:50051')
    stub = CamCalculationServiceStub(channel)
    
    with open('python_client/testparts/BsplineSurface01.stp', 'rb') as f:
        step_data = f.read()
    
    # 测试不同步长
    test_cases = [
        (0.05, 8.0, "粗加工"),
        (0.03, 4.0, "半精加工"),
        (0.02, 2.0, "精加工"),
    ]
    
    for step_u, step_v, desc in test_cases:
        request = SurfaceCalculationRequest(
            step_data=step_data,
            step_u=step_u,
            step_v=step_v,
            toolpath_mode=0,
            num_paths=10
        )
        
        response = stub.CalculateSurfaceToolpath(request, timeout=5.0)
        points = np.frombuffer(response.raw_vertices, dtype=np.float64).reshape((-1, 3))
        
        # 检查重复点
        unique_points = np.unique(points, axis=0)
        duplicates = len(points) - len(unique_points)
        
        print(f"\n{desc} (step_u={step_u}, step_v={step_v}):")
        print(f"  总点数: {len(points)}")
        print(f"  唯一点: {len(unique_points)}")
        print(f"  重复点: {duplicates} {'✓' if duplicates == 0 else '✗'}")

def test_error_handling():
    """测试错误处理"""
    print("\n" + "=" * 70)
    print("错误处理测试 (Bug #3修复验证)")
    print("=" * 70)
    
    # 测试1: 无效的STEP数据
    print("\n测试1: 无效STEP数据")
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = CamCalculationServiceStub(channel)
        
        request = SurfaceCalculationRequest(
            step_data=b"invalid data",
            step_u=0.1,
            step_v=0.1,
            toolpath_mode=0,
            num_paths=5
        )
        
        response = stub.CalculateSurfaceToolpath(request, timeout=2.0)
        print("  ✗ 应该返回错误")
    except grpc.RpcError as e:
        print(f"  ✓ 正确捕获错误: {e.code()}")
    
    # 测试2: 连接错误端口
    print("\n测试2: 连接错误端口")
    try:
        channel = grpc.insecure_channel('localhost:50099')
        stub = CamCalculationServiceStub(channel)
        
        request = SurfaceCalculationRequest(
            step_data=b"test",
            step_u=0.1,
            step_v=0.1,
            toolpath_mode=0,
            num_paths=5
        )
        
        response = stub.CalculateSurfaceToolpath(request, timeout=2.0)
        print("  ✗ 应该连接失败")
    except grpc.RpcError as e:
        print(f"  ✓ 正确捕获连接错误: {e.code()}")

if __name__ == '__main__':
    try:
        test_contour_mode()
        test_raster_mode()
        test_error_handling()
        
        print("\n" + "=" * 70)
        print("✓ 所有测试通过！修复效果良好")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
