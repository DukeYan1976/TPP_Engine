import grpc
import numpy as np
import sys
import os
sys.path.append('..')

from cam_service_pb2 import CalculationRequest, SurfaceCalculationRequest
from cam_service_pb2_grpc import CamCalculationServiceStub

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCC.Core.gp import gp_Pnt
from OCC.Display.SimpleGui import init_display
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import topods
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps

def calculate_box_toolpath(stub, num_paths=10, toolpath_mode=0):
    """长方体刀轨计算 - 使用曲面模式"""
    from OCC.Core.STEPControl import STEPControl_Writer
    import tempfile
    
    box = BRepPrimAPI_MakeBox(100, 100, 50).Shape()
    
    # 导出为临时STEP文件
    temp_step = tempfile.mktemp(suffix='.stp')
    writer = STEPControl_Writer()
    writer.Transfer(box, 0)
    writer.Write(temp_step)
    
    # 使用曲面刀轨计算
    with open(temp_step, 'rb') as f:
        step_data = f.read()
    
    # 读取box用于可视化
    reader = STEPControl_Reader()
    reader.ReadFile(temp_step)
    reader.TransferRoots()
    shape = reader.OneShape()
    
    # 查找最大面
    max_area = 0.0
    largest_face = None
    
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        props = GProp_GProps()
        brepgprop.SurfaceProperties(face, props)
        area = props.Mass()
        
        if area > max_area:
            max_area = area
            largest_face = face
        
        explorer.Next()
    
    print(f"Box: Found largest face with area: {max_area:.2f}")
    
    # 获取参数范围
    from OCC.Core.BRepTools import breptools
    u_min, u_max, v_min, v_max = breptools.UVBounds(largest_face)
    
    # 计算步长
    if toolpath_mode == 0:
        step_v = (v_max - v_min) / (num_paths - 1) if num_paths > 1 else (v_max - v_min)
        step_u = (u_max - u_min) / 20.0
    else:
        step_u = 1.0
        step_v = 1.0
    
    print(f"Toolpath mode: {'Contour' if toolpath_mode == 1 else 'Raster'}")
    
    # 调用 gRPC 服务
    request = SurfaceCalculationRequest(
        step_data=step_data,
        step_u=step_u,
        step_v=step_v,
        toolpath_mode=toolpath_mode,
        num_paths=num_paths
    )
    
    response = stub.CalculateSurfaceToolpath(request)
    vertices = np.frombuffer(response.raw_vertices, dtype=np.float64)
    points = vertices.reshape((response.point_count, 3))
    
    print(f"Received {response.point_count} points")
    
    # 清理临时文件
    import os
    os.remove(temp_step)
    
    return box, largest_face, points

def calculate_surface_toolpath(stub, step_file, num_paths=10, toolpath_mode=0):
    """曲面刀轨计算
    
    Args:
        toolpath_mode: 0=行切, 1=环切
    """
    with open(step_file, 'rb') as f:
        step_data = f.read()
    
    # 读取 STEP 文件用于可视化
    reader = STEPControl_Reader()
    if reader.ReadFile(step_file) != IFSelect_RetDone:
        print(f"Failed to read STEP file: {step_file}")
        return None, None, None
    
    reader.TransferRoots()
    shape = reader.OneShape()
    
    # 查找最大面
    max_area = 0.0
    largest_face = None
    
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        props = GProp_GProps()
        brepgprop.SurfaceProperties(face, props)
        area = props.Mass()
        
        if area > max_area:
            max_area = area
            largest_face = face
        
        explorer.Next()
    
    print(f"Found largest face with area: {max_area:.2f}")
    
    # 获取面的参数范围以计算步长
    from OCC.Core.BRepTools import breptools
    u_min, u_max, v_min, v_max = breptools.UVBounds(largest_face)
    
    print(f"UV bounds: U[{u_min:.4f}, {u_max:.4f}], V[{v_min:.4f}, {v_max:.4f}]")
    
    # 计算步长
    if toolpath_mode == 0:
        # 行切模式
        step_v = (v_max - v_min) / (num_paths - 1) if num_paths > 1 else (v_max - v_min)
        step_u = (u_max - u_min) / 20.0
    else:
        # 环切模式：步长参数在C++端计算
        step_u = 1.0
        step_v = 1.0
    
    print(f"Step sizes: U={step_u:.4f}, V={step_v:.4f}")
    print(f"Toolpath mode: {'Contour' if toolpath_mode == 1 else 'Raster'}")
    
    # 调用 gRPC 服务
    request = SurfaceCalculationRequest(
        step_data=step_data,
        step_u=step_u,
        step_v=step_v,
        toolpath_mode=toolpath_mode,
        num_paths=num_paths
    )
    
    response = stub.CalculateSurfaceToolpath(request)
    vertices = np.frombuffer(response.raw_vertices, dtype=np.float64)
    points = vertices.reshape((response.point_count, 3))
    
    print(f"Received {response.point_count} points")
    
    return shape, largest_face, points

def visualize(shape, toolpath_points, highlight_face=None):
    """可视化几何和刀轨"""
    print(f"Visualizing {len(toolpath_points)} toolpath points...")
    
    # 计算相邻点距离，检测环边界（距离跳变处）
    diffs = np.diff(toolpath_points, axis=0)
    dists = np.sqrt(np.sum(diffs**2, axis=1))
    median_dist = np.median(dists[dists > 1e-9]) if np.any(dists > 1e-9) else 1.0
    threshold = median_dist * 5.0
    
    edges = []
    for i in range(len(toolpath_points) - 1):
        if dists[i] < 1e-9 or dists[i] > threshold:
            continue  # 跳过重合点和环间跳变
        p1 = toolpath_points[i]
        p2 = toolpath_points[i + 1]
        edge = BRepBuilderAPI_MakeEdge(
            gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2])),
            gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2]))
        ).Edge()
        edges.append(edge)
    
    print("Building wire...")
    wire_builder = BRepBuilderAPI_MakeWire()
    for edge in edges:
        wire_builder.Add(edge)
    toolpath_wire = wire_builder.Wire()
    
    print("Initializing display...")
    display, start_display, add_menu, add_function_to_menu = init_display('pyqt5')
    
    # 显示主体（半透明灰色）
    display.DisplayShape(shape, color=Quantity_Color(0.7, 0.7, 0.7, Quantity_TOC_RGB), 
                        transparency=0.7, update=False)
    
    # 高亮最大面（蓝色边框）
    if highlight_face:
        display.DisplayShape(highlight_face, color=Quantity_Color(0.2, 0.5, 1.0, Quantity_TOC_RGB),
                           transparency=0.5, update=False)
    
    print("Displaying toolpath...")
    # 显示刀轨（加粗绿色）
    from OCC.Core.AIS import AIS_Shape
    from OCC.Core.Prs3d import Prs3d_LineAspect
    from OCC.Core.Aspect import Aspect_TOL_SOLID
    
    ais_toolpath = AIS_Shape(toolpath_wire)
    ais_toolpath.SetColor(Quantity_Color(0.0, 0.8, 0.0, Quantity_TOC_RGB))
    
    # 设置线宽
    drawer = ais_toolpath.Attributes()
    line_aspect = Prs3d_LineAspect(Quantity_Color(0.0, 0.8, 0.0, Quantity_TOC_RGB), Aspect_TOL_SOLID, 3.0)
    drawer.SetWireAspect(line_aspect)
    ais_toolpath.SetAttributes(drawer)
    
    display.Context.Display(ais_toolpath, False)
    
    display.FitAll()
    display.View.SetBackgroundColor(Quantity_Color(0.95, 0.95, 0.95, Quantity_TOC_RGB))
    
    print("Press 'q' or close window to exit")
    start_display()

def main():
    try:
        channel = grpc.insecure_channel('localhost:50051')
        stub = CamCalculationServiceStub(channel)
    except Exception as e:
        print(f"Error: Failed to create gRPC channel: {e}")
        return
    
    # 解析参数
    num_paths = 10
    toolpath_mode = 0  # 0=行切, 1=环切
    step_file = None
    
    # 检查是否有STEP文件参数
    for arg in sys.argv[1:]:
        if arg.endswith('.stp') or arg.endswith('.step'):
            step_file = arg
            break
    
    # 解析模式参数
    for arg in sys.argv[1:]:
        if arg in ['contour', 'c', '1']:
            toolpath_mode = 1
        elif arg in ['raster', 'r', '0']:
            toolpath_mode = 0
        elif arg.isdigit():
            num_paths = int(arg)
    
    if step_file:
        # 曲面模式
        if not os.path.exists(step_file):
            print(f"Error: File not found: {step_file}")
            return
        
        print(f"Processing STEP file: {step_file}")
        try:
            shape, largest_face, points = calculate_surface_toolpath(stub, step_file, num_paths, toolpath_mode)
        except grpc.RpcError as e:
            print(f"gRPC Error: {e.code()} - {e.details()}")
            return
        except Exception as e:
            print(f"Error: {e}")
            return
        
        if shape is None:
            return
        
        visualize(shape, points, largest_face)
    else:
        # 长方体模式
        print("No STEP file provided, using default box geometry")
        try:
            box, largest_face, points = calculate_box_toolpath(stub, num_paths, toolpath_mode)
        except grpc.RpcError as e:
            print(f"gRPC Error: {e.code()} - {e.details()}")
            return
        except Exception as e:
            print(f"Error: {e}")
            return
        
        visualize(box, points, largest_face)

if __name__ == '__main__':
    main()
