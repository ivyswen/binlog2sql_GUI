#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel,
    QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
import pymysql
import os


class ConnectionDialog(QDialog):
    """数据库连接配置对话框"""

    def __init__(self, parent=None, connection_data=None):
        """
        初始化连接对话框

        Args:
            parent: 父窗口
            connection_data: 现有连接数据（用于编辑模式）
        """
        super().__init__(parent)
        self.connection_data = connection_data or {}
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("数据库连接配置")
        self.setModal(True)
        self.resize(400, 300)

        # 设置对话框图标
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                   "Resources", "favicon.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass  # 忽略图标设置错误

        # 主布局
        layout = QVBoxLayout(self)

        # 连接信息组
        conn_group = QGroupBox("连接信息")
        conn_layout = QFormLayout(conn_group)

        # 连接名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入连接名称")
        conn_layout.addRow("连接名称:", self.name_edit)

        # 主机地址
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        conn_layout.addRow("主机地址:", self.host_edit)

        # 端口
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(3306)
        conn_layout.addRow("端口:", self.port_spin)

        # 用户名
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("root")
        conn_layout.addRow("用户名:", self.user_edit)

        # 密码
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("输入密码")
        conn_layout.addRow("密码:", self.password_edit)

        # 字符集
        self.charset_edit = QLineEdit()
        self.charset_edit.setText("utf8")
        conn_layout.addRow("字符集:", self.charset_edit)

        layout.addWidget(conn_group)

        # 按钮布局
        button_layout = QHBoxLayout()

        # 测试连接按钮
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self.test_connection)
        button_layout.addWidget(self.test_btn)

        button_layout.addStretch()

        # 确定和取消按钮
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self.accept_connection)
        button_layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # 状态标签
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: blue;")
        layout.addWidget(self.status_label)

    def load_data(self):
        """加载现有连接数据"""
        if self.connection_data:
            self.name_edit.setText(self.connection_data.get("name", ""))
            self.host_edit.setText(self.connection_data.get("host", "127.0.0.1"))
            self.port_spin.setValue(self.connection_data.get("port", 3306))
            self.user_edit.setText(self.connection_data.get("user", "root"))
            self.password_edit.setText(self.connection_data.get("password", ""))
            self.charset_edit.setText(self.connection_data.get("charset", "utf8"))

            # 编辑模式下禁用名称编辑
            if "name" in self.connection_data:
                self.name_edit.setEnabled(False)

    def get_connection_info(self):
        """获取连接信息"""
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip() or "127.0.0.1",
            "port": self.port_spin.value(),
            "user": self.user_edit.text().strip() or "root",
            "password": self.password_edit.text(),
            "charset": self.charset_edit.text().strip() or "utf8"
        }

    def test_connection(self):
        """测试数据库连接"""
        self.status_label.setText("正在测试连接...")
        self.test_btn.setEnabled(False)

        try:
            conn_info = self.get_connection_info()

            # 验证必填字段
            if not conn_info["name"]:
                raise ValueError("连接名称不能为空")

            if not conn_info["host"]:
                raise ValueError("主机地址不能为空")

            if not conn_info["user"]:
                raise ValueError("用户名不能为空")

            # 测试连接
            connection = pymysql.connect(
                host=conn_info["host"],
                port=conn_info["port"],
                user=conn_info["user"],
                passwd=conn_info["password"],
                charset=conn_info["charset"],
                connect_timeout=5
            )
            connection.close()

            self.status_label.setText("连接测试成功！")
            self.status_label.setStyleSheet("color: green;")

        except ValueError as e:
            self.status_label.setText(f"输入错误: {str(e)}")
            self.status_label.setStyleSheet("color: red;")

        except Exception as e:
            self.status_label.setText(f"连接失败: {str(e)}")
            self.status_label.setStyleSheet("color: red;")

        finally:
            self.test_btn.setEnabled(True)

    def accept_connection(self):
        """确认连接配置"""
        try:
            conn_info = self.get_connection_info()

            # 验证必填字段
            if not conn_info["name"]:
                QMessageBox.warning(self, "警告", "连接名称不能为空")
                return

            if not conn_info["host"]:
                QMessageBox.warning(self, "警告", "主机地址不能为空")
                return

            if not conn_info["user"]:
                QMessageBox.warning(self, "警告", "用户名不能为空")
                return

            # 保存连接信息
            self.connection_result = conn_info
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存连接配置失败: {str(e)}")

    def get_result(self):
        """获取对话框结果"""
        return getattr(self, 'connection_result', None)
