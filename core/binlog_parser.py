#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import datetime
import pymysql
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.event import QueryEvent, RotateEvent, FormatDescriptionEvent
from .binlog_util import (
    concat_sql_from_binlog_event,
    create_unique_file,
    temp_open,
    reversed_lines,
    is_dml_event,
    event_type
)
from .logger import get_logger

# 获取logger实例
logger = get_logger("BinlogParser")


class BinlogParser(object):
    """Binlog解析器类"""

    def __init__(self, connection_settings, start_file=None, start_pos=None, end_file=None, end_pos=None,
                 start_time=None, stop_time=None, only_schemas=None, only_tables=None, no_pk=False,
                 flashback=False, stop_never=False, back_interval=1.0, only_dml=True, sql_type=None):
        """
        初始化Binlog解析器

        Args:
            connection_settings: 数据库连接配置 {'host': '127.0.0.1', 'port': 3306, 'user': 'user', 'passwd': 'passwd', 'charset': 'utf8'}
            start_file: 起始binlog文件
            start_pos: 起始位置
            end_file: 结束binlog文件
            end_pos: 结束位置
            start_time: 开始时间
            stop_time: 结束时间
            only_schemas: 只处理指定数据库
            only_tables: 只处理指定表
            no_pk: 生成不包含主键的insert语句
            flashback: 生成回滚SQL
            stop_never: 持续解析
            back_interval: 回滚SQL间隔时间
            only_dml: 只处理DML语句
            sql_type: SQL类型过滤
        """
        if not start_file:
            logger.error("缺少参数: start_file")
            raise ValueError('缺少参数: start_file')

        logger.info(f"初始化Binlog解析器: host={connection_settings.get('host')}, start_file={start_file}")
        self.conn_setting = connection_settings
        self.start_file = start_file
        self.start_pos = start_pos if start_pos else 4  # use binlog v4
        self.end_file = end_file if end_file else start_file
        self.end_pos = end_pos

        if start_time:
            self.start_time = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        else:
            self.start_time = datetime.datetime.strptime('1980-01-01 00:00:00', "%Y-%m-%d %H:%M:%S")

        if stop_time:
            self.stop_time = datetime.datetime.strptime(stop_time, "%Y-%m-%d %H:%M:%S")
        else:
            self.stop_time = datetime.datetime.strptime('2999-12-31 00:00:00', "%Y-%m-%d %H:%M:%S")

        self.only_schemas = only_schemas if only_schemas else None
        self.only_tables = only_tables if only_tables else None
        self.no_pk, self.flashback, self.stop_never, self.back_interval = (no_pk, flashback, stop_never, back_interval)
        self.only_dml = only_dml
        self.sql_type = [t.upper() for t in sql_type] if sql_type else []
        self.binlogList = []

        # 初始化数据库连接并获取binlog信息
        self._init_connection()

    def _init_connection(self):
        """初始化数据库连接并获取binlog信息"""
        try:
            logger.info(f"连接数据库: {self.conn_setting['host']}:{self.conn_setting['port']}")
            self.connection = pymysql.connect(**self.conn_setting)
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW MASTER STATUS")
                result = cursor.fetchone()
                if result:
                    self.eof_file, self.eof_pos = result[:2]
                else:
                    raise ValueError('无法获取MASTER STATUS')

                cursor.execute("SHOW MASTER LOGS")
                bin_index = [row[0] for row in cursor.fetchall()]

                if self.start_file not in bin_index:
                    logger.error(f"参数错误: start_file {self.start_file} 不在mysql服务器中")
                    raise ValueError('参数错误: start_file %s 不在mysql服务器中' % self.start_file)

                logger.info(f"找到binlog文件列表: {bin_index}")
                binlog2i = lambda x: x.split('.')[1]
                for binary in bin_index:
                    if binlog2i(self.start_file) <= binlog2i(binary) <= binlog2i(self.end_file):
                        self.binlogList.append(binary)

                logger.info(f"待解析的binlog文件: {self.binlogList}")

                cursor.execute("SELECT @@server_id")
                result = cursor.fetchone()
                if result:
                    self.server_id = result[0]
                else:
                    raise ValueError('缺少server_id在 %s:%s' % (self.conn_setting['host'], self.conn_setting['port']))

                if not self.server_id:
                    logger.error(f"缺少server_id在 {self.conn_setting['host']}:{self.conn_setting['port']}")
                    raise ValueError('缺少server_id在 %s:%s' % (self.conn_setting['host'], self.conn_setting['port']))

                logger.info(f"数据库连接成功, server_id: {self.server_id}")
        except Exception as e:
            logger.error(f"数据库连接失败: {str(e)}")
            raise ValueError(f'数据库连接失败: {str(e)}')

    def process_binlog(self, callback=None):
        """
        处理binlog

        Args:
            callback: 回调函数，用于处理生成的SQL语句

        Returns:
            bool: 处理是否成功
        """
        try:
            logger.info("开始解析binlog")
            logger.info(f"解析参数: start_file={self.start_file}, start_pos={self.start_pos}, "
                       f"end_file={self.end_file}, end_pos={self.end_pos}")
            logger.info(f"时间范围: {self.start_time} - {self.stop_time}")
            logger.info(f"过滤条件: schemas={self.only_schemas}, tables={self.only_tables}")
            logger.info(f"SQL类型: {self.sql_type}, flashback={self.flashback}")
            stream = BinLogStreamReader(
                connection_settings=self.conn_setting,
                server_id=self.server_id,
                log_file=self.start_file,
                log_pos=self.start_pos,
                only_schemas=self.only_schemas,
                only_tables=self.only_tables,
                resume_stream=True,
                blocking=True
            )

            flag_last_event = False
            e_start_pos, last_pos = stream.log_pos, stream.log_pos

            # 创建临时文件用于flashback模式
            tmp_file = create_unique_file('%s.%s' % (self.conn_setting['host'], self.conn_setting['port']))

            with temp_open(tmp_file, "w") as f_tmp, self.connection.cursor() as cursor:
                for binlog_event in stream:
                    if not self.stop_never:
                        try:
                            event_time = datetime.datetime.fromtimestamp(binlog_event.timestamp)
                        except OSError:
                            event_time = datetime.datetime(1980, 1, 1, 0, 0)

                        if (stream.log_file == self.end_file and stream.log_pos == self.end_pos) or \
                           (stream.log_file == self.eof_file and stream.log_pos == self.eof_pos):
                            flag_last_event = True
                        elif event_time < self.start_time:
                            if not (isinstance(binlog_event, RotateEvent) or isinstance(binlog_event, FormatDescriptionEvent)):
                                last_pos = binlog_event.packet.log_pos
                            continue
                        elif (stream.log_file not in self.binlogList) or \
                             (self.end_pos and stream.log_file == self.end_file and stream.log_pos > self.end_pos) or \
                             (stream.log_file == self.eof_file and stream.log_pos > self.eof_pos) or \
                             (event_time >= self.stop_time):
                            break

                    if isinstance(binlog_event, QueryEvent) and binlog_event.query == 'BEGIN':
                        e_start_pos = last_pos

                    if isinstance(binlog_event, QueryEvent) and not self.only_dml:
                        sql = concat_sql_from_binlog_event(
                            cursor=cursor,
                            binlog_event=binlog_event,
                            flashback=self.flashback,
                            no_pk=self.no_pk
                        )
                        if sql:
                            if callback:
                                callback(sql)
                            else:
                                print(sql)

                    elif is_dml_event(binlog_event) and event_type(binlog_event) in self.sql_type:
                        for row in binlog_event.rows:
                            sql = concat_sql_from_binlog_event(
                                cursor=cursor,
                                binlog_event=binlog_event,
                                no_pk=self.no_pk,
                                row=row,
                                flashback=self.flashback,
                                e_start_pos=e_start_pos
                            )
                            if self.flashback:
                                f_tmp.write(sql + '\n')
                            else:
                                if callback:
                                    callback(sql)
                                else:
                                    print(sql)

                    if not (isinstance(binlog_event, RotateEvent) or isinstance(binlog_event, FormatDescriptionEvent)):
                        last_pos = binlog_event.packet.log_pos

                    if flag_last_event:
                        break

            stream.close()

            if self.flashback:
                self._print_rollback_sql(filename=tmp_file, callback=callback)

            logger.info("binlog解析完成")
            return True

        except Exception as e:
            logger.error(f'处理binlog时发生错误: {str(e)}')
            raise Exception(f'处理binlog时发生错误: {str(e)}')

    def _print_rollback_sql(self, filename, callback=None):
        """打印回滚SQL"""
        with open(filename, "rb") as f_tmp:
            batch_size = 1000
            i = 0
            for line in reversed_lines(f_tmp):
                sql = line.rstrip()
                if callback:
                    callback(sql)
                else:
                    print(sql)

                if i >= batch_size:
                    i = 0
                    if self.back_interval:
                        sleep_sql = 'SELECT SLEEP(%s);' % self.back_interval
                        if callback:
                            callback(sleep_sql)
                        else:
                            print(sleep_sql)
                else:
                    i += 1

    def test_connection(self):
        """测试数据库连接"""
        try:
            connection = pymysql.connect(**self.conn_setting)
            connection.close()
            return True, "连接成功"
        except Exception as e:
            return False, f"连接失败: {str(e)}"

    def get_binlog_files(self):
        """获取可用的binlog文件列表"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW MASTER LOGS")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            raise Exception(f'获取binlog文件列表失败: {str(e)}')

    def __del__(self):
        """析构函数"""
        try:
            if hasattr(self, 'connection') and self.connection:
                self.connection.close()
        except:
            # 忽略关闭连接时的错误
            pass
