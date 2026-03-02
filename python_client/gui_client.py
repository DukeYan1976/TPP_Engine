"""CAM刀轨计算 - Qt GUI客户端"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QRadioButton, QButtonGroup, QSlider, QMessageBox,
                             QGroupBox, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from OCC.Display.backend import load_backend
load_backend('pyqt5')
from OCC.Display.qtDisplay import qtViewer3d

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import topods
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepTools import breptools
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCC.Core.AIS import AIS_Shape
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCC.Core.gp import gp_Pnt
from OCC.Core.Prs3d import Prs3d_LineAspect
from OCC.Core.Aspect import Aspect_TOL_SOLID
from OCC.Core.V3d import V3d_DirectionalLight, V3d_AmbientLight, V3d_TypeOfLight
from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial

from cam_calculator import CamCalculator
import numpy as np


class ToolpathWorker(QThread):
    """后台线程执行刀轨计算"""
    finished = pyqtSignal(np.ndarray)
    error = pyqtSignal(str)
    
    def __init__(self, calculator, step_data, params, face_index):
        super().__init__()
        self.calculator = calculator
        self.step_data = step_data
        self.params = params
        self.face_index = face_index
    
    def run(self):
        try:
            points = self.calculator.calculate_toolpath(
                self.step_data,
                self.params['toolpath_mode'],
                self.params['num_paths'],
                self.params['step_u'],
                self.params['step_v'],
                self.params['start_direction'],
                self.face_index
            )
            self.finished.emit(points)
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
        self.toolpath_ais = None  # 保存刀轨AIS对象用于删除
        self.calculator = CamCalculator()
        self.worker = None  # 后台计算线程
        self._callback_registered = False  # 回调是否已注册
        
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
        control_panel.setMaximumWidth(300)
        
        # 文件选择
        file_group = QGroupBox("STEP文件")
        file_layout = QVBoxLayout()
        self.file_label = QLabel("未选择文件")
        self.file_label.setWordWrap(True)
        btn_load = QPushButton("选择STEP文件")
        btn_load.clicked.connect(self.load_step_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(btn_load)
        file_group.setLayout(file_layout)
        control_layout.addWidget(file_group)
        
        # 面选择提示
        face_group = QGroupBox("面选择")
        face_layout = QVBoxLayout()
        self.face_label = QLabel("请在3D视图中点击选择一个面")
        self.face_label.setWordWrap(True)
        face_layout.addWidget(self.face_label)
        face_group.setLayout(face_layout)
        control_layout.addWidget(face_group)
        
        # 刀轨参数
        param_group = QGroupBox("刀轨参数")
        param_layout = QVBoxLayout()
        
        # 刀路模式
        mode_label = QLabel("刀路模式:")
        self.mode_group = QButtonGroup()
        self.radio_raster = QRadioButton("行切")
        self.radio_contour = QRadioButton("环切")
        self.radio_raster.setChecked(True)
        self.mode_group.addButton(self.radio_raster, 0)
        self.mode_group.addButton(self.radio_contour, 1)
        
        # 起始方向
        dir_label = QLabel("起始方向:")
        self.dir_group = QButtonGroup()
        self.radio_u = QRadioButton("U向")
        self.radio_v = QRadioButton("V向")
        self.radio_v.setChecked(True)
        self.dir_group.addButton(self.radio_u, 0)
        self.dir_group.addButton(self.radio_v, 1)
        
        # 刀路数
        paths_label = QLabel("刀路数: 10")
        self.paths_slider = QSlider(Qt.Horizontal)
        self.paths_slider.setMinimum(3)
        self.paths_slider.setMaximum(20)
        self.paths_slider.setValue(10)
        self.paths_slider.setTickPosition(QSlider.TicksBelow)
        self.paths_slider.setTickInterval(1)
        self.paths_slider.valueChanged.connect(
            lambda v: paths_label.setText(f"刀路数: {v}")
        )
        
        param_layout.addWidget(mode_label)
        param_layout.addWidget(self.radio_raster)
        param_layout.addWidget(self.radio_contour)
        param_layout.addWidget(dir_label)
        param_layout.addWidget(self.radio_u)
        param_layout.addWidget(self.radio_v)
        param_layout.addWidget(paths_label)
        param_layout.addWidget(self.paths_slider)
        param_group.setLayout(param_layout)
        control_layout.addWidget(param_group)
        
        # 执行按钮
        self.btn_calculate = QPushButton("计算刀路")
        self.btn_calculate.setEnabled(False)
        self.btn_calculate.clicked.connect(self.calculate_toolpath)
        control_layout.addWidget(self.btn_calculate)
        
        # 进度条
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        control_layout.addWidget(self.progress)
        
        # 状态信息
        self.status_label = QLabel("就绪")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("QLabel { padding: 5px; }")
        control_layout.addWidget(self.status_label)
        
        # 刀位点计数
        self.point_count_label = QLabel("")
        self.point_count_label.setWordWrap(True)
        self.point_count_label.setStyleSheet("QLabel { color: green; font-weight: bold; padding: 5px; }")
        control_layout.addWidget(self.point_count_label)
        
        control_layout.addStretch()
        
        # 分隔线
        from PyQt5.QtWidgets import QFrame
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        control_layout.addWidget(separator)
        
        # 显示模式控制（底部）
        view_group = QGroupBox("显示模式")
        view_layout = QVBoxLayout()
        
        self.display_mode_group = QButtonGroup()
        self.radio_shaded = QRadioButton("着色")
        self.radio_wireframe = QRadioButton("线框")
        self.radio_shaded.setChecked(True)
        
        self.display_mode_group.addButton(self.radio_shaded, 0)
        self.display_mode_group.addButton(self.radio_wireframe, 1)
        
        self.radio_shaded.toggled.connect(lambda checked: self.set_shaded_mode() if checked else None)
        self.radio_wireframe.toggled.connect(lambda checked: self.set_wireframe_mode() if checked else None)
        
        view_layout.addWidget(self.radio_shaded)
        view_layout.addWidget(self.radio_wireframe)
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
                self.viewer._display.Context.Display(ais_shape, True)
                self.status_label.setText(f"已加载 {len(self.faces)} 个面（整体显示，几何匹配选择）")
            else:
                # 逐面显示
                material = self.setup_material()
                for face in self.faces:
                    ais_face = AIS_Shape(face)
                    ais_face.SetColor(Quantity_Color(0.75, 0.75, 0.8, Quantity_TOC_RGB))
                    ais_face.SetMaterial(material)
                    self.viewer._display.Context.Display(ais_face, False)
                
                self.viewer._display.Repaint()
                self.status_label.setText(f"已加载 {len(self.faces)} 个面，请点击选择一个面")
            
            self.viewer._display.FitAll()
            
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
        
        # 高亮显示选中的面（红色，半透明，不参与选择）
        self.selected_face_ais = AIS_Shape(self.selected_face)
        self.selected_face_ais.SetColor(Quantity_Color(1.0, 0.2, 0.2, Quantity_TOC_RGB))
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
        self.toolpath_points = None
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
    
    def on_toolpath_calculated(self, points):
        """刀路计算完成"""
        self.toolpath_points = points
        
        # 显示刀轨
        self.display_toolpath(points)
        
        # 恢复UI
        self.btn_calculate.setEnabled(True)
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
