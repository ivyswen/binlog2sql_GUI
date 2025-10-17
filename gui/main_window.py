#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime
import pymysql
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLineEdit, QSpinBox, QComboBox,
    QPushButton, QTextEdit, QCheckBox, QDateTimeEdit, QLabel,
    QMenuBar, QMenu, QMessageBox, QProgressBar, QListWidget,
    QListWidgetItem, QFileDialog, QDoubleSpinBox, QDialog,
    QApplication
)
from PySide6.QtCore import Qt, QDateTime, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase, QIcon

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
    progress_updated = Signal(int, str)  # 进度更新信号 (百分比, 状态信息)

    def __init__(self, parser):
        super().__init__()
        self.parser = parser
        self.is_running = True
        self.total_files = 0
        self.current_file_index = 0
        self.current_file_name = ""

    def run(self):
        """运行解析任务"""
        try:
            logger.info("ParseWorker开始运行")

            # 获取要解析的binlog文件范围
            start_file = self.parser.start_file
            end_file = self.parser.end_file or start_file
            logger.info(f"解析文件范围: {start_file} 到 {end_file}")

            # 获取所有可用的binlog文件
            try:
                all_binlog_files = self.parser.get_binlog_files()
                logger.info(f"获取到的binlog文件列表: {all_binlog_files}")
            except Exception as e:
                logger.error(f"获取binlog文件列表失败: {str(e)}")
                # 使用解析器内部的binlog列表作为备选
                all_binlog_files = self.parser.binlog_list
                logger.info(f"使用解析器内部的binlog列表: {all_binlog_files}")

            # 计算要处理的文件范围
            if start_file in all_binlog_files and end_file in all_binlog_files:
                start_index = all_binlog_files.index(start_file)
                end_index = all_binlog_files.index(end_file)
                self.file_range = all_binlog_files[start_index:end_index + 1]
                self.total_files = len(self.file_range)
                logger.info(f"计算出的文件范围: {self.file_range}, 总文件数: {self.total_files}")
            else:
                # 如果文件不在列表中，使用解析器内部的binlog列表
                if hasattr(self.parser, 'binlogList') and self.parser.binlogList:
                    self.file_range = self.parser.binlogList
                    self.total_files = len(self.file_range)
                    logger.info(f"使用解析器内部binlog列表: {self.file_range}, 总文件数: {self.total_files}")
                else:
                    # 最后的备选方案
                    self.file_range = [start_file]
                    self.total_files = 1
                    logger.warning(f"无法获取文件列表，使用单文件模式: {self.file_range}")

            self.progress_updated.emit(0, f"准备解析 {self.total_files} 个binlog文件: {start_file} 到 {end_file}")

            # 设置进度回调
            logger.info("设置进度回调函数")
            self.parser.set_progress_callback(self.update_progress)

            logger.info("开始调用process_binlog")
            self.parser.process_binlog(callback=self.emit_sql)
            self.progress_updated.emit(100, "解析完成")
            self.finished.emit()
        except Exception as e:
            logger.error(f"ParseWorker运行时发生错误: {str(e)}")
            self.error_occurred.emit(str(e))

    def update_progress(self, current_file_name):
        """更新进度 - 仅基于binlog文件数量计算"""
        try:
            # 动态扩展文件范围以适应实际解析的文件
            if hasattr(self, 'file_range') and current_file_name not in self.file_range:
                # 如果当前文件不在范围内，动态添加到范围中
                self.file_range.append(current_file_name)
                self.total_files = len(self.file_range)
                logger.info(f"动态扩展文件范围，新增文件: {current_file_name}, 总文件数: {self.total_files}")

            # 计算进度
            if hasattr(self, 'file_range') and current_file_name in self.file_range:
                current_file_index = self.file_range.index(current_file_name)
                # 简单的文件进度：每个文件占用相等的进度空间
                progress = (current_file_index / max(self.total_files, 1)) * 100
                status_msg = f"正在解析: {current_file_name} ({current_file_index + 1}/{self.total_files})"
            else:
                # 如果仍然无法计算，显示基本进度
                progress = 50  # 显示50%作为默认进度
                status_msg = f"正在解析: {current_file_name}"
                logger.warning(f"无法计算进度，使用默认进度50%")

            # 确保进度在合理范围内
            progress = max(0, min(int(progress), 95))  # 最大95%，留5%给完成

            # 发射进度信号
            self.progress_updated.emit(progress, status_msg)

        except Exception as e:
            # 进度更新失败时发送基本信号
            logger.warning(f"更新进度时发生错误: {str(e)}")
            try:
                self.progress_updated.emit(10, f"正在解析: {current_file_name}")
            except:
                pass

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

        # SQL批量更新相关
        self.sql_buffer = []  # SQL缓冲区
        self.sql_count = 0    # SQL计数
        self.batch_size = 50  # 批量大小
        self.update_timer = QTimer()  # 定时器
        self.update_timer.timeout.connect(self.flush_sql_buffer)
        self.update_timer.setSingleShot(False)

        # SQL关键字过滤相关
        self.keyword_filters = []  # 关键字过滤列表
        self.filtered_sql_count = 0  # 被过滤的SQL计数
        self.matched_sql_count = 0  # 匹配的SQL计数

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

    def set_window_icon(self):
        """设置窗口图标"""
        try:
            # 获取图标文件路径
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "Resources", "favicon.ico")

            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                self.setWindowIcon(icon)
                logger.info(f"成功设置窗口图标: {icon_path}")
            else:
                logger.warning(f"图标文件不存在: {icon_path}")
        except Exception as e:
            logger.error(f"设置窗口图标失败: {str(e)}")

    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("MySQL Binlog解析工具")

        # 设置窗口图标
        self.set_window_icon()

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

        # 起始文件 - 改为QComboBox
        self.start_file_combo = QComboBox()
        self.start_file_combo.setEditable(True)
        self.start_file_combo.setPlaceholderText("例如: mysql-bin.000001")
        binlog_layout.addRow("起始文件:", self.start_file_combo)

        # 起始位置
        self.start_pos_spin = QSpinBox()
        self.start_pos_spin.setRange(4, 999999999)
        self.start_pos_spin.setValue(4)
        binlog_layout.addRow("起始位置:", self.start_pos_spin)

        # 结束文件 - 改为QComboBox
        self.end_file_combo = QComboBox()
        self.end_file_combo.setEditable(True)
        self.end_file_combo.setPlaceholderText("留空表示与起始文件相同")
        binlog_layout.addRow("结束文件:", self.end_file_combo)

        # 结束位置
        self.end_pos_spin = QSpinBox()
        self.end_pos_spin.setRange(0, 999999999)
        self.end_pos_spin.setValue(0)
        self.end_pos_spin.setSpecialValueText("最新位置")
        binlog_layout.addRow("结束位置:", self.end_pos_spin)

        # 获取Binlog文件列表按钮
        fetch_binlog_layout = QHBoxLayout()
        self.fetch_binlog_btn = QPushButton("获取Binlog文件列表")
        self.fetch_binlog_btn.clicked.connect(self.on_fetch_binlog_files)
        fetch_binlog_layout.addWidget(self.fetch_binlog_btn)
        fetch_binlog_layout.addStretch()
        binlog_layout.addRow("", fetch_binlog_layout)

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
        # self.databases_edit.setText("tmsp")
        self.databases_edit.setPlaceholderText("多个数据库用空格分隔")
        filter_layout.addRow("数据库:", self.databases_edit)

        # 表过滤
        self.tables_edit = QLineEdit()
        # self.tables_edit.setText("tmsp_send_trans_turn")
        self.tables_edit.setPlaceholderText("多个表用空格分隔")
        filter_layout.addRow("表:", self.tables_edit)

        # SQL关键字过滤
        keyword_filter_layout = QHBoxLayout()
        self.enable_keyword_filter = QCheckBox("启用关键字过滤")
        self.enable_keyword_filter.setChecked(False)
        keyword_filter_layout.addWidget(self.enable_keyword_filter)

        self.keyword_filter_edit = QLineEdit()
        self.keyword_filter_edit.setPlaceholderText("输入关键字，多个关键字用空格分隔（如：UPDATE DELETE）")
        self.keyword_filter_edit.setEnabled(False)
        keyword_filter_layout.addWidget(self.keyword_filter_edit)

        # 连接复选框信号以启用/禁用文本框
        self.enable_keyword_filter.toggled.connect(self.keyword_filter_edit.setEnabled)

        filter_layout.addRow("关键字过滤:", keyword_filter_layout)

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

        # 加载关键字过滤设置
        enable_keyword_filter = parse_settings.get("enable_keyword_filter", False)
        self.enable_keyword_filter.setChecked(enable_keyword_filter)
        keyword_filter_text = parse_settings.get("keyword_filter_text", "")
        self.keyword_filter_edit.setText(keyword_filter_text)
        self.keyword_filter_edit.setEnabled(enable_keyword_filter)

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
            "enable_time_filter": self.enable_time_filter.isChecked(),
            "enable_keyword_filter": self.enable_keyword_filter.isChecked(),
            "keyword_filter_text": self.keyword_filter_edit.text()
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
            # 清空binlog文件下拉框，提示用户需要重新获取
            self.start_file_combo.clear()
            self.end_file_combo.clear()
            logger.info(f"连接已改变为: {connection_name}，已清空binlog文件列表")

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

    def on_fetch_binlog_files(self):
        """获取Binlog文件列表"""
        logger.info("用户点击获取Binlog文件列表按钮")

        # 验证连接
        current_conn = self.connection_combo.currentText()
        if not current_conn:
            logger.warning("未选择数据库连接")
            QMessageBox.warning(self, "警告", "请先选择数据库连接")
            return

        # 获取连接信息
        conn_info = self.config_manager.get_connection(current_conn)
        if not conn_info:
            QMessageBox.warning(self, "警告", "连接信息不存在")
            return

        try:
            # 更新按钮状态
            self.fetch_binlog_btn.setEnabled(False)
            self.fetch_binlog_btn.setText("获取中...")
            QApplication.processEvents()

            # 准备连接配置
            connection_settings = {
                'host': conn_info['host'],
                'port': conn_info['port'],
                'user': conn_info['user'],
                'passwd': conn_info['password'],
                'charset': conn_info['charset']
            }

            # 第一步：先通过直接SQL查询获取第一个可用的binlog文件
            logger.info(f"正在查询第一个可用的binlog文件: {conn_info['host']}:{conn_info['port']}")

            first_binlog_file = None
            temp_connection = None
            try:
                # 创建临时连接以查询binlog文件列表
                temp_connection = pymysql.connect(
                    host=conn_info['host'],
                    port=conn_info['port'],
                    user=conn_info['user'],
                    password=conn_info['password'],
                    charset=conn_info['charset']
                )

                with temp_connection.cursor() as cursor:
                    # 执行SHOW MASTER LOGS查询
                    cursor.execute("SHOW MASTER LOGS")
                    rows = cursor.fetchall()

                    if rows:
                        # 获取第一个binlog文件名
                        first_binlog_file = rows[0][0]
                        logger.info(f"查询到第一个binlog文件: {first_binlog_file}")
                    else:
                        raise Exception("未找到任何binlog文件")
            finally:
                if temp_connection:
                    temp_connection.close()

            # 第二步：使用获取到的第一个binlog文件创建临时解析器
            logger.info(f"创建临时解析器以获取binlog文件列表，使用start_file: {first_binlog_file}")

            temp_parser = BinlogParser(
                connection_settings=connection_settings,
                start_file=first_binlog_file,  # 使用查询到的第一个文件
                start_pos=4
            )

            # 获取binlog文件列表
            binlog_files = temp_parser.get_binlog_files()
            logger.info(f"成功获取binlog文件列表: {binlog_files}")

            if not binlog_files:
                QMessageBox.warning(self, "警告", "未找到任何binlog文件")
                self.fetch_binlog_btn.setEnabled(True)
                self.fetch_binlog_btn.setText("获取Binlog文件列表")
                return

            # 清空并填充下拉框
            self.start_file_combo.clear()
            self.end_file_combo.clear()

            for binlog_file in binlog_files:
                self.start_file_combo.addItem(binlog_file)
                self.end_file_combo.addItem(binlog_file)

            # 设置默认值：开始文件选择第一个，结束文件选择最后一个
            self.start_file_combo.setCurrentIndex(0)
            self.end_file_combo.setCurrentIndex(len(binlog_files) - 1)

            logger.info(f"已填充binlog文件列表，共{len(binlog_files)}个文件")

            # 显示成功提示
            QMessageBox.information(
                self, "成功",
                f"已获取{len(binlog_files)}个binlog文件\n"
                f"开始文件: {binlog_files[0]}\n"
                f"结束文件: {binlog_files[-1]}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"获取binlog文件列表失败: {error_msg}")
            QMessageBox.critical(self, "错误", f"获取binlog文件列表失败:\n{error_msg}")

        finally:
            # 恢复按钮状态
            self.fetch_binlog_btn.setEnabled(True)
            self.fetch_binlog_btn.setText("获取Binlog文件列表")

    def start_parse(self):
        """开始解析binlog"""
        logger.info("用户开始解析binlog")

        # 验证输入
        current_conn = self.connection_combo.currentText()
        if not current_conn:
            logger.warning("未选择数据库连接")
            QMessageBox.warning(self, "警告", "请先选择数据库连接")
            return

        start_file = self.start_file_combo.currentText().strip()
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
                end_file=self.end_file_combo.currentText().strip() or None,
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

            # 初始化关键字过滤（必须在clear_results()之后）
            logger.info("开始初始化关键字过滤")
            if self.enable_keyword_filter.isChecked():
                # 获取关键字过滤条件
                keyword_text = self.keyword_filter_edit.text().strip()
                logger.info(f"关键字过滤已启用，输入的关键字文本: '{keyword_text}'")
                if keyword_text:
                    # 支持空格和逗号分隔
                    keywords = [kw.strip().upper() for kw in keyword_text.replace(',', ' ').split()]
                    self.keyword_filters = [kw for kw in keywords if kw]  # 过滤空字符串

                    if self.keyword_filters:
                        logger.info(f"✓ 关键字过滤初始化成功，关键字列表: {self.keyword_filters}")
                    else:
                        logger.warning("关键字过滤已启用但未输入有效关键字")
                else:
                    logger.warning("关键字过滤已启用但未输入关键字")
            else:
                logger.info("关键字过滤未启用")

            # 创建工作线程
            self.parse_worker = ParseWorker(parser)
            self.parse_worker.sql_generated.connect(self.on_sql_generated)
            self.parse_worker.error_occurred.connect(self.on_parse_error)
            self.parse_worker.finished.connect(self.on_parse_finished)
            self.parse_worker.progress_updated.connect(self.on_progress_updated)

            # 更新UI状态
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 100)  # 设置为百分比进度
            self.progress_bar.setValue(0)
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
        """处理生成的SQL - 使用批量更新机制"""
        # 检查是否需要进行关键字过滤
        if self.enable_keyword_filter.isChecked() and self.keyword_filters:
            # 如果启用了关键字过滤，检查SQL是否包含任意一个关键字（OR逻辑）
            sql_upper = sql.upper()
            matched = any(keyword in sql_upper for keyword in self.keyword_filters)

            if not matched:
                # SQL不匹配任何关键字，跳过此SQL
                self.filtered_sql_count += 1
                # 每过滤100条SQL记录一次日志
                if self.filtered_sql_count % 100 == 0:
                    logger.debug(f"已过滤 {self.filtered_sql_count} 条SQL")
                return
            else:
                # SQL匹配关键字，计数
                self.matched_sql_count += 1
                # 每匹配10条SQL记录一次日志
                if self.matched_sql_count % 10 == 0:
                    logger.debug(f"已匹配 {self.matched_sql_count} 条SQL")

        # 添加到缓冲区
        self.sql_buffer.append(sql)
        self.sql_count += 1

        # 如果缓冲区达到批量大小，立即刷新
        if len(self.sql_buffer) >= self.batch_size:
            self.flush_sql_buffer()
        else:
            # 启动定时器，确保即使没有达到批量大小也会定期更新
            if not self.update_timer.isActive():
                self.update_timer.start(200)  # 200毫秒后更新

    def flush_sql_buffer(self):
        """刷新SQL缓冲区到UI"""
        if not self.sql_buffer:
            return

        # 停止定时器
        self.update_timer.stop()

        try:
            # 临时禁用语法高亮以提高性能
            highlighter = self.sql_highlighter
            if hasattr(self, 'sql_highlighter'):
                self.sql_highlighter = None

            # 批量添加SQL到文本框
            cursor = self.result_text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)

            # 将所有SQL合并为一个字符串，减少UI更新次数
            batch_text = '\n'.join(self.sql_buffer)
            if self.result_text.toPlainText():
                batch_text = '\n' + batch_text

            cursor.insertText(batch_text)

            # 更新计数
            self.sql_count_label.setText(f"SQL语句数: {self.sql_count}")

            # 清空缓冲区
            self.sql_buffer.clear()

            # 重新启用语法高亮
            if hasattr(self, 'sql_highlighter'):
                self.sql_highlighter = highlighter

            # 滚动到底部
            scrollbar = self.result_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            logger.warning(f"刷新SQL缓冲区时发生错误: {str(e)}")
            # 确保缓冲区被清空，避免内存泄漏
            self.sql_buffer.clear()

    def on_parse_error(self, error_msg):
        """处理解析错误"""
        logger.error(f"解析过程中发生错误: {error_msg}")
        QMessageBox.critical(self, "解析错误", error_msg)
        self.on_parse_finished()

    def on_progress_updated(self, percentage, status_msg):
        """处理进度更新"""
        self.progress_bar.setValue(percentage)
        self.statusBar().showMessage(status_msg)

    def on_parse_finished(self):
        """解析完成"""
        logger.info("解析任务完成")

        # 刷新剩余的SQL缓冲区
        self.flush_sql_buffer()

        # 记录过滤统计信息
        logger.info(f"检查关键字过滤状态 - 启用: {self.enable_keyword_filter.isChecked()}, 关键字列表: {self.keyword_filters}")
        if self.enable_keyword_filter.isChecked() and self.keyword_filters:
            total_processed = self.matched_sql_count + self.filtered_sql_count
            logger.info(f"✓ 关键字过滤统计 - 总处理: {total_processed}, 匹配: {self.matched_sql_count}, 过滤: {self.filtered_sql_count}")
            if self.matched_sql_count == 0:
                logger.warning("未找到匹配关键字的SQL语句")
        elif self.enable_keyword_filter.isChecked() and not self.keyword_filters:
            logger.warning("关键字过滤已启用但关键字列表为空")
        else:
            logger.info("关键字过滤未启用")

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

        # 重置批量更新相关状态
        self.sql_buffer.clear()
        self.sql_count = 0
        self.update_timer.stop()

        # 重置过滤相关状态
        self.keyword_filters = []
        self.filtered_sql_count = 0
        self.matched_sql_count = 0

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
