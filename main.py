#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
from PySide6.QtWidgets import QApplication

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 初始化日志系统
from core.logger import setup_logger
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

    # 设置高DPI支持
    # PySide6中高DPI支持默认启用，无需手动设置
    # 如果需要禁用高DPI支持，可以使用环境变量 QT_AUTO_SCREEN_SCALE_FACTOR=0

    # 设置应用程序级别的字体策略，避免字体错误
    try:
        from PySide6.QtGui import QFont
        # 设置应用程序默认字体为安全的字体
        default_font = QFont()
        default_font.setStyleHint(QFont.StyleHint.SansSerif)
        default_font.setFamily("Microsoft YaHei UI")  # Windows 默认中文字体
        app.setFont(default_font)
        logger.info(f"设置应用程序默认字体: {default_font.family()}")
    except Exception as e:
        logger.warning(f"设置应用程序字体失败: {e}")
        # 继续运行，不影响主要功能

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
