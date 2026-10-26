#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
大事务分析 GUI 模块
提供大事务分析的配置、执行、Master-Detail 结果展示与导出。
"""

import csv
import pymysql
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QPushButton,
    QProgressBar,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QMessageBox,
    QFileDialog,
    QMenu,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QAction, QGuiApplication

from core.bigtxn_analyzer import BigTxnAnalyzer
from core.logger import get_logger

logger = get_logger("BigTxnWidget")


class NumericTableWidgetItem(QTableWidgetItem):
    """支持数字排序的表格项"""

    def __init__(self, value, display_text=None):
        text = str(display_text if display_text is not None else value)
        super().__init__(text)
        self.raw_value = value

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            try:
                return float(self.raw_value) < float(other.raw_value)
            except (ValueError, TypeError):
                pass
        return super().__lt__(other)


class BigTxnWorker(QThread):
    """大事务分析后台工作线程"""

    progress_updated = Signal(int, int, int, int, str)  # (pct, cur_pos, total_size, txn_count, msg)
    analysis_finished = Signal(list)  # (top_txns)
    error_occurred = Signal(str)  # (error_message)

    def __init__(self, analyzer):
        super().__init__()
        self.analyzer = analyzer

    def run(self):
        try:
            self.analyzer.set_progress_callback(self._on_progress)
            results = self.analyzer.analyze()
            self.analysis_finished.emit(results)
        except Exception as e:
            logger.error(f"BigTxnWorker 运行异常: {str(e)}")
            self.error_occurred.emit(str(e))

    def _on_progress(self, pct, cur_pos, total_size, txn_count, msg):
        self.progress_updated.emit(pct, cur_pos, total_size, txn_count, msg)

    def stop(self):
        if self.analyzer:
            self.analyzer.stop()


class BigTxnWidget(QWidget):
    """大事务分析选项卡组件"""

    # 信号：通知主窗口跳转到 SQL 解析页面并填入参数 (file, start_pos, end_pos)
    view_in_sql_parser = Signal(str, int, int)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.worker = None
        self.current_results = []
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. 顶部配置与控制面板
        top_group = QGroupBox("大事务分析配置")
        top_layout = QVBoxLayout(top_group)

        form_layout = QHBoxLayout()

        # 连接选择
        self.conn_label = QLabel("数据库连接:")
        self.connection_combo = QComboBox()
        self.connection_combo.setMinimumWidth(160)
        form_layout.addWidget(self.conn_label)
        form_layout.addWidget(self.connection_combo)

        # Binlog 文件选择
        self.file_label = QLabel("Binlog 文件:")
        self.binlog_combo = QComboBox()
        self.binlog_combo.setEditable(True)
        self.binlog_combo.setMinimumWidth(180)
        self.binlog_combo.setPlaceholderText("例如: mysql-bin.000001")
        self.fetch_files_btn = QPushButton("刷新文件")
        self.fetch_files_btn.clicked.connect(self.fetch_binlog_files)

        form_layout.addWidget(self.file_label)
        form_layout.addWidget(self.binlog_combo)
        form_layout.addWidget(self.fetch_files_btn)

        # Top N 限制
        self.top_label = QLabel("Top N 数量:")
        self.top_spin = QSpinBox()
        self.top_spin.setRange(1, 1000)
        self.top_spin.setValue(20)
        self.top_spin.setMinimumWidth(80)
        form_layout.addWidget(self.top_label)
        form_layout.addWidget(self.top_spin)

        form_layout.addStretch()

        # 控制按钮
        self.start_btn = QPushButton("开始分析")
        self.start_btn.setStyleSheet("font-weight: bold;")
        self.start_btn.clicked.connect(self.start_analysis)
        form_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_analysis)
        form_layout.addWidget(self.stop_btn)

        self.export_csv_btn = QPushButton("导出 CSV")
        self.export_csv_btn.setEnabled(False)
        self.export_csv_btn.clicked.connect(self.export_to_csv)
        form_layout.addWidget(self.export_csv_btn)

        self.export_txt_btn = QPushButton("导出 TXT")
        self.export_txt_btn.setEnabled(False)
        self.export_txt_btn.clicked.connect(self.export_to_txt)
        form_layout.addWidget(self.export_txt_btn)

        top_layout.addLayout(form_layout)

        # 进度与状态行
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setMinimumWidth(300)
        progress_layout.addWidget(self.status_label)

        top_layout.addLayout(progress_layout)
        main_layout.addWidget(top_group)

        # 2. 中间 Master-Detail 上下分栏
        splitter = QSplitter(Qt.Vertical)

        # Master Panel: Top N 表格
        master_widget = QWidget()
        master_layout = QVBoxLayout(master_widget)
        master_layout.setContentsMargins(0, 0, 0, 0)

        master_title_layout = QHBoxLayout()
        master_title = QLabel("<b>Top N 大事务列表</b> (点击查看详情，双击可在 SQL 解析中查看)")
        master_title_layout.addWidget(master_title)
        master_title_layout.addStretch()

        self.btn_view_sql = QPushButton("🔍 在 SQL 解析中查看此事务")
        self.btn_view_sql.setEnabled(False)
        self.btn_view_sql.clicked.connect(self.on_view_selected_in_sql)
        master_title_layout.addWidget(self.btn_view_sql)
        master_layout.addLayout(master_title_layout)

        self.master_table = QTableWidget()
        self.master_table.setColumnCount(9)
        self.master_table.setHorizontalHeaderLabels([
            "排名", "大小 (Bytes)", "格式化大小", "起始位置", "结束位置", "XID", "线程ID", "时间", "状态"
        ])
        self.master_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.master_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.master_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.master_table.setSortingEnabled(True)
        self.master_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.master_table.horizontalHeader().setStretchLastSection(True)
        self.master_table.itemSelectionChanged.connect(self.on_master_row_selected)
        self.master_table.doubleClicked.connect(self.on_view_selected_in_sql)
        self.master_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.master_table.customContextMenuRequested.connect(self.show_context_menu)

        master_layout.addWidget(self.master_table)
        splitter.addWidget(master_widget)

        # Detail Panel: 详情分栏
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_group = QGroupBox("事务详情")
        detail_box_layout = QHBoxLayout(self.detail_group)

        # 详情左侧：表分布统计
        table_stats_box = QGroupBox("涉及数据表统计 (Table_map)")
        table_stats_layout = QVBoxLayout(table_stats_box)
        self.table_stats_widget = QTableWidget()
        self.table_stats_widget.setColumnCount(2)
        self.table_stats_widget.setHorizontalHeaderLabels(["数据表 (库名.表名)", "映射次数"])
        self.table_stats_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_stats_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_stats_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table_stats_layout.addWidget(self.table_stats_widget)
        detail_box_layout.addWidget(table_stats_box, 3)

        # 详情右侧：DML 事件统计
        ops_stats_box = QGroupBox("DML 操作事件统计")
        ops_stats_layout = QVBoxLayout(ops_stats_box)
        self.ops_stats_widget = QTableWidget()
        self.ops_stats_widget.setColumnCount(2)
        self.ops_stats_widget.setHorizontalHeaderLabels(["事件类型", "事件数量"])
        self.ops_stats_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ops_stats_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.ops_stats_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        ops_stats_layout.addWidget(self.ops_stats_widget)
        detail_box_layout.addWidget(ops_stats_box, 2)

        detail_layout.addWidget(self.detail_group)
        splitter.addWidget(detail_widget)

        # 设置比例 6:4
        splitter.setSizes([450, 250])
        main_layout.addWidget(splitter)

    @staticmethod
    def format_bytes(num_bytes):
        """将字节数格式化为易读的字符串"""
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.2f} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{num_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"

    def populate_connections(self, connection_names, current_name=None):
        """更新数据库连接列表"""
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        for name in connection_names:
            self.connection_combo.addItem(name)
        if current_name and current_name in connection_names:
            self.connection_combo.setCurrentText(current_name)
        self.connection_combo.blockSignals(False)

    def populate_binlog_files(self, files, current_file=None):
        """更新可用 Binlog 文件列表"""
        self.binlog_combo.blockSignals(True)
        self.binlog_combo.clear()
        for f in files:
            self.binlog_combo.addItem(f)
        if current_file:
            self.binlog_combo.setCurrentText(current_file)
        self.binlog_combo.blockSignals(False)

    def fetch_binlog_files(self):
        """在线查询当前数据库可用的 binlog 文件列表"""
        conn_settings = self.get_selected_connection_settings()
        if not conn_settings:
            QMessageBox.warning(self, "提示", "请先选择有效的数据库连接")
            return

        try:
            conn = pymysql.connect(**conn_settings)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SHOW MASTER LOGS")
                    rows = cursor.fetchall()
                    files = [r[0] for r in rows]
            finally:
                conn.close()

            if files:
                current = self.binlog_combo.currentText().strip()
                self.populate_binlog_files(files, current if current in files else files[0])
                QMessageBox.information(self, "成功", f"成功获取 {len(files)} 个 Binlog 文件")
            else:
                QMessageBox.warning(self, "提示", "未找到任何 Binlog 文件")
        except Exception as e:
            QMessageBox.critical(self, "获取失败", f"获取 Binlog 文件失败:\n{str(e)}")

    def get_selected_connection_settings(self):
        """获取当前选中的数据库连接配置"""
        conn_name = self.connection_combo.currentText().strip()
        if not conn_name:
            return None
        info = self.config_manager.get_connection(conn_name)
        if not info:
            return None
        return {
            "host": info.get("host", "127.0.0.1"),
            "port": int(info.get("port", 3306)),
            "user": info.get("user", "root"),
            "passwd": info.get("password", ""),
            "charset": info.get("charset", "utf8mb4"),
        }

    def start_analysis(self):
        """启动大事务分析"""
        conn_settings = self.get_selected_connection_settings()
        if not conn_settings:
            QMessageBox.warning(self, "提示", "请先选择有效的数据库连接")
            return

        binlog_file = self.binlog_combo.currentText().strip()
        if not binlog_file:
            QMessageBox.warning(self, "提示", "请指定要分析的 Binlog 文件")
            return

        top_n = self.top_spin.value()

        # 重置界面状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_csv_btn.setEnabled(False)
        self.export_txt_btn.setEnabled(False)
        self.btn_view_sql.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"正在连接数据库并分析 {binlog_file}...")

        # 清空当前表格
        self.master_table.setRowCount(0)
        self.table_stats_widget.setRowCount(0)
        self.ops_stats_widget.setRowCount(0)
        self.current_results = []

        try:
            analyzer = BigTxnAnalyzer(conn_settings, binlog_file, top_n)
            self.worker = BigTxnWorker(analyzer)
            self.worker.progress_updated.connect(self.on_progress_updated)
            self.worker.analysis_finished.connect(self.on_analysis_finished)
            self.worker.error_occurred.connect(self.on_analysis_error)
            self.worker.start()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动分析失败: {str(e)}")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def stop_analysis(self):
        """停止大事务分析"""
        if self.worker and self.worker.isRunning():
            self.status_label.setText("正在停止分析，请稍候...")
            self.worker.stop()
            self.stop_btn.setEnabled(False)

    def on_progress_updated(self, pct, cur_pos, total_size, txn_count, msg):
        self.progress_bar.setValue(pct)
        if total_size > 0:
            formatted_pos = self.format_bytes(cur_pos)
            formatted_total = self.format_bytes(total_size)
            self.status_label.setText(
                f"{msg} | 扫描进度: {formatted_pos} / {formatted_total} ({pct}%)"
            )
        else:
            self.status_label.setText(msg)

    def on_analysis_finished(self, results):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.current_results = results

        self.display_results(results)

        if results:
            self.export_csv_btn.setEnabled(True)
            self.export_txt_btn.setEnabled(True)
            self.status_label.setText(f"分析完成！找到 Top {len(results)} 个大事务")
            # 默认选中第一行
            self.master_table.selectRow(0)
        else:
            self.status_label.setText("分析完成，未发现匹配的事务")

    def on_analysis_error(self, err_msg):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"分析出错: {err_msg}")
        QMessageBox.critical(self, "分析失败", f"大事务分析过程中发生错误:\n{err_msg}")

    def display_results(self, results):
        """展示 Top N 结果到 Master 表格"""
        self.master_table.setSortingEnabled(False)
        self.master_table.setRowCount(len(results))

        for row_idx, r in enumerate(results):
            rank = row_idx + 1
            size_bytes = r["size"]
            size_human = self.format_bytes(size_bytes)
            start_pos = r["start"]
            end_pos = r["end"]
            xid = r["xid"]
            thread_id = r["thread"]
            txn_time = r["time"]
            status_str = "⚠️ 未提交 (incomplete)" if r["incomplete"] else "正常"

            item_rank = NumericTableWidgetItem(rank)
            item_bytes = NumericTableWidgetItem(size_bytes)
            item_human = NumericTableWidgetItem(size_bytes, size_human)
            item_start = NumericTableWidgetItem(start_pos)
            item_end = NumericTableWidgetItem(end_pos)
            item_xid = QTableWidgetItem(xid)
            item_thread = QTableWidgetItem(thread_id)
            item_time = QTableWidgetItem(txn_time)
            item_status = QTableWidgetItem(status_str)

            # 对齐与高亮设置
            for it in [item_rank, item_bytes, item_human, item_start, item_end, item_xid, item_thread, item_time, item_status]:
                it.setTextAlignment(Qt.AlignCenter)

            if r["incomplete"]:
                item_status.setForeground(QBrush(QColor(220, 50, 50)))
                item_status.setFont(QFont("Arial", 9, QFont.Bold))

            self.master_table.setItem(row_idx, 0, item_rank)
            self.master_table.setItem(row_idx, 1, item_bytes)
            self.master_table.setItem(row_idx, 2, item_human)
            self.master_table.setItem(row_idx, 3, item_start)
            self.master_table.setItem(row_idx, 4, item_end)
            self.master_table.setItem(row_idx, 5, item_xid)
            self.master_table.setItem(row_idx, 6, item_thread)
            self.master_table.setItem(row_idx, 7, item_time)
            self.master_table.setItem(row_idx, 8, item_status)

        self.master_table.setSortingEnabled(True)

    def on_master_row_selected(self):
        """选中 Master 行时刷新 Detail 详情面板"""
        selected_rows = self.master_table.selectionModel().selectedRows()
        if not selected_rows:
            self.btn_view_sql.setEnabled(False)
            self.table_stats_widget.setRowCount(0)
            self.ops_stats_widget.setRowCount(0)
            self.detail_group.setTitle("事务详情")
            return

        self.btn_view_sql.setEnabled(True)
        selected_row = selected_rows[0].row()

        # 根据排名的原始值在 self.current_results 中查找匹配事务
        rank_item = self.master_table.item(selected_row, 0)
        if not rank_item or not hasattr(rank_item, "raw_value"):
            return

        rank_val = int(rank_item.raw_value)
        if 1 <= rank_val <= len(self.current_results):
            rec = self.current_results[rank_val - 1]
            self.update_detail_panel(rank_val, rec)

    def update_detail_panel(self, rank, rec):
        """填充详情面板"""
        self.detail_group.setTitle(
            f"事务详情 (排名 #{rank} | 大小: {self.format_bytes(rec['size'])} | Pos: {rec['start']} ~ {rec['end']} | XID: {rec['xid'] or '无'})"
        )

        # 1. 表统计 (Table_map)
        tables_counter = rec.get("tables", {})
        sorted_tables = tables_counter.most_common() if hasattr(tables_counter, "most_common") else []
        self.table_stats_widget.setRowCount(len(sorted_tables))
        for row, (tbl, count) in enumerate(sorted_tables):
            item_tbl = QTableWidgetItem(tbl)
            item_cnt = NumericTableWidgetItem(count)
            item_cnt.setTextAlignment(Qt.AlignCenter)
            self.table_stats_widget.setItem(row, 0, item_tbl)
            self.table_stats_widget.setItem(row, 1, item_cnt)

        # 2. DML 操作统计
        ops_counter = rec.get("ops", {})
        sorted_ops = ops_counter.most_common() if hasattr(ops_counter, "most_common") else []
        self.ops_stats_widget.setRowCount(len(sorted_ops))
        for row, (op, count) in enumerate(sorted_ops):
            item_op = QTableWidgetItem(f"{op} events")
            item_cnt = NumericTableWidgetItem(count)
            item_cnt.setTextAlignment(Qt.AlignCenter)
            self.ops_stats_widget.setItem(row, 0, item_op)
            self.ops_stats_widget.setItem(row, 1, item_cnt)

    def on_view_selected_in_sql(self):
        """响应在 SQL 解析中查看此事务按钮或双击"""
        selected_rows = self.master_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        selected_row = selected_rows[0].row()
        rank_item = self.master_table.item(selected_row, 0)
        if not rank_item or not hasattr(rank_item, "raw_value"):
            return

        rank_val = int(rank_item.raw_value)
        if 1 <= rank_val <= len(self.current_results):
            rec = self.current_results[rank_val - 1]
            binlog_file = self.binlog_combo.currentText().strip()
            start_pos = rec["start"]
            end_pos = rec["end"]
            logger.info(
                f"请求跳转到 SQL 解析: file={binlog_file}, start={start_pos}, end={end_pos}"
            )
            self.view_in_sql_parser.emit(binlog_file, start_pos, end_pos)

    def show_context_menu(self, pos):
        """右键菜单"""
        selected_rows = self.master_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        menu = QMenu(self)
        action_view = QAction("🔍 在 SQL 解析中查看此事务", self)
        action_view.triggered.connect(self.on_view_selected_in_sql)
        menu.addAction(action_view)

        menu.addSeparator()

        selected_row = selected_rows[0].row()
        item_start = self.master_table.item(selected_row, 3)
        item_end = self.master_table.item(selected_row, 4)
        item_xid = self.master_table.item(selected_row, 5)

        if item_start:
            act_copy_start = QAction(f"复制起始位置 ({item_start.text()})", self)
            act_copy_start.triggered.connect(
                lambda: QGuiApplication.clipboard().setText(item_start.text())
            )
            menu.addAction(act_copy_start)

        if item_end:
            act_copy_end = QAction(f"复制结束位置 ({item_end.text()})", self)
            act_copy_end.triggered.connect(
                lambda: QGuiApplication.clipboard().setText(item_end.text())
            )
            menu.addAction(act_copy_end)

        if item_xid and item_xid.text():
            act_copy_xid = QAction(f"复制 XID ({item_xid.text()})", self)
            act_copy_xid.triggered.connect(
                lambda: QGuiApplication.clipboard().setText(item_xid.text())
            )
            menu.addAction(act_copy_xid)

        menu.exec_(self.master_table.viewport().mapToGlobal(pos))

    def export_to_csv(self):
        """导出结果为 CSV 报表"""
        if not self.current_results:
            QMessageBox.information(self, "提示", "当前没有可导出的分析结果")
            return

        binlog_file = self.binlog_combo.currentText().strip() or "binlog"
        default_filename = f"bigtxn_report_{binlog_file}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV 报表", default_filename, "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow([
                    "排名", "大小(Bytes)", "格式化大小", "起始位置", "结束位置",
                    "XID", "线程ID", "时间", "是否未提交", "涉及表概要", "DML事件概要"
                ])

                for idx, r in enumerate(self.current_results):
                    rank = idx + 1
                    tables_str = "; ".join(
                        [f"{tbl}({cnt})" for tbl, cnt in r["tables"].most_common()]
                    )
                    ops_str = "; ".join(
                        [f"{op}({cnt})" for op, cnt in r["ops"].most_common()]
                    )
                    writer.writerow([
                        rank,
                        r["size"],
                        self.format_bytes(r["size"]),
                        r["start"],
                        r["end"],
                        r["xid"],
                        r["thread"],
                        r["time"],
                        "是" if r["incomplete"] else "否",
                        tables_str,
                        ops_str,
                    ])

            QMessageBox.information(self, "成功", f"CSV 报表导出成功:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 CSV 报表时发生错误:\n{str(e)}")

    def export_to_txt(self):
        """导出结果为与原脚本格式一致的 TXT 报告"""
        if not self.current_results:
            QMessageBox.information(self, "提示", "当前没有可导出的分析结果")
            return

        binlog_file = self.binlog_combo.currentText().strip() or "binlog"
        default_filename = f"bigtxn_report_{binlog_file}.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 TXT 分析报告", default_filename, "Text Files (*.txt);;All Files (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# Binlog 大事务分析报告 (文件: {binlog_file})\n")
                f.write("# 格式: <size>\\tstart=<pos>\\tend=<pos>\\txid=<xid>\\tthread=<tid>\\ttime=<time>\\n\n\n")

                for r in self.current_results:
                    header = (
                        f"{r['size']}\tstart={r['start']}\tend={r['end']}\txid={r['xid']}"
                        f"\tthread={r['thread']}\ttime={r['time']}"
                        + ("\t(incomplete)" if r["incomplete"] else "")
                    )
                    f.write(header + "\n")
                    for t, c in r["tables"].most_common():
                        f.write(f"\tTable_map x{c}\t{t}\n")
                    for op, c in r["ops"].most_common():
                        f.write(f"\t{op} events x{c}\n")

            QMessageBox.information(self, "成功", f"TXT 分析报告导出成功:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 TXT 报告时发生错误:\n{str(e)}")
