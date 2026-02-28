"""CAM计算gRPC调用封装"""

import grpc
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from cam_service_pb2 import SurfaceCalculationRequest
from cam_service_pb2_grpc import CamCalculationServiceStub

class CamCalculator:
    def __init__(self, server_address='localhost:50051'):
        self.server_address = server_address
        self.channel = None
        self.stub = None
    
    def connect(self):
        """连接到gRPC服务器"""
        try:
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = CamCalculationServiceStub(self.channel)
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to server: {e}")
    
    def calculate_toolpath(self, step_data, toolpath_mode, num_paths, step_u, step_v, start_direction=1):
        """
        计算刀轨
        
        Args:
            step_data: STEP文件二进制数据
            toolpath_mode: 0=行切, 1=环切
            num_paths: 刀路数量
            step_u: U方向步长
            step_v: V方向步长
            start_direction: 0=U向, 1=V向 (默认V向)
            
        Returns:
            numpy array of shape (N, 3) - 刀轨点坐标
        """
        if not self.stub:
            raise RuntimeError("Not connected to server. Call connect() first.")
        
        request = SurfaceCalculationRequest(
            step_data=step_data,
            step_u=step_u,
            step_v=step_v,
            toolpath_mode=toolpath_mode,
            num_paths=num_paths,
            start_direction=start_direction
        )
        
        try:
            response = self.stub.CalculateSurfaceToolpath(request, timeout=10.0)
            vertices = np.frombuffer(response.raw_vertices, dtype=np.float64)
            points = vertices.reshape((response.point_count, 3))
            return points
        except grpc.RpcError as e:
            raise RuntimeError(f"gRPC Error: {e.code()} - {e.details()}")
    
    def close(self):
        """关闭连接"""
        if self.channel:
            self.channel.close()
