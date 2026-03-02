"""
MotorCortex MVP 程序脚本生成器
根据刀轨数据生成可执行的Python运动脚本
"""

import numpy as np
from typing import List, Tuple
from pathlib import Path
from datetime import datetime


class MotionScriptGenerator:
    """运动脚本生成器"""
    
    def __init__(self):
        self.feed_rapid = 3000.0  # 快速移动进给率 mm/s（非切削，快）
        self.feed_cut = 300.0     # 切削进给率 mm/s（切削，慢且稳定）
        self.safe_z = 50.0        # 安全高度 mm
        self.retract_height = 5.0 # 抬刀高度 mm（相对于刀路最高点）
        self.axis_mode = 5        # 轴数模式: 3=三轴, 5=五轴
    
    def generate_script(
        self,
        toolpath_points: np.ndarray,
        toolpath_normals: np.ndarray,
        output_path: str,
        metadata: dict = None
    ) -> str:
        """
        生成运动脚本
        
        Args:
            toolpath_points: 刀轨点坐标 (N, 3)
            toolpath_normals: 刀轨法线 (N, 3)，指向材料外侧
            output_path: 输出文件路径
            metadata: 元数据（可选）
            
        Returns:
            生成的脚本内容
        """
        if len(toolpath_points) == 0:
            raise ValueError("刀轨点数据为空")
        
        if len(toolpath_points) != len(toolpath_normals):
            raise ValueError("刀轨点和法线数量不匹配")
        
        # 归一化法线
        normals = self._normalize_normals(toolpath_normals)
        
        # 计算安全高度（刀路最高点 + retract_height）
        max_z = np.max(toolpath_points[:, 2])
        safe_z = max_z + self.retract_height
        
        # 生成脚本内容
        script_lines = []
        
        # 文件头
        script_lines.extend(self._generate_header(metadata, len(toolpath_points)))
        
        # 参数定义
        script_lines.extend(self._generate_parameters(safe_z))
        
        # 初始化：移动到安全平面
        script_lines.extend(self._generate_initial_move(safe_z))
        
        # 快速移动到起始点上方
        start_point = toolpath_points[0]
        script_lines.extend(self._generate_rapid_to_start(start_point, safe_z))
        
        # 下刀到起始点
        start_normal = normals[0]
        script_lines.extend(self._generate_approach(start_point, start_normal))
        
        # 连续切削轨迹
        script_lines.extend(self._generate_cutting_path(toolpath_points, normals))
        
        # 抬刀到安全高度
        end_point = toolpath_points[-1]
        script_lines.extend(self._generate_retract(end_point, safe_z))
        
        # 完成提示
        script_lines.append("\nprint('✓ 刀路执行完成')")
        
        # 写入文件
        script_content = '\n'.join(script_lines)
        Path(output_path).write_text(script_content, encoding='utf-8')
        
        return script_content
    
    def _normalize_normals(self, normals: np.ndarray) -> np.ndarray:
        """归一化法线向量"""
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0  # 避免除零
        return normals / norms
    
    def _generate_header(self, metadata: dict, point_count: int) -> List[str]:
        """生成文件头注释"""
        lines = [
            '"""',
            'MotorCortex MVP 运动脚本',
            f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            f'刀位点数: {point_count}',
        ]
        
        if metadata:
            if 'model_name' in metadata:
                lines.append(f'模型文件: {metadata["model_name"]}')
            if 'toolpath_mode' in metadata:
                mode_name = '环切' if metadata['toolpath_mode'] == 1 else '行切'
                lines.append(f'刀路模式: {mode_name}')
            if 'num_paths' in metadata:
                lines.append(f'刀路数量: {metadata["num_paths"]}')
        
        lines.extend([
            '"""',
            '',
            'import math',
            ''
        ])
        
        return lines
    
    def _generate_parameters(self, safe_z: float) -> List[str]:
        """生成参数定义"""
        axis_mode_str = '三轴' if self.axis_mode == 3 else '五轴'
        return [
            '# ========== 参数定义 ==========',
            f'feed_rapid = {self.feed_rapid}  # 快速移动进给率 mm/s',
            f'feed_cut = {self.feed_cut}      # 切削进给率 mm/s',
            f'safe_z = {safe_z:.3f}           # 安全高度 mm',
            f'# 轴数模式: {axis_mode_str}',
            ''
        ]
    
    def _generate_initial_move(self, safe_z: float) -> List[str]:
        """生成初始移动到安全平面"""
        lines = ['# ========== 初始化：移动到安全平面 ==========']
        
        if self.axis_mode == 3:
            lines.extend([
                f'LinearMove(',
                f'    x=0, y=0, z=safe_z,',
                f'    f=feed_rapid',
                f')',
            ])
        else:
            lines.extend([
                f'FiveAxisMove(',
                f'    x=0, y=0, z=safe_z,',
                f'    i=0, j=0, k=-1,',
                f'    f=feed_rapid',
                f')',
            ])
        
        lines.extend(['', 'Dwell(0.5)  # 稳定', ''])
        return lines
    
    def _generate_rapid_to_start(self, start_point: np.ndarray, safe_z: float) -> List[str]:
        """生成快速移动到起始点上方"""
        lines = ['# ========== 快速移动到起始位置上方 ==========']
        
        if self.axis_mode == 3:
            lines.extend([
                f'LinearMove(',
                f'    x={start_point[0]:.6f}, y={start_point[1]:.6f}, z=safe_z,',
                f'    f=feed_rapid',
                f')',
            ])
        else:
            lines.extend([
                f'FiveAxisMove(',
                f'    x={start_point[0]:.6f}, y={start_point[1]:.6f}, z=safe_z,',
                f'    i=0, j=0, k=-1,  # 垂直向下',
                f'    f=feed_rapid',
                f')',
            ])
        
        lines.extend(['', 'Dwell(0.2)  # 稳定', ''])
        return lines
    
    def _generate_approach(self, start_point: np.ndarray, start_normal: np.ndarray) -> List[str]:
        """生成下刀到起始点"""
        lines = ['# ========== 下刀到起始点 ==========']
        
        if self.axis_mode == 3:
            lines.extend([
                f'LinearMove(',
                f'    x={start_point[0]:.6f}, y={start_point[1]:.6f}, z={start_point[2]:.6f},',
                f'    f=feed_cut',
                f')',
            ])
        else:
            # 直接使用传入的刀轴方向（前端已处理好方向）
            tool_dir = start_normal
            lines.extend([
                f'FiveAxisMove(',
                f'    x={start_point[0]:.6f}, y={start_point[1]:.6f}, z={start_point[2]:.6f},',
                f'    i={tool_dir[0]:.6f}, j={tool_dir[1]:.6f}, k={tool_dir[2]:.6f},',
                f'    f=feed_cut',
                f')',
            ])
        
        lines.append('')
        return lines
    
    def _generate_cutting_path(self, points: np.ndarray, normals: np.ndarray) -> List[str]:
        """生成连续切削轨迹"""
        lines = [
            '# ========== 连续切削轨迹 ==========',
            'BeginContour()',
            ''
        ]
        
        # 生成每个刀位点
        for i, (point, normal) in enumerate(zip(points, normals)):
            # 每10个点添加一个注释
            if i % 10 == 0:
                lines.append(f'# 刀位点 {i+1}/{len(points)}')
            
            if self.axis_mode == 3:
                lines.append(
                    f'LinearMove('
                    f'x={point[0]:.6f}, y={point[1]:.6f}, z={point[2]:.6f}, '
                    f'f=feed_cut)'
                )
            else:
                # 直接使用传入的刀轴方向（前端已处理好方向）
                tool_dir = normal
                lines.append(
                    f'FiveAxisMove('
                    f'x={point[0]:.6f}, y={point[1]:.6f}, z={point[2]:.6f}, '
                    f'i={tool_dir[0]:.6f}, j={tool_dir[1]:.6f}, k={tool_dir[2]:.6f}, '
                    f'f=feed_cut)'
                )
        
        lines.extend([
            '',
            'EndContour()',
            ''
        ])
        
        return lines
    
    def _generate_retract(self, end_point: np.ndarray, safe_z: float) -> List[str]:
        """生成抬刀到安全高度"""
        lines = ['# ========== 抬刀到安全高度 ==========']
        
        if self.axis_mode == 3:
            lines.extend([
                f'LinearMove(',
                f'    x={end_point[0]:.6f}, y={end_point[1]:.6f}, z=safe_z,',
                f'    f=feed_rapid',
                f')',
            ])
        else:
            lines.extend([
                f'FiveAxisMove(',
                f'    x={end_point[0]:.6f}, y={end_point[1]:.6f}, z=safe_z,',
                f'    i=0, j=0, k=-1,  # 垂直向下',
                f'    f=feed_rapid',
                f')',
            ])
        
        lines.append('')
        return lines


def generate_motion_script(
    toolpath_points: np.ndarray,
    toolpath_normals: np.ndarray,
    output_path: str,
    feed_rapid: float = 3000.0,
    feed_cut: float = 300.0,
    retract_height: float = 5.0,
    axis_mode: int = 5,
    metadata: dict = None
) -> str:
    """
    便捷函数：生成运动脚本
    
    Args:
        toolpath_points: 刀轨点坐标 (N, 3)
        toolpath_normals: 刀轨法线 (N, 3)
        output_path: 输出文件路径
        feed_rapid: 快速移动进给率 mm/s
        feed_cut: 切削进给率 mm/s
        retract_height: 抬刀高度 mm
        axis_mode: 轴数模式 (3=三轴, 5=五轴)
        metadata: 元数据
        
    Returns:
        生成的脚本内容
    """
    generator = MotionScriptGenerator()
    generator.feed_rapid = feed_rapid
    generator.feed_cut = feed_cut
    generator.retract_height = retract_height
    generator.axis_mode = axis_mode
    
    return generator.generate_script(
        toolpath_points,
        toolpath_normals,
        output_path,
        metadata
    )
