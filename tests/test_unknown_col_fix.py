#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
单元测试：测试针对 MySQL 8.0 binlog_row_metadata=MINIMAL 时
UNKNOWN_COL 列名自适应恢复机制。
"""

import inspect
import unittest
from unittest.mock import MagicMock
from core.binlog_util import fix_unknown_col_keys, generate_sql_pattern
from core.binlog_parser import BinlogParser
from pymysqlreplication.row_event import WriteRowsEvent, TableMapEvent
from pymysqlreplication.table import Table
from pymysqlreplication.column import Column


def create_test_table(table_id, schema, table_name, columns):
    """跨版本自适应构建 Table 实例（兼容 0.46 与 1.0+）"""
    sig = inspect.signature(Table.__init__)
    params = list(sig.parameters.keys())
    if "column_schemas" in params:
        return Table(None, table_id, schema, table_name, columns)
    else:
        return Table(table_id, schema, table_name, columns)


class TestUnknownColFix(unittest.TestCase):

    def test_fix_unknown_col_keys(self):
        """测试 fix_unknown_col_keys 对 UNKNOWN_COL 的映射恢复"""
        col0 = Column(type=15, name="id", is_primary=True)
        col1 = Column(type=15, name="operation_type", is_primary=False)
        col2 = Column(type=15, name="description", is_primary=False)
        tbl = create_test_table(1, "line_ctms", "line_operation_log", [col0, col1, col2])

        event = MagicMock(spec=WriteRowsEvent)
        event.table_id = 1
        event.table_map = {1: tbl}

        row_dict = {
            "UNKNOWN_COL0": "01a1678f",
            "UNKNOWN_COL1": "UPDATE",
            "UNKNOWN_COL2": "交接单整单到达确认",
        }

        fixed = fix_unknown_col_keys(row_dict, event)
        self.assertEqual(fixed["id"], "01a1678f")
        self.assertEqual(fixed["operation_type"], "UPDATE")
        self.assertEqual(fixed["description"], "交接单整单到达确认")
        self.assertNotIn("UNKNOWN_COL0", fixed)

    def test_generate_sql_pattern_with_unknown_cols(self):
        """测试在带有 UNKNOWN_COL 的情况下，生成的 SQL 模板自动转为真实列名"""
        col0 = Column(type=15, name="id", is_primary=True)
        col1 = Column(type=15, name="operation_type", is_primary=False)
        tbl = create_test_table(1, "line_ctms", "line_operation_log", [col0, col1])

        event = MagicMock(spec=WriteRowsEvent)
        event.schema = "line_ctms"
        event.table = "line_operation_log"
        event.table_id = 1
        event.table_map = {1: tbl}
        event.primary_key = "id"

        row = {
            "values": {
                "UNKNOWN_COL0": "uuid-1234",
                "UNKNOWN_COL1": "UPDATE",
            }
        }

        pattern = generate_sql_pattern(event, row=row, flashback=False, no_pk=False)
        # 模板中应包含真实列名，而不是 UNKNOWN_COL0
        self.assertIn("`id`, `operation_type`", pattern["template"])
        self.assertNotIn("UNKNOWN_COL0", pattern["template"])

    def test_ensure_table_columns_database_query(self):
        """测试 _ensure_table_columns 从数据库自动恢复缺失列名"""
        parser = BinlogParser.__new__(BinlogParser)
        parser.table_columns_cache = {}

        # 模拟列名为空或 UNKNOWN_COL 的表对象
        col0 = Column(type=15, name="UNKNOWN_COL0", is_primary=False)
        col1 = Column(type=15, name="UNKNOWN_COL1", is_primary=False)
        tbl = create_test_table(10, "line_ctms", "line_operation_log", [col0, col1])

        event = MagicMock(spec=WriteRowsEvent)
        event.table_id = 10
        event.table_map = {10: tbl}
        event.schema = "line_ctms"
        event.table = "line_operation_log"

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("id", "PRI"),
            ("operation_type", ""),
        ]

        parser._ensure_table_columns(mock_cursor, event)

        # 验证表对象列名被正确赋上真实列名
        self.assertEqual(tbl.columns[0].name, "id")
        self.assertTrue(tbl.columns[0].is_primary)
        self.assertEqual(tbl.columns[1].name, "operation_type")
        self.assertEqual(tbl.primary_key, "id")
        self.assertEqual(event.primary_key, "id")

        # 验证结果被缓存
        self.assertIn(("line_ctms", "line_operation_log"), parser.table_columns_cache)


if __name__ == "__main__":
    unittest.main()
