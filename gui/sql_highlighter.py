#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SQL语法高亮器
为QTextEdit提供SQL语句的语法高亮功能
"""

import re
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont


class SqlHighlighter(QSyntaxHighlighter):
    """SQL语法高亮器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        self._setup_highlighting_rules()

    def _setup_highlighting_rules(self):
        """设置高亮规则"""

        # SQL关键字
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(86, 156, 214))  # 蓝色
        keyword_format.setFontWeight(QFont.Weight.Bold)

        sql_keywords = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'FROM', 'WHERE', 'INTO',
            'VALUES', 'SET', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON',
            'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'UNION',
            'CREATE', 'DROP', 'ALTER', 'TABLE', 'INDEX', 'VIEW', 'DATABASE',
            'SCHEMA', 'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES', 'CONSTRAINT',
            'NOT', 'NULL', 'DEFAULT', 'AUTO_INCREMENT', 'UNIQUE', 'CHECK',
            'AND', 'OR', 'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'IS', 'AS',
            'DISTINCT', 'ALL', 'ANY', 'SOME', 'CASE', 'WHEN', 'THEN', 'ELSE',
            'END', 'IF', 'IFNULL', 'COALESCE', 'COUNT', 'SUM', 'AVG', 'MAX',
            'MIN', 'CONCAT', 'SUBSTRING', 'LENGTH', 'UPPER', 'LOWER',
            'TRIM', 'REPLACE', 'NOW', 'CURDATE', 'CURTIME', 'DATE', 'TIME',
            'TIMESTAMP', 'YEAR', 'MONTH', 'DAY', 'HOUR', 'MINUTE', 'SECOND',
            'USE', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN', 'BEGIN', 'COMMIT',
            'ROLLBACK', 'TRANSACTION', 'START', 'SAVEPOINT', 'RELEASE',
            'LOCK', 'UNLOCK', 'TABLES', 'READ', 'WRITE', 'SLEEP'
        ]

        for keyword in sql_keywords:
            pattern = r'\b' + keyword + r'\b'
            self.highlighting_rules.append((re.compile(pattern, re.IGNORECASE), keyword_format))

        # 数据类型
        datatype_format = QTextCharFormat()
        datatype_format.setForeground(QColor(78, 201, 176))  # 青绿色
        datatype_format.setFontWeight(QFont.Weight.Bold)

        datatypes = [
            'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT', 'MEDIUMINT',
            'DECIMAL', 'NUMERIC', 'FLOAT', 'DOUBLE', 'REAL', 'BIT',
            'BOOLEAN', 'BOOL', 'SERIAL',
            'DATE', 'DATETIME', 'TIMESTAMP', 'TIME', 'YEAR',
            'CHAR', 'VARCHAR', 'BINARY', 'VARBINARY', 'BLOB', 'TEXT',
            'TINYBLOB', 'TINYTEXT', 'MEDIUMBLOB', 'MEDIUMTEXT',
            'LONGBLOB', 'LONGTEXT', 'ENUM', 'SET', 'JSON'
        ]

        for datatype in datatypes:
            pattern = r'\b' + datatype + r'\b'
            self.highlighting_rules.append((re.compile(pattern, re.IGNORECASE), datatype_format))

        # 字符串 (单引号)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(206, 145, 120))  # 橙色
        self.highlighting_rules.append((re.compile(r"'[^']*'"), string_format))

        # 字符串 (双引号)
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), string_format))

        # 数字
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(181, 206, 168))  # 浅绿色
        self.highlighting_rules.append((re.compile(r'\b\d+\.?\d*\b'), number_format))

        # 标识符 (反引号)
        identifier_format = QTextCharFormat()
        identifier_format.setForeground(QColor(220, 220, 170))  # 浅黄色
        self.highlighting_rules.append((re.compile(r'`[^`]*`'), identifier_format))

        # 注释 (-- 风格)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))  # 绿色
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'--[^\r\n]*'), comment_format))

        # 注释 (# 风格)
        self.highlighting_rules.append((re.compile(r'#[^\r\n]*'), comment_format))

        # 多行注释 (/* ... */)
        self.highlighting_rules.append((re.compile(r'/\*.*?\*/', re.DOTALL), comment_format))

        # 操作符
        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor(212, 212, 212))  # 浅灰色
        operator_format.setFontWeight(QFont.Weight.Bold)

        operators = [
            r'=', r'!=', r'<>', r'<', r'>', r'<=', r'>=',
            r'\+', r'-', r'\*', r'/', r'%', r'\^',
            r'&&', r'\|\|', r'!', r'~'
        ]

        for op in operators:
            self.highlighting_rules.append((re.compile(op), operator_format))

        # 特殊符号
        symbol_format = QTextCharFormat()
        symbol_format.setForeground(QColor(212, 212, 212))  # 浅灰色

        symbols = [r'\(', r'\)', r'\[', r'\]', r'\{', r'\}', r';', r',', r'\.']

        for symbol in symbols:
            self.highlighting_rules.append((re.compile(symbol), symbol_format))

    def highlightBlock(self, text):
        """高亮文本块"""
        # 应用所有高亮规则
        for pattern, format_obj in self.highlighting_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - match.start()
                self.setFormat(start, length, format_obj)
