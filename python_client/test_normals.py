#!/usr/bin/env python3
"""快速测试脚本 - 验证法线数据传输"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from cam_calculator import CamCalculator
import numpy as np

def test_toolpath_with_normals():
    """测试刀路计算是否返回法线"""
    print("=== 测试刀路计算（带法线） ===\n")
    
    # 连接服务器
    calc = CamCalculator()
    try:
        calc.connect()
        print("✓ 已连接到服务器\n")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return False
    
    # 读取测试文件
    test_file = os.path.join(os.path.dirname(__file__), 
                             "testparts", "BsplineSurface01.stp")
    
    if not os.path.exists(test_file):
        print(f"✗ 测试文件不存在: {test_file}")
        return False
    
    with open(test_file, 'rb') as f:
        step_data = f.read()
    
    print(f"✓ 已加载测试文件: {len(step_data)} bytes\n")
    
    # 计算刀路
    try:
        print("计算刀路中...")
        points, normals = calc.calculate_toolpath(
            step_data,
            toolpath_mode=0,  # 行切
            num_paths=5,
            step_u=0.1,
            step_v=0.1,
            start_direction=1,  # V向
            face_index=-1
        )
        
        print(f"✓ 刀路计算完成\n")
        print(f"  点数: {len(points)}")
        print(f"  法线数: {len(normals)}")
        print(f"  点数组形状: {points.shape}")
        print(f"  法线数组形状: {normals.shape}\n")
        
        # 验证法线
        print("验证法线数据:")
        print(f"  前3个点:")
        for i in range(min(3, len(points))):
            p = points[i]
            n = normals[i]
            n_len = np.linalg.norm(n)
            print(f"    点{i}: ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})")
            print(f"    法线: ({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f}) 长度={n_len:.6f}")
        
        # 检查所有法线是否为单位向量
        norms = np.linalg.norm(normals, axis=1)
        min_norm = norms.min()
        max_norm = norms.max()
        avg_norm = norms.mean()
        
        print(f"\n  法线长度统计:")
        print(f"    最小: {min_norm:.6f}")
        print(f"    最大: {max_norm:.6f}")
        print(f"    平均: {avg_norm:.6f}")
        
        if abs(avg_norm - 1.0) < 0.01:
            print("  ✓ 法线已归一化")
        else:
            print("  ✗ 警告: 法线未正确归一化")
        
        # 测试输出格式
        print("\n模拟输出格式:")
        print("X Y Z Nx Ny Nz")
        for i in range(min(3, len(points))):
            p = points[i]
            n = normals[i]
            print(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
        
        print("\n✓ 测试通过")
        return True
        
    except Exception as e:
        print(f"✗ 计算失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        calc.close()

if __name__ == '__main__':
    success = test_toolpath_with_normals()
    sys.exit(0 if success else 1)
