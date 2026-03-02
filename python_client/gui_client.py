"""CAM刀轨计算 - Qt GUI客户端"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QRadioButton, QButtonGroup, QSlider, QMessageBox,
                             QGroupBox, QProgressBar, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime

from OCC.Display.backend import load_backend
load_backend('pyqt5')
from OCC.Display.qtDisplay import qtViewer3d

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_VERTEX
from OCC.Core.TopoDS import topods, TopoDS_Compound
from OCC.Core.BRep import BRep_Builder, BRep_Tool
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepTools import breptools
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.AIS import AIS_Shape, AIS_Trihedron
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCC.Core.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Trsf
from OCC.Core.Geom import Geom_Axis2Placement
from OCC.Core.Prs3d import Prs3d_LineAspect, Prs3d_Drawer
from OCC.Core.Aspect import Aspect_TOL_SOLID
from OCC.Core.V3d import V3d_DirectionalLight, V3d_AmbientLight, V3d_TypeOfLight
from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial

from cam_calculator import CamCalculator
from motion_script_generator import generate_motion_script
import numpy as np

class ToolpathWorker(QThread):
    """后台线程执行刀轨计算"""
    finished = pyqtSignal(np.ndarray, np.ndarray)  # (points, normals)
    error = pyqtSignal(str)
    
    def __init__(self, calculator, step_data, params, face_index):
        super().__init__()
        self.calculator = calculator
        self.step_data = step_data
        self.params = params
        self.face_index = face_index
    
    def run(self):
        try:
            points, normals = self.calculator.calculate_toolpath(
                self.step_data,
                self.params['toolpath_mode'],
                self.params['num_paths'],
                self.params['step_u'],
                self.params['step_v'],
                self.params['start_direction'],
                self.face_index
            )
            self.finished.emit(points, normals)
        except Exception as e:
            self.error.emit(str(e))


class CamGuiClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAM Toolpath Calculator")
        self.setGeometry(100, 100, 1200, 800)
        
        # 数据
        self.step_file_path = None
        self.step_data = None  # 缓存文件数据，避免重复读取
        self.shape = None
        self.faces = []
        self.selected_face = None
        self.selected_face_index = -1  # 记录选中面的索引
        self.selected_face_ais = None
        self.toolpath_points = None
        self.toolpath_normals = None  # 刀轨法线
        self.toolpath_ais = None  # 保存刀轨AIS对象用于删除
        self.normals_ais = None  # 法线可视化对象
        self.show_normals = True  # 默认显示刀轴
        self.calculator = CamCalculator()
        self.worker = None  # 后台计算线程
        self._callback_registered = False  # 回调是否已注册
        
        # 工件坐标系
        self.wcs_mode = 0  # 0=世界坐标系, 1=自定义
        self.wcs_transform = np.eye(4)  # 4x4变换矩阵
        self.wcs_ais = None  # 自定义坐标系可视化
        self.world_cs_ais = None  # 世界坐标系可视化（固定参考）
        self.wcs_picking_step = 0  # 三点拾取步骤 (0=未开始, 1-3=拾取中)
        self.wcs_points = []  # 拾取的三个点
        self.wcs_adjusting = False  # 是否处于调整模式
        
        # 连接服务器
        try:
            self.calculator.connect()
        except Exception as e:
            QMessageBox.critical(self, "连接错误", f"无法连接到gRPC服务器:\n{e}")
        
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # 左侧：3D显示区
        self.viewer = qtViewer3d(central_widget)
        main_layout.addWidget(self.viewer, stretch=3)
        
        # 右侧：控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(8)  # 减小间距
        control_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        control_panel.setMaximumWidth(280)  # 减小宽度
        
        # 文件选择
        file_group = QGroupBox("STEP文件")
        file_layout = QVBoxLayout()
        file_layout.setSpacing(4)
        self.file_label = QLabel("未选择文件")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet("QLabel { font-size: 10px; }")
        btn_load = QPushButton("选择文件")
        btn_load.setMaximumHeight(28)
        btn_load.clicked.connect(self.load_step_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(btn_load)
        file_group.setLayout(file_layout)
        control_layout.addWidget(file_group)
        
        # 面选择提示
        face_group = QGroupBox("面选择")
        face_layout = QVBoxLayout()
        face_layout.setSpacing(4)
        self.face_label = QLabel("点击3D视图选择面")
        self.face_label.setWordWrap(True)
        self.face_label.setStyleSheet("QLabel { font-size: 10px; }")
        face_layout.addWidget(self.face_label)
        face_group.setLayout(face_layout)
        control_layout.addWidget(face_group)
        
        # 刀轨参数
        param_group = QGroupBox("刀轨参数")
        param_layout = QVBoxLayout()
        param_layout.setSpacing(4)
        
        # 轴数选择（水平布局）
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel("轴数:"))
        self.axis_group = QButtonGroup()
        self.radio_3axis = QRadioButton("3轴")
        self.radio_multi_axis = QRadioButton("3+轴")
        self.radio_multi_axis.setChecked(True)
        self.axis_group.addButton(self.radio_3axis, 3)
        self.axis_group.addButton(self.radio_multi_axis, 5)
        axis_layout.addWidget(self.radio_3axis)
        axis_layout.addWidget(self.radio_multi_axis)
        axis_layout.addStretch()
        param_layout.addLayout(axis_layout)
        
        # 刀路模式（水平布局）
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("模式:"))
        self.mode_group = QButtonGroup()
        self.radio_raster = QRadioButton("行切")
        self.radio_contour = QRadioButton("环切")
        self.radio_raster.setChecked(True)
        self.mode_group.addButton(self.radio_raster, 0)
        self.mode_group.addButton(self.radio_contour, 1)
        mode_layout.addWidget(self.radio_raster)
        mode_layout.addWidget(self.radio_contour)
        mode_layout.addStretch()
        param_layout.addLayout(mode_layout)
        
        # 起始方向（水平布局）
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("方向:"))
        self.dir_group = QButtonGroup()
        self.radio_u = QRadioButton("U向")
        self.radio_v = QRadioButton("V向")
        self.radio_v.setChecked(True)
        self.dir_group.addButton(self.radio_u, 0)
        self.dir_group.addButton(self.radio_v, 1)
        dir_layout.addWidget(self.radio_u)
        dir_layout.addWidget(self.radio_v)
        dir_layout.addStretch()
        param_layout.addLayout(dir_layout)
        
        # 刀路数
        paths_label = QLabel("刀路数: 10")
        paths_label.setStyleSheet("QLabel { font-size: 10px; }")
        self.paths_slider = QSlider(Qt.Horizontal)
        self.paths_slider.setMinimum(3)
        self.paths_slider.setMaximum(20)
        self.paths_slider.setValue(10)
        self.paths_slider.setMaximumHeight(20)
        self.paths_slider.valueChanged.connect(
            lambda v: paths_label.setText(f"刀路数: {v}")
        )
        param_layout.addWidget(paths_label)
        param_layout.addWidget(self.paths_slider)
        
        # 刀轴方向反转
        self.checkbox_invert_tool_axis = QCheckBox("反转刀轴方向")
        self.checkbox_invert_tool_axis.setChecked(False)
        param_layout.addWidget(self.checkbox_invert_tool_axis)
        
        param_group.setLayout(param_layout)
        control_layout.addWidget(param_group)
        
        # 执行和输出按钮（水平布局）
        btn_layout = QHBoxLayout()
        self.btn_calculate = QPushButton("计算")
        self.btn_calculate.setEnabled(False)
        self.btn_calculate.setMaximumHeight(32)
        self.btn_calculate.clicked.connect(self.calculate_toolpath)
        self.btn_export = QPushButton("输出")
        self.btn_export.setEnabled(False)
        self.btn_export.setMaximumHeight(32)
        self.btn_export.clicked.connect(self.export_toolpath)
        btn_layout.addWidget(self.btn_calculate)
        btn_layout.addWidget(self.btn_export)
        control_layout.addLayout(btn_layout)
        
        # 工件坐标系（简化，隐藏开发中功能）
        wcs_layout = QHBoxLayout()
        wcs_layout.addWidget(QLabel("坐标系:"))
        self.wcs_radio_world = QRadioButton("世界")
        self.wcs_radio_world.setChecked(True)
        self.wcs_radio_world.setEnabled(True)
        wcs_layout.addWidget(self.wcs_radio_world)
        wcs_layout.addStretch()
        control_layout.addLayout(wcs_layout)
        
        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximumHeight(15)
        control_layout.addWidget(self.progress)
        
        # 状态信息（紧凑）
        self.status_label = QLabel("就绪")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("QLabel { font-size: 10px; padding: 3px; }")
        control_layout.addWidget(self.status_label)
        
        # 刀位点计数
        self.point_count_label = QLabel("")
        self.point_count_label.setWordWrap(True)
        self.point_count_label.setStyleSheet("QLabel { color: green; font-size: 10px; font-weight: bold; padding: 2px; }")
        control_layout.addWidget(self.point_count_label)
        
        control_layout.addStretch()
        
        # 显示模式控制（底部，紧凑）
        view_group = QGroupBox("显示")
        view_layout = QVBoxLayout()
        view_layout.setSpacing(4)
        
        # 显示模式（水平布局）
        display_layout = QHBoxLayout()
        self.display_mode_group = QButtonGroup()
        self.radio_shaded = QRadioButton("着色")
        self.radio_wireframe = QRadioButton("线框")
        self.radio_shaded.setChecked(True)
        self.display_mode_group.addButton(self.radio_shaded, 0)
        self.display_mode_group.addButton(self.radio_wireframe, 1)
        self.radio_shaded.toggled.connect(lambda checked: self.set_shaded_mode() if checked else None)
        self.radio_wireframe.toggled.connect(lambda checked: self.set_wireframe_mode() if checked else None)
        display_layout.addWidget(self.radio_shaded)
        display_layout.addWidget(self.radio_wireframe)
        display_layout.addStretch()
        view_layout.addLayout(display_layout)
        
        # 刀轴显示开关（默认勾选）
        self.checkbox_show_normals = QCheckBox("显示刀轴")
        self.checkbox_show_normals.setChecked(True)  # 先设置状态
        self.checkbox_show_normals.toggled.connect(self.toggle_normals_display)  # 后连接信号
        view_layout.addWidget(self.checkbox_show_normals)
        
        view_group.setLayout(view_layout)
        control_layout.addWidget(view_group)
        main_layout.addWidget(control_panel, stretch=1)
    
    def setup_lighting(self):
        """配置UG/NX风格光照系统"""
        view = self.viewer._display.View
        
        # 清除默认光源
        view.InitActiveLights()
        while view.MoreActiveLights():
            view.ActiveLight().SetEnabled(False)
            view.NextActiveLights()
        
        # 环境光（柔和全局照明，强度30%）
        ambient = V3d_AmbientLight()
        ambient.SetIntensity(0.3)
        view.SetLightOn(ambient)
        
        # 主方向光（右上45度，强度80%）
        main_light = V3d_DirectionalLight(V3d_TypeOfLight.V3d_DIRECTIONAL)
        main_light.SetDirection(-1, -1, -1)
        main_light.SetIntensity(0.8)
        view.SetLightOn(main_light)
        
        # 辅助光（左侧补光，强度40%）
        fill_light = V3d_DirectionalLight(V3d_TypeOfLight.V3d_DIRECTIONAL)
        fill_light.SetDirection(1, -0.5, -0.5)
        fill_light.SetIntensity(0.4)
        view.SetLightOn(fill_light)
        
        # 启用头灯（跟随相机）
        view.SetLightOn()
    
    def setup_material(self):
        """创建金属材质（铝合金风格）"""
        material = Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NOM_ALUMINIUM)
        material.SetShininess(0.8)  # 光泽度 (0-1)
        return material
    
    
    def _reset_state(self):
        """重置模型相关状态，释放旧资源"""
        # 等待正在运行的计算线程
        if self.worker and self.worker.isRunning():
            self.worker.finished.disconnect()
            self.worker.error.disconnect()
            self.worker.wait(3000)
        self.worker = None
        
        # 清除AIS对象（EraseAll之前先置空引用，避免对已移除对象操作）
        self.selected_face_ais = None
        self.toolpath_ais = None
        self.world_cs_ais = None  # 重置世界坐标系，加载新模型时重新创建
        
        # 清除模型数据
        self.shape = None
        self.faces = []
        self.selected_face = None
        self.selected_face_index = -1
        self.toolpath_points = None
        self.step_data = None
        
        # 重置UI
        self.btn_calculate.setEnabled(False)
        self.face_label.setText("请在3D视图中点击选择一个面")
        self.point_count_label.setText("")
        self.progress.setVisible(False)
    
    def load_step_file(self):
        """加载STEP文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择STEP文件", "", "STEP Files (*.stp *.step);;All Files (*)"
        )
        
        if not file_path:
            return
        
        # 清理旧模型状态
        self._reset_state()
        
        self.step_file_path = file_path
        self.file_label.setText("正在加载...")
        self.status_label.setText("正在加载STEP文件...")
        
        try:
            # 检查文件大小
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            is_large_file = file_size_mb > 100
            
            if is_large_file:
                QMessageBox.warning(
                    self, "大文件警告",
                    f"文件大小 {file_size_mb:.1f} MB，超过100MB。\n"
                    f"将作为整体Shape显示以保证性能，面选择使用几何匹配模式。"
                )
            
            # 读取STEP文件
            reader = STEPControl_Reader()
            if reader.ReadFile(file_path) != IFSelect_RetDone:
                raise Exception("无法读取STEP文件")
            
            reader.TransferRoots()
            self.shape = reader.OneShape()
            
            # 提取所有面
            self.faces = []
            explorer = TopExp_Explorer(self.shape, TopAbs_FACE)
            face_index = 0
            while explorer.More():
                face = topods.Face(explorer.Current())
                self.faces.append(face)
                explorer.Next()
                face_index += 1
            
            # 更新文件信息显示
            self.file_label.setText(
                f"{os.path.basename(file_path)}\n"
                f"{len(self.faces)} 个面 | {file_size_mb:.1f} MB"
            )
            
            # 显示模型
            self.viewer._display.EraseAll()
            
            # 大文件或面数多时整体显示，否则逐面显示
            if is_large_file or len(self.faces) > 500:
                # 整体显示，面选择通过几何匹配
                ais_shape = AIS_Shape(self.shape)
                ais_shape.SetColor(Quantity_Color(0.75, 0.75, 0.8, Quantity_TOC_RGB))
                ais_shape.SetMaterial(self.setup_material())
                ais_shape.SetTransparency(0.2)  # 80%不透明度（0.2透明度）
                self.viewer._display.Context.Display(ais_shape, True)
                self.status_label.setText(f"已加载 {len(self.faces)} 个面（整体显示，几何匹配选择）")
            else:
                # 逐面显示
                material = self.setup_material()
                for face in self.faces:
                    ais_face = AIS_Shape(face)
                    ais_face.SetColor(Quantity_Color(0.75, 0.75, 0.8, Quantity_TOC_RGB))
                    ais_face.SetMaterial(material)
                    ais_face.SetTransparency(0.2)  # 80%不透明度（0.2透明度）
                    self.viewer._display.Context.Display(ais_face, False)
                
                self.viewer._display.Repaint()
                self.status_label.setText(f"已加载 {len(self.faces)} 个面，请点击选择一个面")
            
            self.viewer._display.FitAll()
            
            # 显示世界坐标系参考
            self.display_world_coordinate_system()
            
            # 重新激活面选择模式（必须在DisplayShape之后，否则新对象不会被激活）
            self.viewer._display.SetSelectionModeFace()
            
            # 缓存文件数据
            with open(file_path, 'rb') as f:
                self.step_data = f.read()
            
            # 只注册一次回调
            if not self._callback_registered:
                self.viewer._display.register_select_callback(self.on_face_selected)
                self._callback_registered = True
            
        except Exception as e:
            QMessageBox.critical(self, "加载错误", f"加载STEP文件失败:\n{e}")
            self.status_label.setText("加载失败")
    
    def on_face_selected(self, shapes, x, y):
        """面选择回调"""
        # 如果正在拾取工件坐标系点，使用点击位置
        if self.wcs_picking_step > 0:
            # 获取3D点坐标（使用视图投影）
            view = self.viewer._display.View
            from OCC.Core.gp import gp_Pnt
            point_3d = gp_Pnt()
            # 简化：使用shapes中心点或直接使用x,y投影
            if shapes:
                # 尝试从选中的形状获取点
                selected_shape = shapes[0]
                if selected_shape.ShapeType() == TopAbs_VERTEX:
                    vertex = topods.Vertex(selected_shape)
                    point_3d = BRep_Tool.Pnt(vertex)
                elif selected_shape.ShapeType() == TopAbs_FACE:
                    # 使用面的中心点
                    face = topods.Face(selected_shape)
                    props = GProp_GProps()
                    brepgprop.SurfaceProperties(face, props)
                    point_3d = props.CentreOfMass()
                else:
                    # 使用包围盒中心
                    from OCC.Core.Bnd import Bnd_Box
                    from OCC.Core.BRepBndLib import brepbndlib
                    bbox = Bnd_Box()
                    brepbndlib.Add(selected_shape, bbox)
                    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
                    point_3d = gp_Pnt((xmin+xmax)/2, (ymin+ymax)/2, (zmin+zmax)/2)
                
                self.on_wcs_point_picked(point_3d.X(), point_3d.Y(), point_3d.Z())
                return
        
        # 正常的面选择逻辑
        if not shapes or not self.faces:
            return
        
        # shapes[0] 是 Context.SelectedShape() 返回的 TopoDS_Shape
        selected_shape = shapes[0]
        
        # 提取面
        selected_face = None
        if selected_shape.ShapeType() == TopAbs_FACE:
            selected_face = topods.Face(selected_shape)
        else:
            exp = TopExp_Explorer(selected_shape, TopAbs_FACE)
            if exp.More():
                selected_face = topods.Face(exp.Current())
        
        if not selected_face:
            return
        
        # 在 self.faces 中查找匹配：IsSame > IsPartner > 几何匹配
        face_index = -1
        for i, face in enumerate(self.faces):
            if face.IsSame(selected_face):
                face_index = i
                break
        
        if face_index == -1:
            for i, face in enumerate(self.faces):
                if face.IsPartner(selected_face):
                    face_index = i
                    break
        
        if face_index == -1:
            # 几何属性匹配作为最后手段
            props_selected = GProp_GProps()
            brepgprop.SurfaceProperties(selected_face, props_selected)
            center_selected = props_selected.CentreOfMass()
            area_selected = props_selected.Mass()
            
            best_dist = float('inf')
            for i, face in enumerate(self.faces):
                props_face = GProp_GProps()
                brepgprop.SurfaceProperties(face, props_face)
                center = props_face.CentreOfMass()
                area = props_face.Mass()
                
                if abs(area - area_selected) < 0.01:
                    dist = ((center.X() - center_selected.X())**2 +
                            (center.Y() - center_selected.Y())**2 +
                            (center.Z() - center_selected.Z())**2)
                    if dist < best_dist and dist < 0.01:
                        best_dist = dist
                        face_index = i
        
        if face_index == -1 or face_index >= len(self.faces):
            return
        
        self.selected_face = self.faces[face_index]
        self.selected_face_index = face_index
        
        # 清除旧的高亮
        if self.selected_face_ais:
            self.viewer._display.Context.Remove(self.selected_face_ais, True)
            self.selected_face_ais = None
        
        # 高亮显示选中的面（桔黄色，半透明，不参与选择）
        self.selected_face_ais = AIS_Shape(self.selected_face)
        self.selected_face_ais.SetColor(Quantity_Color(1.0, 0.6, 0.0, Quantity_TOC_RGB))
        self.selected_face_ais.SetTransparency(0.3)
        
        # selectionMode=-1 表示不激活任何选择模式，避免干扰面选择
        self.viewer._display.Context.Display(self.selected_face_ais, 1, -1, True)
        
        # 获取面积和UV范围
        props = GProp_GProps()
        brepgprop.SurfaceProperties(self.selected_face, props)
        area = props.Mass()
        
        u_min, u_max, v_min, v_max = breptools.UVBounds(self.selected_face)
        
        self.face_label.setText(
            f"已选择面 #{face_index}\n面积: {area:.2f}\n"
            f"UV范围:\nU[{u_min:.4f}, {u_max:.4f}]\n"
            f"V[{v_min:.4f}, {v_max:.4f}]"
        )
        self.btn_calculate.setEnabled(True)
        self.status_label.setText("已选择面，可以重新点击选择其他面")
    
    def calculate_toolpath(self):
        """计算刀路"""
        if not self.selected_face or not self.step_data:
            return
        
        # 如果有正在运行的计算，断开信号避免干扰
        if self.worker and self.worker.isRunning():
            self.worker.finished.disconnect()
            self.worker.error.disconnect()
            self.worker.wait(3000)
        
        # 清除上一次的刀轨显示
        if self.toolpath_ais:
            self.viewer._display.Context.Remove(self.toolpath_ais, True)
            self.toolpath_ais = None
        if self.normals_ais:
            self.viewer._display.Context.Remove(self.normals_ais, True)
            self.normals_ais = None
        self.toolpath_points = None
        self.toolpath_normals = None
        self.point_count_label.setText("")  # 清除点数显示
        
        # 使用缓存的文件数据
        step_data = self.step_data
        
        # 获取参数
        toolpath_mode = self.mode_group.checkedId()
        num_paths = self.paths_slider.value()
        
        # 计算步长
        u_min, u_max, v_min, v_max = breptools.UVBounds(self.selected_face)
        
        if toolpath_mode == 0:  # 行切
            if self.dir_group.checkedId() == 1:  # V向
                step_v = (v_max - v_min) / (num_paths - 1) if num_paths > 1 else (v_max - v_min)
                step_u = (u_max - u_min) / 20.0
            else:  # U向
                step_u = (u_max - u_min) / (num_paths - 1) if num_paths > 1 else (u_max - u_min)
                step_v = (v_max - v_min) / 20.0
        else:  # 环切
            step_u = 1.0
            step_v = 1.0
        
        params = {
            'toolpath_mode': toolpath_mode,
            'num_paths': num_paths,
            'step_u': step_u,
            'step_v': step_v,
            'start_direction': self.dir_group.checkedId()  # 0=U向, 1=V向
        }
        
        # 禁用按钮，显示进度
        self.btn_calculate.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # 不确定进度
        
        mode_name = "环切" if toolpath_mode == 1 else "行切"
        self.status_label.setText(f"正在计算刀路...\n模式: {mode_name}\n刀路数: {num_paths}\n请稍候...")
        QApplication.processEvents()  # 立即更新UI
        
        # 启动后台线程
        self.worker = ToolpathWorker(self.calculator, step_data, params, self.selected_face_index)
        self.worker.finished.connect(self.on_toolpath_calculated)
        self.worker.error.connect(self.on_toolpath_error)
        self.worker.start()
    
    def on_toolpath_calculated(self, points, normals):
        """刀路计算完成"""
        # 根据用户设置决定刀轴方向
        if self.checkbox_invert_tool_axis.isChecked():
            normals = -normals  # 用户勾选反转：反转刀轴
        
        self.toolpath_points = points
        self.toolpath_normals = normals
        
        # 显示刀轨
        self.display_toolpath(points)
        
        # 如果刀轴显示开关打开，显示刀轴
        if self.show_normals:
            self.display_normals()
        
        # 恢复UI
        self.btn_calculate.setEnabled(True)
        self.btn_export.setEnabled(True)  # 启用输出按钮
        self.progress.setVisible(False)
        
        # 计算统计信息
        total_length = 0.0
        for i in range(len(points) - 1):
            dx = points[i+1][0] - points[i][0]
            dy = points[i+1][1] - points[i][1]
            dz = points[i+1][2] - points[i][2]
            total_length += (dx*dx + dy*dy + dz*dz) ** 0.5
        
        self.status_label.setText(
            f"✓ 刀路计算完成\n"
            f"点数: {len(points)}\n"
            f"路径长度: {total_length:.2f} mm"
        )
        
        # 更新刀位点计数显示
        self.point_count_label.setText(f"当前刀位点: {len(points)} 个")
    
    def on_toolpath_error(self, error_msg):
        """刀路计算错误"""
        QMessageBox.critical(self, "计算错误", f"刀路计算失败:\n{error_msg}")
        self.btn_calculate.setEnabled(True)
        self.progress.setVisible(False)
        self.status_label.setText("✗ 计算失败，请检查参数或服务器连接")
    
    def display_toolpath(self, points):
        """显示刀轨"""
        # 创建刀轨线段
        edges = []
        for i in range(len(points) - 1):
            p1 = gp_Pnt(points[i][0], points[i][1], points[i][2])
            p2 = gp_Pnt(points[i+1][0], points[i+1][1], points[i+1][2])
            edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
            edges.append(edge)
        
        wire_builder = BRepBuilderAPI_MakeWire()
        for edge in edges:
            wire_builder.Add(edge)
        toolpath_wire = wire_builder.Wire()
        
        # 显示刀轨（绿色加粗）
        self.toolpath_ais = AIS_Shape(toolpath_wire)
        self.toolpath_ais.SetColor(Quantity_Color(0.0, 0.8, 0.0, Quantity_TOC_RGB))
        
        drawer = self.toolpath_ais.Attributes()
        line_aspect = Prs3d_LineAspect(
            Quantity_Color(0.0, 0.8, 0.0, Quantity_TOC_RGB), 
            Aspect_TOL_SOLID, 
            3.0
        )
        drawer.SetWireAspect(line_aspect)
        self.toolpath_ais.SetAttributes(drawer)
        
        self.viewer._display.Context.Display(self.toolpath_ais, True)
    
    def on_wcs_mode_changed(self):
        """工件坐标系模式切换（简化版）"""
        # 当前只支持世界坐标系
        self.wcs_mode = 0
        self.wcs_transform = np.eye(4)
    
    def start_wcs_picking(self):
        """开始三点拾取定义工件坐标系（禁用）"""
        pass
    
    def start_wcs_adjustment(self):
        """开始调整工件坐标系（禁用）"""
        pass
    
    def on_wcs_point_picked(self, x, y, z):
        """工件坐标系点拾取回调（禁用）"""
        pass
        
        current_point = np.array([x, y, z])
        
        # 检查是否与已有点重合
        for i, existing_point in enumerate(self.wcs_points):
            dist = np.linalg.norm(current_point - existing_point)
            if dist < 1e-3:  # 距离小于0.001mm视为重合
                QMessageBox.warning(
                    self, "错误", 
                    f"拾取的点与第{i+1}个点距离太近（{dist:.6f}mm），请选择不同的点"
                )
                return
        
        self.wcs_points.append(current_point)
        
        mode_prefix = "调整模式" if self.wcs_adjusting else "工件坐标系设置"
        
        if self.wcs_picking_step == 1:
            self.wcs_status_label.setText("请点击X轴正方向")
            self.status_label.setText(f"{mode_prefix}:\n步骤2/3 - 点击X轴方向")
            self.wcs_picking_step = 2
        elif self.wcs_picking_step == 2:
            self.wcs_status_label.setText("请点击XY平面上一点")
            self.status_label.setText(f"{mode_prefix}:\n步骤3/3 - 点击XY平面")
            self.wcs_picking_step = 3
        elif self.wcs_picking_step == 3:
            # 计算坐标系
            self.compute_wcs_transform()
            if self.wcs_picking_step == 0:  # compute失败会重置step
                return
            self.wcs_adjusting = False
            self.wcs_status_label.setText("状态: 已设置")
            self.status_label.setText("✓ 工件坐标系设置完成")
            self.btn_adjust_wcs.setEnabled(True)
            self.display_custom_wcs()
            self.update_wcs_info()
    
    def compute_wcs_transform(self):
        """根据三点计算工件坐标系变换矩阵"""
        origin = self.wcs_points[0]
        x_point = self.wcs_points[1]
        xy_point = self.wcs_points[2]
        
        # X轴方向
        x_vec = x_point - origin
        x_len = np.linalg.norm(x_vec)
        if x_len < 1e-6:
            QMessageBox.warning(self, "错误", "原点和X轴点距离太近，请重新选择")
            self.wcs_picking_step = 0
            self.wcs_adjusting = False
            return
        x_vec = x_vec / x_len
        
        # 临时Y方向
        temp_y = xy_point - origin
        temp_y_len = np.linalg.norm(temp_y)
        if temp_y_len < 1e-6:
            QMessageBox.warning(self, "错误", "原点和XY平面点距离太近，请重新选择")
            self.wcs_picking_step = 0
            self.wcs_adjusting = False
            return
        
        # Z轴 = X × temp_Y
        z_vec = np.cross(x_vec, temp_y)
        z_len = np.linalg.norm(z_vec)
        if z_len < 1e-6:
            QMessageBox.warning(self, "错误", "三点共线，无法定义坐标系，请重新选择")
            self.wcs_picking_step = 0
            self.wcs_adjusting = False
            return
        z_vec = z_vec / z_len
        
        # Y轴 = Z × X (确保正交)
        y_vec = np.cross(z_vec, x_vec)
        
        # 构建变换矩阵 (世界坐标系 -> 工件坐标系)
        R = np.column_stack([x_vec, y_vec, z_vec])
        self.wcs_transform = np.eye(4)
        self.wcs_transform[:3, :3] = R.T
        self.wcs_transform[:3, 3] = -R.T @ origin
    
    def display_world_coordinate_system(self):
        """显示世界坐标系（固定参考）"""
        if self.world_cs_ais:
            return  # 已显示
        
        # 计算轴长度（模型包围盒的15%，如果没有模型则使用默认值）
        axis_length = 50.0
        if self.shape:
            from OCC.Core.Bnd import Bnd_Box
            from OCC.Core.BRepBndLib import brepbndlib
            bbox = Bnd_Box()
            brepbndlib.Add(self.shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            diagonal = ((xmax-xmin)**2 + (ymax-ymin)**2 + (zmax-zmin)**2) ** 0.5
            axis_length = diagonal * 0.15
        
        # 创建世界坐标系 (原点在0,0,0)
        origin = gp_Pnt(0, 0, 0)
        z_dir = gp_Dir(0, 0, 1)
        x_dir = gp_Dir(1, 0, 0)
        ax2 = gp_Ax2(origin, z_dir, x_dir)
        
        geom_axis = Geom_Axis2Placement(ax2)
        self.world_cs_ais = AIS_Trihedron(geom_axis)
        
        # 设置尺寸和样式
        self.world_cs_ais.SetSize(axis_length)
        
        # 显示但不激活任何选择模式（关键修复）
        self.viewer._display.Context.Display(self.world_cs_ais, False)
        self.viewer._display.Repaint()
    
    def display_custom_wcs(self):
        """显示自定义工件坐标系"""
        if self.wcs_ais:
            self.viewer._display.Context.Remove(self.wcs_ais, True)
            self.wcs_ais = None
        
        # 从变换矩阵反算原点和方向
        R_inv = self.wcs_transform[:3, :3].T
        origin_world = -R_inv @ self.wcs_transform[:3, 3]
        
        x_dir_world = R_inv[:, 0]
        y_dir_world = R_inv[:, 1]
        z_dir_world = R_inv[:, 2]
        
        # 验证方向向量
        if np.linalg.norm(x_dir_world) < 1e-6 or np.linalg.norm(z_dir_world) < 1e-6:
            QMessageBox.warning(self, "错误", "坐标系方向向量无效")
            return
        
        # 计算轴长度
        axis_length = 50.0
        if self.shape:
            from OCC.Core.Bnd import Bnd_Box
            from OCC.Core.BRepBndLib import brepbndlib
            bbox = Bnd_Box()
            brepbndlib.Add(self.shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            diagonal = ((xmax-xmin)**2 + (ymax-ymin)**2 + (zmax-zmin)**2) ** 0.5
            axis_length = diagonal * 0.2  # 自定义坐标系稍大
        
        # 创建坐标系
        try:
            origin = gp_Pnt(float(origin_world[0]), float(origin_world[1]), float(origin_world[2]))
            z_dir = gp_Dir(float(z_dir_world[0]), float(z_dir_world[1]), float(z_dir_world[2]))
            x_dir = gp_Dir(float(x_dir_world[0]), float(x_dir_world[1]), float(x_dir_world[2]))
            ax2 = gp_Ax2(origin, z_dir, x_dir)
            
            geom_axis = Geom_Axis2Placement(ax2)
            self.wcs_ais = AIS_Trihedron(geom_axis)
            
            # 设置尺寸和样式（不透明，更明显）
            self.wcs_ais.SetSize(axis_length)
            
            # 显示但不激活任何选择模式（关键修复）
            self.viewer._display.Context.Display(self.wcs_ais, False)
            self.viewer._display.Repaint()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建坐标系失败:\n{e}")
    
    def toggle_normals_display(self, checked):
        """切换刀轴显示"""
        self.show_normals = checked
        if checked:
            # 有数据时才显示
            if self.toolpath_points is not None and self.toolpath_normals is not None:
                self.display_normals()
        else:
            # 隐藏刀轴
            if self.normals_ais:
                self.viewer._display.Context.Remove(self.normals_ais, True)
                self.viewer._display.Repaint()
                self.normals_ais = None
    
    def display_normals(self):
        """显示刀轨刀轴"""
        if self.toolpath_points is None or self.toolpath_normals is None:
            return
        
        # 清除旧的刀轴显示
        if self.normals_ais:
            self.viewer._display.Context.Remove(self.normals_ais, True)
            self.normals_ais = None
        
        # 计算合理的刀轴长度（刀轨包围盒对角线的2%）
        points = self.toolpath_points
        normals = self.toolpath_normals  # 直接使用存储的刀轴方向
        bbox_min = np.min(points, axis=0)
        bbox_max = np.max(points, axis=0)
        diagonal = np.linalg.norm(bbox_max - bbox_min)
        normal_length = diagonal * 0.02
        
        # 创建刀轴线段（每隔5个点显示一个刀轴，避免过于密集）
        from OCC.Core.TopoDS import TopoDS_Compound
        from OCC.Core.BRep import BRep_Builder
        compound = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(compound)
        
        step = max(1, len(points) // 100)  # 最多显示100个刀轴
        for i in range(0, len(points), step):
            p = points[i]
            n = normals[i]
            
            # 安全检查：跳过无效的法线
            if not np.isfinite(n).all() or np.linalg.norm(n) < 1e-6:
                continue
            
            # 起点和终点
            p1 = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            p2 = gp_Pnt(float(p[0] + n[0] * normal_length), 
                        float(p[1] + n[1] * normal_length), 
                        float(p[2] + n[2] * normal_length))
            
            try:
                edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
                builder.Add(compound, edge)
            except Exception:
                continue  # 跳过无法创建的边
        
        # 显示刀轴（深绿色）
        self.normals_ais = AIS_Shape(compound)
        self.normals_ais.SetColor(Quantity_Color(0.0, 0.5, 0.0, Quantity_TOC_RGB))
        
        drawer = self.normals_ais.Attributes()
        line_aspect = Prs3d_LineAspect(
            Quantity_Color(0.0, 0.5, 0.0, Quantity_TOC_RGB), 
            Aspect_TOL_SOLID, 
            1.5
        )
        drawer.SetWireAspect(line_aspect)
        self.normals_ais.SetAttributes(drawer)
        
        self.viewer._display.Context.Display(self.normals_ais, False)
        self.viewer._display.Repaint()
    def update_wcs_info(self):
        """更新工件坐标系变换信息显示"""
        # 提取原点
        R_inv = self.wcs_transform[:3, :3].T
        origin = -R_inv @ self.wcs_transform[:3, 3]
        
        # 提取欧拉角 (ZYX顺序)
        R = self.wcs_transform[:3, :3]
        sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
        
        if sy > 1e-6:
            rx = np.arctan2(R[2, 1], R[2, 2])
            ry = np.arctan2(-R[2, 0], sy)
            rz = np.arctan2(R[1, 0], R[0, 0])
        else:
            rx = np.arctan2(-R[1, 2], R[1, 1])
            ry = np.arctan2(-R[2, 0], sy)
            rz = 0
        
        # 转换为角度
        rx_deg = np.degrees(rx)
        ry_deg = np.degrees(ry)
        rz_deg = np.degrees(rz)
        
        self.wcs_info_label.setText(
            f"原点: ({origin[0]:.2f}, {origin[1]:.2f}, {origin[2]:.2f})\n"
            f"旋转: X={rx_deg:.1f}° Y={ry_deg:.1f}° Z={rz_deg:.1f}°"
        )
    
    def export_toolpath(self):
        """输出刀路到文件"""
        if self.toolpath_points is None or self.toolpath_normals is None:
            QMessageBox.warning(self, "警告", "没有可输出的刀路数据")
            return
        
        # 选择输出格式
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择输出格式")
        layout = QVBoxLayout()
        
        radio_script = QRadioButton("运动脚本 (.py)")
        radio_txt = QRadioButton("文本格式 (.txt)")
        radio_script.setChecked(True)
        
        layout.addWidget(radio_script)
        layout.addWidget(radio_txt)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() != QDialog.Accepted:
            return
        
        # 根据选择调用不同的输出函数
        if radio_script.isChecked():
            self._export_motion_script()
        else:
            self._export_text_format()
    
    def _export_text_format(self):
        """输出文本格式刀路"""
        from pathlib import Path
        
        # 默认输出目录：MotorCortex_MVP/scripts/CAMpaths
        default_dir = Path("/Users/y/openclaw/myWorkspace/02_Develop/SourceCode/MotorCortex_MVP/scripts/CAMpaths")
        
        # 如果目录不存在，回退到用户文档目录
        if not default_dir.exists():
            default_dir = Path.home() / "Documents"
        
        # 生成简短文件名：tp_3ax_时间.txt 或 tp_5ax_时间.txt
        axis_mode = self.axis_group.checkedId()
        axis_str = "3ax" if axis_mode == 3 else "5ax"
        timestamp = QDateTime.currentDateTime().toString('MMdd_HHmm')
        default_name = f"tp_{axis_str}_{timestamp}.txt"
        default_path = str(Path(default_dir) / default_name)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "输出刀路", default_path, "文本文件 (*.txt);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        try:
            points_wcs = self.transform_points_to_wcs(self.toolpath_points)
            normals_wcs = self.transform_normals_to_wcs(self.toolpath_normals)
            
            with open(file_path, 'w') as f:
                f.write("; Toolpath Output\n")
                f.write(f"; Coordinate System: {'Custom' if self.wcs_mode == 1 else 'World'}\n")
                f.write(f"; Total Points: {len(points_wcs)}\n")
                
                total_length = 0.0
                for i in range(len(points_wcs) - 1):
                    total_length += np.linalg.norm(points_wcs[i+1] - points_wcs[i])
                f.write(f"; Path Length: {total_length:.3f} mm\n")
                f.write(f"; Generated: {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}\n")
                f.write(";\n")
                f.write("; Format: X Y Z Nx Ny Nz\n")
                f.write(";\n")
                
                for i in range(len(points_wcs)):
                    p = points_wcs[i]
                    n = normals_wcs[i]
                    f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
            
            QMessageBox.information(self, "成功", f"刀路已输出到:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"输出失败:\n{e}")
    
    def _export_motion_script(self):
        """输出运动脚本"""
        from pathlib import Path
        
        # 默认输出目录：MotorCortex_MVP/scripts/CAMpaths
        default_dir = Path("/Users/y/openclaw/myWorkspace/02_Develop/SourceCode/MotorCortex_MVP/scripts/CAMpaths")
        
        # 如果目录不存在，回退到用户文档目录
        if not default_dir.exists():
            default_dir = Path.home() / "Documents"
        
        # 生成简短文件名：ms_3ax_时间.py 或 ms_5ax_时间.py
        axis_mode = self.axis_group.checkedId()
        axis_str = "3ax" if axis_mode == 3 else "5ax"
        timestamp = QDateTime.currentDateTime().toString('MMdd_HHmm')
        default_name = f"ms_{axis_str}_{timestamp}.py"
        default_path = str(Path(default_dir) / default_name)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "输出运动脚本", default_path, "Python脚本 (*.py);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        try:
            # 转换坐标
            points_wcs = self.transform_points_to_wcs(self.toolpath_points)
            normals_wcs = self.transform_normals_to_wcs(self.toolpath_normals)
            
            # 准备元数据
            metadata = {
                'model_name': os.path.basename(self.step_file_path) if self.step_file_path else 'Unknown',
                'toolpath_mode': self.mode_group.checkedId(),
                'num_paths': self.paths_slider.value()
            }
            
            # 获取轴数模式
            axis_mode = self.axis_group.checkedId()
            
            # 生成脚本
            generate_motion_script(
                toolpath_points=points_wcs,
                toolpath_normals=normals_wcs,
                output_path=file_path,
                feed_rapid=3000.0,  # 快速移动 mm/s（非切削，快）
                feed_cut=300.0,     # 切削进给 mm/s（切削，慢且稳定）
                retract_height=5.0, # 抬刀高度 mm
                axis_mode=axis_mode,
                metadata=metadata
            )
            
            axis_mode_str = "3轴" if axis_mode == 3 else "3+轴"
            QMessageBox.information(
                self, "成功", 
                f"运动脚本已生成:\n{file_path}\n\n"
                f"轴数: {axis_mode_str}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"脚本生成失败:\n{e}")
    
    def transform_points_to_wcs(self, points):
        """将点从世界坐标系转换到工件坐标系"""
        if self.wcs_mode == 0:
            return points
        
        # 齐次坐标
        points_h = np.hstack([points, np.ones((len(points), 1))])
        # 应用变换
        points_wcs = (self.wcs_transform @ points_h.T).T
        return points_wcs[:, :3]
    
    def transform_normals_to_wcs(self, normals):
        """将法线从世界坐标系转换到工件坐标系"""
        if self.wcs_mode == 0:
            return normals
        
        # 法线只需旋转，不需要平移
        R = self.wcs_transform[:3, :3]
        return (R @ normals.T).T
    
    def closeEvent(self, event):
        """关闭窗口"""
        self.calculator.close()
        event.accept()
    
    def set_wireframe_mode(self):
        """设置线框模式"""
        # 使用display的内置方法
        self.viewer._display.SetModeWireFrame()
        self.status_label.setText("显示模式: 线框")
    
    def set_shaded_mode(self):
        """设置着色模式"""
        # 使用display的内置方法
        self.viewer._display.SetModeShaded()
        self.status_label.setText("显示模式: 着色")


def main():
    app = QApplication(sys.argv)
    window = CamGuiClient()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
