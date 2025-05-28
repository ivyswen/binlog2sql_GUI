#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 初始化日志系统
from core.logger import setup_logger, get_logger
logger = setup_logger()

from gui.main_window import MainWindow


def main():
    """主函数"""
    # 创建应用程序
    app = QApplication(sys.argv)

    # 设置应用程序信息
    app.setApplicationName("Binlog2SQL GUI")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Binlog2SQL")

    # 设置高DPI支持（PySide6中这些属性已弃用，但保留以兼容旧版本）
    try:
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        # PySide6中这些属性可能不存在
        pass

    try:
        logger.info("创建主窗口")
        # 创建主窗口
        window = MainWindow()
        window.show()

        logger.info("应用程序启动成功")
        # 运行应用程序
        sys.exit(app.exec())

    except Exception as e:
        logger.error(f"应用程序启动失败: {str(e)}")
        print(f"应用程序启动失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
