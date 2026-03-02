"""测试坐标系显示功能"""

from OCC.Display.SimpleGui import init_display
from OCC.Core.AIS import AIS_Trihedron
from OCC.Core.gp import gp_Pnt, gp_Ax2, gp_Dir
from OCC.Core.Geom import Geom_Axis2Placement
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox

# 初始化显示
display, start_display, add_menu, add_function_to_menu = init_display()

# 创建一个简单的盒子作为参考
box = BRepPrimAPI_MakeBox(100, 100, 100).Shape()
display.DisplayShape(box, color='BLUE', transparency=0.5)

# 显示世界坐标系
origin = gp_Pnt(0, 0, 0)
z_dir = gp_Dir(0, 0, 1)
x_dir = gp_Dir(1, 0, 0)
ax2 = gp_Ax2(origin, z_dir, x_dir)
geom_axis = Geom_Axis2Placement(ax2)
world_cs = AIS_Trihedron(geom_axis)
world_cs.SetSize(80.0)
world_cs.SetTransparency(0.4)
display.Context.Display(world_cs, False)

# 显示自定义坐标系（偏移和旋转）
origin2 = gp_Pnt(50, 50, 50)
z_dir2 = gp_Dir(1, 1, 1)  # 倾斜的Z轴
x_dir2 = gp_Dir(1, -1, 0)  # 倾斜的X轴
ax2_2 = gp_Ax2(origin2, z_dir2, x_dir2)
geom_axis2 = Geom_Axis2Placement(ax2_2)
custom_cs = AIS_Trihedron(geom_axis2)
custom_cs.SetSize(100.0)
display.Context.Display(custom_cs, False)

display.FitAll()
print("✓ 坐标系显示测试")
print("  - 半透明坐标系：世界坐标系 (0,0,0)")
print("  - 不透明坐标系：自定义坐标系 (50,50,50)")
start_display()
