#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import datetime
import pymysql
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.event import QueryEvent, RotateEvent, FormatDescriptionEvent
from .binlog_util import (
    concat_sql_from_binlog_event,
    create_unique_file,
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
            # 确保使用UTF-8字符集
            conn_settings = self.conn_setting.copy()
            if 'charset' not in conn_settings:
                conn_settings['charset'] = 'utf8mb4'
            self.connection = pymysql.connect(**conn_settings)
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

            # 确保BinLogStreamReader使用UTF-8字符集，并增加容错处理
            stream_conn_settings = self.conn_setting.copy()
            if 'charset' not in stream_conn_settings:
                stream_conn_settings['charset'] = 'utf8mb4'

            # 添加额外的连接参数以提高编码兼容性
            stream_conn_settings.update({
                'use_unicode': True,
                'charset': 'utf8mb4',
                'sql_mode': 'TRADITIONAL',
                'init_command': "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"
            })

            logger.info(f"使用连接配置: charset={stream_conn_settings.get('charset')}")

            try:
                stream = BinLogStreamReader(
                    connection_settings=stream_conn_settings,
                    server_id=self.server_id,
                    log_file=self.start_file,
                    log_pos=self.start_pos,
                    only_schemas=self.only_schemas,
                    only_tables=self.only_tables,
                    resume_stream=True,
                    blocking=True,
                    # 添加额外的容错参数
                    fail_on_table_metadata_unavailable=False
                )
            except Exception as stream_error:
                logger.error(f"创建BinLogStreamReader失败: {str(stream_error)}")
                # 尝试使用更基本的字符集配置重试
                fallback_settings = self.conn_setting.copy()
                fallback_settings['charset'] = 'utf8'
                logger.info("尝试使用fallback字符集配置重新创建stream...")

                stream = BinLogStreamReader(
                    connection_settings=fallback_settings,
                    server_id=self.server_id,
                    log_file=self.start_file,
                    log_pos=self.start_pos,
                    only_schemas=self.only_schemas,
                    only_tables=self.only_tables,
                    resume_stream=True,
                    blocking=True,
                    fail_on_table_metadata_unavailable=False
                )

            flag_last_event = False
            e_start_pos, last_pos = stream.log_pos, stream.log_pos

            # 创建临时文件用于flashback模式
            # 将IP地址中的点号和端口号组合成安全的文件名
            safe_host = self.conn_setting['host'].replace('.', '_').replace(':', '_')
            safe_port = str(self.conn_setting['port'])
            tmp_file = create_unique_file('binlog_tmp_%s_%s' % (safe_host, safe_port))

            # 在flashback模式下，需要在处理完所有事件后才读取临时文件，所以不能使用temp_open
            f_tmp = open(tmp_file, "w", encoding="utf-8", errors="ignore")
            try:
                with self.connection.cursor() as cursor:
                    # 使用安全的事件迭代器，自动处理编码错误
                    logger.info("开始使用安全事件迭代器处理binlog事件...")
                    for binlog_event in self._safe_event_iterator(stream):
                        try:
                            # 首先修复事件中的编码问题
                            try:
                                self._fix_event_encoding(binlog_event)
                            except Exception as e:
                                logger.warning(f"修复事件编码时发生错误，跳过该事件: {str(e)}")
                                continue

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
                                try:
                                    sql = concat_sql_from_binlog_event(
                                        cursor=cursor,
                                        binlog_event=binlog_event,
                                        flashback=self.flashback,
                                        no_pk=self.no_pk
                                    )
                                    if sql:
                                        # 确保SQL是正确编码的字符串
                                        if isinstance(sql, bytes):
                                            sql = sql.decode('utf-8', 'ignore')
                                        if callback:
                                            callback(sql)
                                        else:
                                            print(sql)
                                except UnicodeDecodeError as e:
                                    logger.warning(f"处理QueryEvent时发生编码错误，跳过该事件: {str(e)}")
                                    continue
                                except Exception as e:
                                    logger.error(f"处理QueryEvent时发生错误: {str(e)}")
                                    continue

                            elif is_dml_event(binlog_event) and event_type(binlog_event) in self.sql_type:
                                for row in binlog_event.rows:
                                    try:
                                        sql = concat_sql_from_binlog_event(
                                            cursor=cursor,
                                            binlog_event=binlog_event,
                                            no_pk=self.no_pk,
                                            row=row,
                                            flashback=self.flashback,
                                            e_start_pos=e_start_pos
                                        )
                                        if self.flashback:
                                            # 确保写入文件的内容是正确编码的字符串
                                            if isinstance(sql, bytes):
                                                sql = sql.decode('utf-8', 'ignore')
                                            f_tmp.write(sql + '\n')
                                        else:
                                            if callback:
                                                callback(sql)
                                            else:
                                                print(sql)
                                    except UnicodeDecodeError as e:
                                        logger.warning(f"处理行数据时发生编码错误，跳过该行: {str(e)}")
                                        continue
                                    except Exception as e:
                                        logger.error(f"处理行数据时发生错误: {str(e)}")
                                        continue

                            if not (isinstance(binlog_event, RotateEvent) or isinstance(binlog_event, FormatDescriptionEvent)):
                                last_pos = binlog_event.packet.log_pos

                            if flag_last_event:
                                break

                        except UnicodeDecodeError as e:
                            logger.warning(f"处理binlog事件时发生编码错误，跳过该事件: {str(e)}")
                            continue
                        except Exception as e:
                            logger.error(f"处理binlog事件时发生错误: {str(e)}")
                            # 对于非编码错误，我们继续处理下一个事件
                            continue

                stream.close()

                if self.flashback:
                    f_tmp.close()  # 关闭文件以便读取
                    self._print_rollback_sql(filename=tmp_file, callback=callback)

                logger.info("binlog解析完成")
                return True
            finally:
                # 确保文件被关闭和删除
                try:
                    if not f_tmp.closed:
                        f_tmp.close()
                except:
                    pass
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except:
                    pass

        except Exception as e:
            error_msg = str(e)
            logger.error(f'处理binlog时发生错误: {error_msg}')

            # 检查是否是编码错误
            if 'utf-8' in error_msg.lower() or 'decode' in error_msg.lower() or 'unicode' in error_msg.lower():
                logger.warning("检测到编码错误，但解析器已处理了部分数据。建议检查数据库字符集设置。")

                # 如果是flashback模式，尝试读取已写入的临时文件
                if self.flashback:
                    try:
                        # 确保临时文件已关闭（如果文件对象存在的话）
                        try:
                            if 'f_tmp' in locals() and f_tmp and not f_tmp.closed:
                                f_tmp.close()
                        except:
                            pass

                        # 尝试读取并输出回滚SQL
                        if 'tmp_file' in locals() and os.path.exists(tmp_file):
                            logger.info("尝试读取flashback模式下的临时文件...")
                            self._print_rollback_sql(filename=tmp_file, callback=callback)
                            logger.info("flashback模式下的临时文件读取完成")
                    except Exception as flashback_error:
                        logger.error(f"读取flashback临时文件时发生错误: {str(flashback_error)}")

                # 对于编码错误，我们返回True表示部分成功，而不是抛出异常
                return True
            else:
                # 对于其他类型的错误，仍然抛出异常
                raise Exception(f'处理binlog时发生错误: {error_msg}')

    def _safe_event_iterator(self, stream):
        """安全的事件迭代器，捕获所有可能的编码错误"""
        event_count = 0
        skipped_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 10  # 最大连续错误数

        logger.info("启动安全事件迭代器...")

        while True:
            try:
                # 尝试获取下一个事件
                try:
                    # BinLogStreamReader需要使用iter()来获取迭代器
                    if not hasattr(self, '_stream_iterator'):
                        self._stream_iterator = iter(stream)

                    event = next(self._stream_iterator)
                    event_count += 1
                    consecutive_errors = 0  # 重置连续错误计数

                    # 每处理500个事件记录一次进度
                    if event_count % 500 == 0:
                        logger.info(f"已处理 {event_count} 个事件，跳过 {skipped_count} 个问题事件")

                except StopIteration:
                    # 正常结束
                    logger.info(f"事件流结束，总共处理 {event_count} 个事件，跳过 {skipped_count} 个问题事件")
                    break
                except UnicodeDecodeError as e:
                    consecutive_errors += 1
                    skipped_count += 1
                    logger.warning(f"跳过编码错误的binlog事件 #{event_count + skipped_count}: {str(e)}")

                    # 如果连续错误太多，可能是严重的编码问题
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"连续遇到 {consecutive_errors} 个编码错误，可能存在严重的字符集问题")
                        break
                    continue
                except Exception as e:
                    consecutive_errors += 1
                    skipped_count += 1
                    error_msg = str(e)

                    # 检查是否是编码相关的错误
                    if any(keyword in error_msg.lower() for keyword in ['utf-8', 'decode', 'unicode', 'encoding']):
                        logger.warning(f"跳过编码相关错误的binlog事件 #{event_count + skipped_count}: {error_msg}")
                    else:
                        logger.warning(f"跳过无法读取的binlog事件 #{event_count + skipped_count}: {error_msg}")

                    # 如果连续错误太多，停止处理
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"连续遇到 {consecutive_errors} 个错误，停止处理")
                        break
                    continue

                try:
                    # 预处理事件，确保所有字符串字段都是正确编码的
                    self._fix_event_encoding(event)
                    yield event

                except UnicodeDecodeError as e:
                    skipped_count += 1
                    logger.warning(f"跳过包含编码错误的binlog事件 #{event_count}: {str(e)}")
                    continue
                except Exception as e:
                    skipped_count += 1
                    logger.warning(f"跳过处理失败的binlog事件 #{event_count}: {str(e)}")
                    continue

            except Exception as e:
                logger.error(f"binlog流迭代时发生严重错误: {str(e)}")
                # 检查是否是编码错误
                if any(keyword in str(e).lower() for keyword in ['utf-8', 'decode', 'unicode', 'encoding']):
                    logger.error("检测到严重的编码错误，建议检查MySQL服务器字符集配置")
                break

        if skipped_count > 0:
            logger.warning(f"总共跳过了 {skipped_count} 个有问题的binlog事件，成功处理了 {event_count} 个事件")
        else:
            logger.info(f"成功处理了 {event_count} 个事件，没有跳过任何事件")

    def _fix_event_encoding(self, event):
        """修复事件中的编码问题"""
        try:
            # 修复schema字段
            if hasattr(event, 'schema') and event.schema is not None:
                if isinstance(event.schema, bytes):
                    try:
                        event.schema = event.schema.decode('utf-8', 'ignore')
                    except:
                        event.schema = str(event.schema)
                elif not isinstance(event.schema, str):
                    event.schema = str(event.schema)

            # 修复table字段
            if hasattr(event, 'table') and event.table is not None:
                if isinstance(event.table, bytes):
                    try:
                        event.table = event.table.decode('utf-8', 'ignore')
                    except:
                        event.table = str(event.table)
                elif not isinstance(event.table, str):
                    event.table = str(event.table)

            # 修复query字段
            if hasattr(event, 'query') and event.query is not None:
                if isinstance(event.query, bytes):
                    try:
                        event.query = event.query.decode('utf-8', 'ignore')
                    except:
                        event.query = str(event.query)
                elif not isinstance(event.query, str):
                    event.query = str(event.query)

            # 修复其他可能的字符串字段
            for attr_name in ['next_binlog', 'ident']:
                if hasattr(event, attr_name):
                    attr_value = getattr(event, attr_name)
                    if attr_value is not None and isinstance(attr_value, bytes):
                        try:
                            setattr(event, attr_name, attr_value.decode('utf-8', 'ignore'))
                        except:
                            setattr(event, attr_name, str(attr_value))

            # 修复行数据中的编码问题
            if hasattr(event, 'rows') and event.rows is not None:
                try:
                    for row in event.rows:
                        self._fix_row_encoding(row)
                except Exception as row_error:
                    logger.warning(f"修复行数据编码时发生错误: {str(row_error)}")

        except Exception as e:
            logger.warning(f"修复事件编码时发生错误: {str(e)}")
            # 不抛出异常，让调用者决定如何处理

    def _fix_row_encoding(self, row):
        """修复行数据中的编码问题"""
        try:
            # 修复values字典
            if hasattr(row, 'values') and isinstance(row.values, dict):
                self._fix_dict_encoding(row.values, 'values')

            # 修复before_values字典
            if hasattr(row, 'before_values') and isinstance(row.before_values, dict):
                self._fix_dict_encoding(row.before_values, 'before_values')

            # 修复after_values字典
            if hasattr(row, 'after_values') and isinstance(row.after_values, dict):
                self._fix_dict_encoding(row.after_values, 'after_values')

        except Exception as e:
            logger.warning(f"修复行数据编码时发生错误: {str(e)}")
            # 不抛出异常，让调用者决定如何处理

    def _fix_dict_encoding(self, data_dict, dict_name):
        """修复字典中的编码问题"""
        try:
            for key, value in list(data_dict.items()):
                # 修复key的编码问题
                if isinstance(key, bytes):
                    try:
                        new_key = key.decode('utf-8', 'ignore')
                        if new_key != key:
                            data_dict[new_key] = data_dict.pop(key)
                            key = new_key
                    except:
                        new_key = str(key)
                        data_dict[new_key] = data_dict.pop(key)
                        key = new_key

                # 修复value的编码问题
                if isinstance(value, bytes):
                    try:
                        data_dict[key] = value.decode('utf-8', 'ignore')
                    except:
                        data_dict[key] = str(value)
                elif value is not None and not isinstance(value, (str, int, float, bool, type(None))):
                    # 对于其他类型，尝试转换为字符串
                    try:
                        data_dict[key] = str(value)
                    except:
                        data_dict[key] = repr(value)

        except Exception as e:
            logger.warning(f"修复{dict_name}字典编码时发生错误: {str(e)}")

    def _print_rollback_sql(self, filename, callback=None):
        """打印回滚SQL"""
        try:
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
        except UnicodeDecodeError as e:
            logger.error(f"读取临时文件时发生UTF-8解码错误: {str(e)}")
            # 尝试使用ignore模式重新读取
            try:
                with open(filename, "r", encoding="utf-8", errors="ignore") as f_tmp:
                    lines = f_tmp.readlines()
                    for line in reversed(lines):
                        sql = line.rstrip()
                        if sql and callback:
                            callback(sql)
                        elif sql:
                            print(sql)
            except Exception as e2:
                logger.error(f"使用ignore模式读取临时文件也失败: {str(e2)}")
                raise e

    def test_connection(self):
        """测试数据库连接"""
        try:
            # 确保使用UTF-8字符集
            conn_settings = self.conn_setting.copy()
            if 'charset' not in conn_settings:
                conn_settings['charset'] = 'utf8mb4'
            connection = pymysql.connect(**conn_settings)
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
