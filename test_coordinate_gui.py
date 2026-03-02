#!/usr/bin/env python3
"""快速测试坐标系显示功能"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python_client'))

from PyQt5.QtWidgets import QApplication
from gui_client import CamGuiClient

def main():
    print("=" * 50)
    print("坐标系功能测试")
    print("=" * 50)
    print("\n测试要点:")
    print("1. 加载STEP文件 → 世界坐标系自动显示")
    print("2. 鼠标移动到坐标系上 → 不应崩溃")
    print("3. 设置自定义坐标系 → 拾取三个不共线的点")
    print("4. 尝试拾取重合点 → 应显示警告")
    print("5. 使用调整功能 → 世界坐标系保持可见")
    print("\n" + "=" * 50)
    
    app = QApplication(sys.argv)
    window = CamGuiClient()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
