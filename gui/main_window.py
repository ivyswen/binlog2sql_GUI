#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLineEdit, QSpinBox, QComboBox,
    QPushButton, QTextEdit, QCheckBox, QDateTimeEdit, QLabel,
    QMenuBar, QMenu, QMessageBox, QProgressBar, QListWidget,
    QListWidgetItem, QFileDialog, QDoubleSpinBox, QDialog,
    QApplication
)
from PySide6.QtCore import Qt, QDateTime, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.config_manager import ConfigManager
from gui.connection_dialog import ConnectionDialog
from gui.sql_highlighter import SqlHighlighter
from core.binlog_parser import BinlogParser
from core.logger import get_logger

# 获取logger实例
logger = get_logger("MainWindow")


class ParseWorker(QThread):
    """Binlog解析工作线程"""

    sql_generated = Signal(str)  # SQL生成信号
    error_occurred = Signal(str)  # 错误信号
    finished = Signal()  # 完成信号

    def __init__(self, parser):
        super().__init__()
        self.parser = parser
        self.is_running = True

    def run(self):
        """运行解析任务"""
        try:
            self.parser.process_binlog(callback=self.emit_sql)
            self.finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

    def emit_sql(self, sql):
        """发射SQL信号"""
        if self.is_running:
            self.sql_generated.emit(sql)

    def stop(self):
        """停止解析"""
        self.is_running = False


class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()
        logger.info("初始化主窗口")
        self.config_manager = ConfigManager()
        self.parse_worker = None
        self.setup_ui()
        self.load_settings()
        logger.info("主窗口初始化完成")

    def get_safe_monospace_font(self):
        """获取安全的等宽字体，带有回退机制"""
        # 定义等宽字体优先级列表
        font_candidates = [
            "Consolas",           # Windows 首选
            "Monaco",             # macOS 首选
            "DejaVu Sans Mono",   # Linux 常见
            "Liberation Mono",    # Linux 常见
            "Courier New",        # 跨平台通用
            "monospace"           # 系统默认等宽字体
        ]

        font_db = QFontDatabase()
        available_fonts = font_db.families()

        # 查找第一个可用的字体
        for font_name in font_candidates:
            if font_name in available_fonts or font_name == "monospace":
                font = QFont(font_name, 10)
                font.setStyleHint(QFont.StyleHint.Monospace)
                logger.info(f"使用字体: {font_name}")
                return font

        # 如果都不可用，使用系统默认等宽字体
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        logger.warning("使用系统默认等宽字体")
        return font

    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("Binlog2SQL GUI - MySQL Binlog解析工具")

        # 创建菜单栏
        self.create_menu_bar()

        # 创建中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧配置面板
        config_panel = self.create_config_panel()
        splitter.addWidget(config_panel)

        # 右侧结果面板
        result_panel = self.create_result_panel()
        splitter.addWidget(result_panel)

        # 设置分割器比例
        splitter.setSizes([400, 800])

        # 状态栏
        self.statusBar().showMessage("就绪")

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        # 导出结果
        export_action = QAction("导出结果(&E)", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.export_results)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        # 退出
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 连接菜单
        conn_menu = menubar.addMenu("连接(&C)")

        # 新建连接
        new_conn_action = QAction("新建连接(&N)", self)
        new_conn_action.setShortcut("Ctrl+N")
        new_conn_action.triggered.connect(self.new_connection)
        conn_menu.addAction(new_conn_action)

        # 编辑连接
        edit_conn_action = QAction("编辑连接(&E)", self)
        edit_conn_action.triggered.connect(self.edit_connection)
        conn_menu.addAction(edit_conn_action)

        # 删除连接
        del_conn_action = QAction("删除连接(&D)", self)
        del_conn_action.triggered.connect(self.delete_connection)
        conn_menu.addAction(del_conn_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        # 关于
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_config_panel(self):
        """创建配置面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 数据库连接组
        conn_group = QGroupBox("数据库连接")
        conn_layout = QFormLayout(conn_group)

        # 连接选择
        self.connection_combo = QComboBox()
        self.connection_combo.currentTextChanged.connect(self.on_connection_changed)
        conn_layout.addRow("连接:", self.connection_combo)

        # 连接管理按钮
        conn_btn_layout = QHBoxLayout()
        self.new_conn_btn = QPushButton("新建")
        self.new_conn_btn.clicked.connect(self.new_connection)
        self.edit_conn_btn = QPushButton("编辑")
        self.edit_conn_btn.clicked.connect(self.edit_connection)
        self.del_conn_btn = QPushButton("删除")
        self.del_conn_btn.clicked.connect(self.delete_connection)

        conn_btn_layout.addWidget(self.new_conn_btn)
        conn_btn_layout.addWidget(self.edit_conn_btn)
        conn_btn_layout.addWidget(self.del_conn_btn)
        conn_layout.addRow("管理:", conn_btn_layout)

        layout.addWidget(conn_group)

        # Binlog配置组
        binlog_group = QGroupBox("Binlog配置")
        binlog_layout = QFormLayout(binlog_group)

        # 起始文件
        self.start_file_edit = QLineEdit()
        self.start_file_edit.setPlaceholderText("例如: mysql-bin.000001")
        self.start_file_edit.setText("mysql-bin.142793")
        binlog_layout.addRow("起始文件:", self.start_file_edit)

        # 起始位置
        self.start_pos_spin = QSpinBox()
        self.start_pos_spin.setRange(4, 999999999)
        self.start_pos_spin.setValue(4)
        binlog_layout.addRow("起始位置:", self.start_pos_spin)

        # 结束文件
        self.end_file_edit = QLineEdit()
        self.end_file_edit.setPlaceholderText("留空表示与起始文件相同")
        self.end_file_edit.setText("mysql-bin.142794")
        binlog_layout.addRow("结束文件:", self.end_file_edit)

        # 结束位置
        self.end_pos_spin = QSpinBox()
        self.end_pos_spin.setRange(0, 999999999)
        self.end_pos_spin.setValue(0)
        self.end_pos_spin.setSpecialValueText("最新位置")
        binlog_layout.addRow("结束位置:", self.end_pos_spin)

        layout.addWidget(binlog_group)

        # 时间过滤组
        time_group = QGroupBox("时间过滤")
        time_layout = QFormLayout(time_group)

        # 时间过滤开关
        self.enable_time_filter = QCheckBox("启用时间过滤")
        self.enable_time_filter.setChecked(True)
        self.enable_time_filter.toggled.connect(self.on_time_filter_toggled)
        time_layout.addRow("", self.enable_time_filter)

        # 开始时间
        self.start_time_edit = QDateTimeEdit()
        self.start_time_edit.setDateTime(QDateTime.currentDateTime().addDays(-1))
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        self.start_time_edit.setCalendarPopup(True)
        time_layout.addRow("开始时间:", self.start_time_edit)

        # 结束时间
        self.end_time_edit = QDateTimeEdit()
        self.end_time_edit.setDateTime(QDateTime.currentDateTime())
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        self.end_time_edit.setCalendarPopup(True)
        time_layout.addRow("结束时间:", self.end_time_edit)

        layout.addWidget(time_group)

        # 过滤选项组
        filter_group = QGroupBox("过滤选项")
        filter_layout = QFormLayout(filter_group)

        # 数据库过滤
        self.databases_edit = QLineEdit()
        self.databases_edit.setText("tmsp")
        self.databases_edit.setPlaceholderText("多个数据库用空格分隔")
        filter_layout.addRow("数据库:", self.databases_edit)

        # 表过滤
        self.tables_edit = QLineEdit()
        self.tables_edit.setText("tmsp_send_trans_turn")
        self.tables_edit.setPlaceholderText("多个表用空格分隔")
        filter_layout.addRow("表:", self.tables_edit)

        layout.addWidget(filter_group)

        # 解析选项组
        parse_group = QGroupBox("解析选项")
        parse_layout = QFormLayout(parse_group)

        # SQL类型
        sql_type_layout = QHBoxLayout()
        self.insert_check = QCheckBox("INSERT")
        self.insert_check.setChecked(True)
        self.update_check = QCheckBox("UPDATE")
        self.update_check.setChecked(True)
        self.delete_check = QCheckBox("DELETE")
        self.delete_check.setChecked(True)

        sql_type_layout.addWidget(self.insert_check)
        sql_type_layout.addWidget(self.update_check)
        sql_type_layout.addWidget(self.delete_check)
        parse_layout.addRow("SQL类型:", sql_type_layout)

        # 其他选项
        self.only_dml_check = QCheckBox("只显示DML语句")
        self.only_dml_check.setChecked(True)
        parse_layout.addRow("", self.only_dml_check)

        self.flashback_check = QCheckBox("生成回滚SQL")
        parse_layout.addRow("", self.flashback_check)

        self.no_pk_check = QCheckBox("不包含主键")
        parse_layout.addRow("", self.no_pk_check)

        # 回滚间隔
        self.back_interval_spin = QDoubleSpinBox()
        self.back_interval_spin.setRange(0.0, 60.0)
        self.back_interval_spin.setValue(1.0)
        self.back_interval_spin.setSuffix(" 秒")
        parse_layout.addRow("回滚间隔:", self.back_interval_spin)

        layout.addWidget(parse_group)

        # 控制按钮
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始解析")
        self.start_btn.clicked.connect(self.start_parse)
        self.stop_btn = QPushButton("停止解析")
        self.stop_btn.clicked.connect(self.stop_parse)
        self.stop_btn.setEnabled(False)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        layout.addLayout(control_layout)

        layout.addStretch()

        return panel

    def create_result_panel(self):
        """创建结果面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 结果显示组
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_results)
        toolbar_layout.addWidget(self.clear_btn)

        self.copy_btn = QPushButton("复制全部")
        self.copy_btn.clicked.connect(self.copy_results)
        toolbar_layout.addWidget(self.copy_btn)

        self.save_btn = QPushButton("保存到文件")
        self.save_btn.clicked.connect(self.save_results)
        toolbar_layout.addWidget(self.save_btn)

        toolbar_layout.addStretch()

        # SQL计数标签
        self.sql_count_label = QLabel("SQL语句数: 0")
        toolbar_layout.addWidget(self.sql_count_label)

        result_layout.addLayout(toolbar_layout)

        # 结果文本框
        self.result_text = QTextEdit()
        # 使用安全的等宽字体，带有回退机制
        monospace_font = self.get_safe_monospace_font()
        self.result_text.setFont(monospace_font)
        self.result_text.setReadOnly(True)

        # 应用SQL语法高亮
        self.sql_highlighter = SqlHighlighter(self.result_text.document())

        result_layout.addWidget(self.result_text)

        layout.addWidget(result_group)

        return panel

    def load_settings(self):
        """加载设置"""
        # 加载窗口设置
        window_settings = self.config_manager.get_window_settings()
        self.resize(window_settings["width"], window_settings["height"])
        if window_settings["maximized"]:
            self.showMaximized()

        # 加载连接列表
        self.refresh_connections()

        # 加载解析设置
        parse_settings = self.config_manager.get_parse_settings()
        sql_types = parse_settings.get("sql_types", ["INSERT", "UPDATE", "DELETE"])

        self.insert_check.setChecked("INSERT" in sql_types)
        self.update_check.setChecked("UPDATE" in sql_types)
        self.delete_check.setChecked("DELETE" in sql_types)
        self.only_dml_check.setChecked(parse_settings.get("only_dml", True))
        self.flashback_check.setChecked(parse_settings.get("flashback", False))
        self.no_pk_check.setChecked(parse_settings.get("no_pk", False))
        self.back_interval_spin.setValue(parse_settings.get("back_interval", 1.0))

        # 加载时间过滤设置
        enable_time_filter = parse_settings.get("enable_time_filter", True)
        self.enable_time_filter.setChecked(enable_time_filter)
        self.on_time_filter_toggled(enable_time_filter)  # 触发状态更新

    def save_settings(self):
        """保存设置"""
        # 保存窗口设置
        self.config_manager.set_window_settings(
            self.width(),
            self.height(),
            self.isMaximized()
        )

        # 保存解析设置
        sql_types = []
        if self.insert_check.isChecked():
            sql_types.append("INSERT")
        if self.update_check.isChecked():
            sql_types.append("UPDATE")
        if self.delete_check.isChecked():
            sql_types.append("DELETE")

        parse_settings = {
            "sql_types": sql_types,
            "only_dml": self.only_dml_check.isChecked(),
            "flashback": self.flashback_check.isChecked(),
            "no_pk": self.no_pk_check.isChecked(),
            "back_interval": self.back_interval_spin.value(),
            "enable_time_filter": self.enable_time_filter.isChecked()
        }
        self.config_manager.set_parse_settings(parse_settings)

    def refresh_connections(self):
        """刷新连接列表"""
        self.connection_combo.clear()
        connections = self.config_manager.get_all_connections()

        if connections:
            self.connection_combo.addItems(connections.keys())

            # 选择最后使用的连接
            last_conn = self.config_manager.get_last_connection()
            if last_conn and last_conn in connections:
                self.connection_combo.setCurrentText(last_conn)

        # 更新按钮状态
        has_connections = len(connections) > 0
        self.edit_conn_btn.setEnabled(has_connections)
        self.del_conn_btn.setEnabled(has_connections)

    def on_connection_changed(self, connection_name):
        """连接改变事件"""
        if connection_name:
            self.config_manager.set_last_connection(connection_name)

    def on_time_filter_toggled(self, checked):
        """时间过滤开关切换事件"""
        self.start_time_edit.setEnabled(checked)
        self.end_time_edit.setEnabled(checked)

        if checked:
            logger.info("启用时间过滤")
        else:
            logger.info("禁用时间过滤")

    def new_connection(self):
        """新建连接"""
        dialog = ConnectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            conn_info = dialog.get_result()
            if conn_info:
                # 检查连接名是否已存在
                if self.config_manager.connection_exists(conn_info["name"]):
                    QMessageBox.warning(self, "警告", "连接名称已存在，请使用其他名称")
                    return

                # 保存连接
                self.config_manager.add_connection(conn_info["name"], conn_info)
                self.refresh_connections()
                self.connection_combo.setCurrentText(conn_info["name"])

                QMessageBox.information(self, "成功", "连接配置已保存")

    def edit_connection(self):
        """编辑连接"""
        current_name = self.connection_combo.currentText()
        if not current_name:
            QMessageBox.warning(self, "警告", "请先选择要编辑的连接")
            return

        conn_info = self.config_manager.get_connection(current_name)
        if not conn_info:
            QMessageBox.warning(self, "警告", "连接信息不存在")
            return

        # 添加连接名到数据中
        conn_info["name"] = current_name

        dialog = ConnectionDialog(self, conn_info)
        if dialog.exec() == QDialog.Accepted:
            new_conn_info = dialog.get_result()
            if new_conn_info:
                self.config_manager.update_connection(current_name, new_conn_info)
                QMessageBox.information(self, "成功", "连接配置已更新")

    def delete_connection(self):
        """删除连接"""
        current_name = self.connection_combo.currentText()
        if not current_name:
            QMessageBox.warning(self, "警告", "请先选择要删除的连接")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除连接 '{current_name}' 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.config_manager.remove_connection(current_name)
            self.refresh_connections()
            QMessageBox.information(self, "成功", "连接已删除")

    def start_parse(self):
        """开始解析binlog"""
        logger.info("用户开始解析binlog")

        # 验证输入
        current_conn = self.connection_combo.currentText()
        if not current_conn:
            logger.warning("未选择数据库连接")
            QMessageBox.warning(self, "警告", "请先选择数据库连接")
            return

        start_file = self.start_file_edit.text().strip()
        if not start_file:
            logger.warning("未输入起始binlog文件")
            QMessageBox.warning(self, "警告", "请输入起始binlog文件")
            return

        # 获取连接信息
        conn_info = self.config_manager.get_connection(current_conn)
        if not conn_info:
            QMessageBox.warning(self, "警告", "连接信息不存在")
            return

        try:
            # 准备解析参数
            connection_settings = {
                'host': conn_info['host'],
                'port': conn_info['port'],
                'user': conn_info['user'],
                'passwd': conn_info['password'],
                'charset': conn_info['charset']
            }

            # 获取SQL类型
            sql_types = []
            if self.insert_check.isChecked():
                sql_types.append("INSERT")
            if self.update_check.isChecked():
                sql_types.append("UPDATE")
            if self.delete_check.isChecked():
                sql_types.append("DELETE")

            if not sql_types:
                QMessageBox.warning(self, "警告", "请至少选择一种SQL类型")
                return

            # 获取时间范围
            if self.enable_time_filter.isChecked():
                start_time = self.start_time_edit.dateTime().toString("yyyy-MM-dd hh:mm:ss")
                end_time = self.end_time_edit.dateTime().toString("yyyy-MM-dd hh:mm:ss")
                logger.info(f"使用时间过滤: {start_time} - {end_time}")
            else:
                start_time = None
                end_time = None
                logger.info("时间过滤已禁用，将解析所有时间范围的数据")

            # 获取过滤条件
            databases = self.databases_edit.text().strip().split() if self.databases_edit.text().strip() else None
            tables = self.tables_edit.text().strip().split() if self.tables_edit.text().strip() else None

            # 创建解析器
            parser = BinlogParser(
                connection_settings=connection_settings,
                start_file=start_file,
                start_pos=self.start_pos_spin.value(),
                end_file=self.end_file_edit.text().strip() or None,
                end_pos=self.end_pos_spin.value() if self.end_pos_spin.value() > 0 else None,
                start_time=start_time,
                stop_time=end_time,
                only_schemas=databases,
                only_tables=tables,
                no_pk=self.no_pk_check.isChecked(),
                flashback=self.flashback_check.isChecked(),
                stop_never=False,
                back_interval=self.back_interval_spin.value(),
                only_dml=self.only_dml_check.isChecked(),
                sql_type=sql_types
            )

            # 清空结果
            self.clear_results()

            # 创建工作线程
            self.parse_worker = ParseWorker(parser)
            self.parse_worker.sql_generated.connect(self.on_sql_generated)
            self.parse_worker.error_occurred.connect(self.on_parse_error)
            self.parse_worker.finished.connect(self.on_parse_finished)

            # 更新UI状态
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # 不确定进度
            self.statusBar().showMessage("正在解析binlog...")

            # 启动解析
            self.parse_worker.start()
            logger.info("解析任务已启动")

        except Exception as e:
            logger.error(f"启动解析失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"启动解析失败: {str(e)}")

    def stop_parse(self):
        """停止解析"""
        logger.info("用户停止解析")
        if self.parse_worker and self.parse_worker.isRunning():
            self.parse_worker.stop()
            self.parse_worker.wait(3000)  # 等待3秒
            if self.parse_worker.isRunning():
                logger.warning("解析线程未正常停止，强制终止")
                self.parse_worker.terminate()

        self.on_parse_finished()

    def on_sql_generated(self, sql):
        """处理生成的SQL"""
        self.result_text.append(sql)

        # 更新计数
        current_count = int(self.sql_count_label.text().split(": ")[1])
        self.sql_count_label.setText(f"SQL语句数: {current_count + 1}")

    def on_parse_error(self, error_msg):
        """处理解析错误"""
        logger.error(f"解析过程中发生错误: {error_msg}")
        QMessageBox.critical(self, "解析错误", error_msg)
        self.on_parse_finished()

    def on_parse_finished(self):
        """解析完成"""
        logger.info("解析任务完成")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage("解析完成")

        if self.parse_worker:
            self.parse_worker = None

    def clear_results(self):
        """清空结果"""
        self.result_text.clear()
        self.sql_count_label.setText("SQL语句数: 0")

    def copy_results(self):
        """复制全部结果"""
        text = self.result_text.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.statusBar().showMessage("结果已复制到剪贴板", 2000)
        else:
            QMessageBox.information(self, "提示", "没有可复制的内容")

    def save_results(self):
        """保存结果到文件"""
        text = self.result_text.toPlainText()
        if not text:
            QMessageBox.information(self, "提示", "没有可保存的内容")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "保存结果",
            f"binlog_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
            "SQL文件 (*.sql);;文本文件 (*.txt);;所有文件 (*.*)"
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(text)
                QMessageBox.information(self, "成功", f"结果已保存到: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存文件失败: {str(e)}")

    def export_results(self):
        """导出结果（菜单项）"""
        self.save_results()

    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于",
            "Binlog2SQL GUI v1.0\n\n"
            "基于PySide6开发的MySQL Binlog解析工具\n"
            "核心解析功能基于binlog2sql项目\n\n"
            "功能特性：\n"
            "• 图形化配置界面\n"
            "• 数据库连接管理\n"
            "• 实时解析显示\n"
            "• 支持回滚SQL生成\n"
            "• 结果导出功能"
        )

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止解析任务
        if self.parse_worker and self.parse_worker.isRunning():
            self.stop_parse()

        # 保存设置
        self.save_settings()

        event.accept()
