#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import datetime
from contextlib import contextmanager
from pymysqlreplication.event import QueryEvent
from pymysqlreplication.row_event import (
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)

if sys.version > '3':
    PY3PLUS = True
else:
    PY3PLUS = False


def is_valid_datetime(string):
    """验证日期时间格式是否正确"""
    try:
        datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")
        return True
    except:
        return False


def create_unique_file(filename):
    """创建唯一文件名"""
    version = 0
    result_file = filename
    # if we have to try more than 1000 times, something is seriously wrong
    while os.path.exists(result_file) and version < 1000:
        result_file = filename + '.' + str(version)
        version += 1
    if version >= 1000:
        raise OSError('cannot create unique file %s.[0-1000]' % filename)
    return result_file


@contextmanager
def temp_open(filename, mode):
    """临时文件上下文管理器"""
    f = open(filename, mode)
    try:
        yield f
    finally:
        f.close()
        if os.path.exists(filename):
            os.remove(filename)


def compare_items(items):
    """比较数据库字段值"""
    # caution: if v is NULL, may need to process
    (k, v) = items
    # 确保key也经过编码处理
    k = fix_object(k)
    if v is None:
        return '`%s` IS %%s' % k
    else:
        return '`%s`=%%s' % k


def fix_object(value):
    """修复Python对象以便正确插入SQL查询"""
    if isinstance(value, set):
        value = ','.join(value)
    if PY3PLUS and isinstance(value, bytes):
        return value.decode('utf-8', 'ignore')  # 使用ignore忽略解码错误
    elif not PY3PLUS:
        # Python 2 compatibility
        try:
            if isinstance(value, unicode):
                return value.encode('utf-8')
        except NameError:
            # unicode doesn't exist in Python 3
            pass
    return value


def is_dml_event(event):
    """判断是否为DML事件"""
    if isinstance(event, WriteRowsEvent) or isinstance(event, UpdateRowsEvent) or isinstance(event, DeleteRowsEvent):
        return True
    else:
        return False


def event_type(event):
    """获取事件类型"""
    t = None
    if isinstance(event, WriteRowsEvent):
        t = 'INSERT'
    elif isinstance(event, UpdateRowsEvent):
        t = 'UPDATE'
    elif isinstance(event, DeleteRowsEvent):
        t = 'DELETE'
    return t


def concat_sql_from_binlog_event(cursor, binlog_event, row=None, e_start_pos=None, flashback=False, no_pk=False):
    """从binlog事件生成SQL语句"""
    if flashback and no_pk:
        raise ValueError('only one of flashback or no_pk can be True')

    if not (isinstance(binlog_event, WriteRowsEvent) or isinstance(binlog_event, UpdateRowsEvent) or
            isinstance(binlog_event, DeleteRowsEvent) or isinstance(binlog_event, QueryEvent)):
        raise ValueError('binlog_event must be WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent or QueryEvent')

    sql = ''
    if isinstance(binlog_event, WriteRowsEvent) or isinstance(binlog_event, UpdateRowsEvent) \
            or isinstance(binlog_event, DeleteRowsEvent):
        pattern = generate_sql_pattern(binlog_event, row=row, flashback=flashback, no_pk=no_pk)
        try:
            sql = cursor.mogrify(pattern['template'], pattern['values'])
            # 确保SQL是字符串类型，处理可能的bytes返回值
            if isinstance(sql, bytes):
                sql = sql.decode('utf-8', 'ignore')
        except UnicodeDecodeError:
            # 如果解码失败，使用ignore模式重试
            if isinstance(sql, bytes):
                sql = sql.decode('utf-8', 'ignore')
            else:
                # 如果不是bytes类型，转换为字符串
                sql = str(sql)
        time = datetime.datetime.fromtimestamp(binlog_event.timestamp)
        sql += ' #start %s end %s time %s' % (e_start_pos, binlog_event.packet.log_pos, time)
    elif flashback is False and isinstance(binlog_event, QueryEvent) and binlog_event.query != 'BEGIN' \
            and binlog_event.query != 'COMMIT':
        if binlog_event.schema:
            # 处理schema可能是bytes类型的情况
            schema = fix_object(binlog_event.schema)
            sql = 'USE {0};\n'.format(schema)
        sql += '{0};'.format(fix_object(binlog_event.query))

    return sql


def generate_sql_pattern(binlog_event, row=None, flashback=False, no_pk=False):
    """生成SQL模板和值"""
    template = ''
    values = []

    # 确保row不为None并且有正确的结构
    if row is None:
        row = {'values': {}, 'before_values': {}, 'after_values': {}}

    # 处理schema和table可能是bytes类型的情况
    schema = fix_object(binlog_event.schema)
    table = fix_object(binlog_event.table)

    if flashback is True:
        if isinstance(binlog_event, WriteRowsEvent):
            row_values = row.get('values', {})
            template = 'DELETE FROM `{0}`.`{1}` WHERE {2} LIMIT 1;'.format(
                schema, table,
                ' AND '.join(map(compare_items, row_values.items()))
            )
            values = map(fix_object, row_values.values())
        elif isinstance(binlog_event, DeleteRowsEvent):
            row_values = row.get('values', {})
            template = 'INSERT INTO `{0}`.`{1}`({2}) VALUES ({3});'.format(
                schema, table,
                ', '.join(map(lambda key: '`%s`' % fix_object(key), row_values.keys())),
                ', '.join(['%s'] * len(row_values))
            )
            values = map(fix_object, row_values.values())
        elif isinstance(binlog_event, UpdateRowsEvent):
            before_values = row.get('before_values', {})
            after_values = row.get('after_values', {})
            template = 'UPDATE `{0}`.`{1}` SET {2} WHERE {3} LIMIT 1;'.format(
                schema, table,
                ', '.join(['`%s`=%%s' % fix_object(x) for x in before_values.keys()]),
                ' AND '.join(map(compare_items, after_values.items())))
            values = map(fix_object, list(before_values.values())+list(after_values.values()))
    else:
        if isinstance(binlog_event, WriteRowsEvent):
            row_values = row.get('values', {})
            if no_pk:
                if hasattr(binlog_event, 'primary_key') and binlog_event.primary_key:
                    row_values.pop(binlog_event.primary_key, None)
            template = 'INSERT INTO `{0}`.`{1}`({2}) VALUES ({3});'.format(
                schema, table,
                ', '.join(map(lambda key: '`%s`' % fix_object(key), row_values.keys())),
                ', '.join(['%s'] * len(row_values))
            )
            values = map(fix_object, row_values.values())
        elif isinstance(binlog_event, DeleteRowsEvent):
            row_values = row.get('values', {})
            template = 'DELETE FROM `{0}`.`{1}` WHERE {2} LIMIT 1;'.format(
                schema, table,
                ' AND '.join(map(compare_items, row_values.items())))
            values = map(fix_object, row_values.values())
        elif isinstance(binlog_event, UpdateRowsEvent):
            before_values = row.get('before_values', {})
            after_values = row.get('after_values', {})
            template = 'UPDATE `{0}`.`{1}` SET {2} WHERE {3} LIMIT 1;'.format(
                schema, table,
                ', '.join(['`%s`=%%s' % fix_object(k) for k in after_values.keys()]),
                ' AND '.join(map(compare_items, before_values.items()))
            )
            values = map(fix_object, list(after_values.values())+list(before_values.values()))

    return {'template': template, 'values': list(values)}


def reversed_lines(fin):
    """按相反顺序生成文件行"""
    part = ''
    for block in reversed_blocks(fin):
        if PY3PLUS:
            block = block.decode("utf-8", 'ignore')  # 使用ignore忽略解码错误
        for c in reversed(block):
            if c == '\n' and part:
                yield part[::-1]
                part = ''
            part += c
    if part:
        yield part[::-1]


def reversed_blocks(fin, block_size=4096):
    """按相反顺序生成文件块"""
    fin.seek(0, os.SEEK_END)
    here = fin.tell()
    while 0 < here:
        delta = min(block_size, here)
        here -= delta
        fin.seek(here, os.SEEK_SET)
        yield fin.read(delta)
