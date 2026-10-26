#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GUI 交互与联动集成测试
测试 MainWindow 中 Tab 挂载、联动跳转及 BigTxnWidget 的结果呈现与导出。
"""

import os
import tempfile
import unittest
from collections import Counter
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 设置离屏测试环境，避免在无显示器环境抛出异常
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from gui.main_window import MainWindow
from gui.bigtxn_widget import BigTxnWidget


class TestBigTxnGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_tabs_initialization(self):
        """测试 TabWidget 正确初始化两个标签页"""
        self.assertEqual(self.window.tab_widget.count(), 2)
        self.assertEqual(self.window.tab_widget.tabText(0), "SQL 解析与回滚")
        self.assertEqual(self.window.tab_widget.tabText(1), "大事务分析")
        self.assertIsInstance(self.window.bigtxn_widget, BigTxnWidget)

    def test_switch_to_sql_parser_with_txn(self):
        """测试从大事务页面跳转联动到 SQL 解析页面的逻辑"""
        # 初始切换到大事务页面 (Tab 1)
        self.window.tab_widget.setCurrentIndex(1)
        self.assertEqual(self.window.tab_widget.currentIndex(), 1)

        # 触发联动信号
        test_file = "mysql-bin.000099"
        test_start = 12040
        test_end = 9988770
        self.window.bigtxn_widget.view_in_sql_parser.emit(test_file, test_start, test_end)

        # 验证自动切换回 Tab 0
        self.assertEqual(self.window.tab_widget.currentIndex(), 0)

        # 验证参数自动填充
        self.assertEqual(self.window.start_file_combo.currentText(), test_file)
        self.assertEqual(self.window.end_file_combo.currentText(), test_file)
        self.assertEqual(self.window.start_pos_spin.value(), test_start)
        self.assertEqual(self.window.end_pos_spin.value(), test_end)

    def test_switch_to_sql_parser_with_large_txn(self):
        """测试从大事务页面跳转超 2GB (64 位 Position) 的事务到 SQL 解析页面"""
        self.window.tab_widget.setCurrentIndex(1)
        self.assertEqual(self.window.tab_widget.currentIndex(), 1)

        test_file = "mysql-bin.000001"
        test_start = 75344317
        test_end = 2495170926  # > 2^31 - 1
        self.window.bigtxn_widget.view_in_sql_parser.emit(test_file, test_start, test_end)

        self.assertEqual(self.window.tab_widget.currentIndex(), 0)
        self.assertEqual(self.window.start_file_combo.currentText(), test_file)
        self.assertEqual(self.window.end_file_combo.currentText(), test_file)
        self.assertEqual(self.window.start_pos_spin.value(), test_start)
        self.assertEqual(self.window.end_pos_spin.value(), test_end)

    def test_first_row_button_click_jump_large_txn(self):
        """测试选中第一行超 2GB 大事务时，点击跳转按钮可成功跳转到 SQL 解析"""
        widget = self.window.bigtxn_widget
        widget.binlog_combo.addItem("mysql-bin.000001")
        widget.binlog_combo.setCurrentText("mysql-bin.000001")

        mock_results = [
            {
                "size": 2419826609,
                "start": 75344317,
                "end": 2495170926,
                "xid": "962758871",
                "thread": "6040231",
                "time": "04:45:04",
                "tables": Counter({"`test`.`large_table`": 100}),
                "ops": Counter({"Write_rows": 100}),
                "incomplete": False,
            },
            {
                "size": 29501341,
                "start": 4,
                "end": 29501345,
                "xid": "962100711",
                "thread": "5393365",
                "time": "02:00:02",
                "tables": Counter({"`test`.`small_table`": 10}),
                "ops": Counter({"Update_rows": 10}),
                "incomplete": False,
            }
        ]

        widget.display_results(mock_results)
        widget.current_results = mock_results

        # 切换到大事务页面
        self.window.tab_widget.setCurrentIndex(1)
        self.assertEqual(self.window.tab_widget.currentIndex(), 1)

        # 选中第一行
        widget.master_table.selectRow(0)
        widget.on_master_row_selected()
        self.assertTrue(widget.btn_view_sql.isEnabled())

        # 点击跳转按钮
        widget.btn_view_sql.click()

        # 验证跳转到 SQL 解析页面并填充了超 2GB 的数值
        self.assertEqual(self.window.tab_widget.currentIndex(), 0)
        self.assertEqual(self.window.start_file_combo.currentText(), "mysql-bin.000001")
        self.assertEqual(self.window.start_pos_spin.value(), 75344317)
        self.assertEqual(self.window.end_pos_spin.value(), 2495170926)

    def test_display_results_and_selection(self):
        """测试 BigTxnWidget 展示结果与 Master-Detail 联动"""
        widget = self.window.bigtxn_widget

        mock_results = [
            {
                "size": 1048576,
                "start": 100,
                "end": 1048676,
                "xid": "123456",
                "thread": "50",
                "time": "14:20:00",
                "tables": Counter({"`app`.`orders`": 15, "`app`.`items`": 30}),
                "ops": Counter({"Write_rows": 20, "Update_rows": 5}),
                "incomplete": False,
            },
            {
                "size": 500,
                "start": 2000,
                "end": 2500,
                "xid": "",
                "thread": "51",
                "time": "14:21:00",
                "tables": Counter({"`test`.`logs`": 2}),
                "ops": Counter({"Delete_rows": 2}),
                "incomplete": True,
            }
        ]

        widget.display_results(mock_results)
        widget.current_results = mock_results

        self.assertEqual(widget.master_table.rowCount(), 2)
        # 验证第一行数据
        self.assertEqual(widget.master_table.item(0, 0).text(), "1")
        self.assertEqual(widget.master_table.item(0, 1).text(), "1048576")
        self.assertIn("1.00 MB", widget.master_table.item(0, 2).text())
        self.assertEqual(widget.master_table.item(0, 5).text(), "123456")
        self.assertEqual(widget.master_table.item(0, 8).text(), "正常")

        # 验证未提交状态高亮
        self.assertIn("incomplete", widget.master_table.item(1, 8).text())

        # 选中第一行，验证详情刷新
        widget.master_table.selectRow(0)
        widget.on_master_row_selected()

        self.assertEqual(widget.table_stats_widget.rowCount(), 2)
        self.assertEqual(widget.ops_stats_widget.rowCount(), 2)
        self.assertTrue(widget.btn_view_sql.isEnabled())

    def test_export_txt_formatting(self):
        """测试导出 TXT 格式与原脚本输出一致"""
        widget = self.window.bigtxn_widget
        widget.binlog_combo.addItem("mysql-bin.000001")
        widget.binlog_combo.setCurrentText("mysql-bin.000001")

        mock_results = [
            {
                "size": 500,
                "start": 100,
                "end": 600,
                "xid": "999",
                "thread": "10",
                "time": "12:00:00",
                "tables": Counter({"`db`.`t1`": 5}),
                "ops": Counter({"Write_rows": 5}),
                "incomplete": False,
            }
        ]
        widget.current_results = mock_results

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name

        try:
            # 格式化文本
            with open(tmp_path, "w", encoding="utf-8") as f:
                for r in widget.current_results:
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

            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("500\tstart=100\tend=600\txid=999\tthread=10\ttime=12:00:00", content)
            self.assertIn("Table_map x5\t`db`.`t1`", content)
            self.assertIn("Write_rows events x5", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
