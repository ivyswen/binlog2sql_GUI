#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
大事务分析核心逻辑模块
基于 MySQL replication 协议在线读取 Binlog，分析统计 Top N 大事务。
严格对齐 binlog_bigtxn.py 的统计口径与字段结构。
"""

import datetime
from collections import Counter
import pymysql
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.event import (
    QueryEvent,
    XidEvent,
    RotateEvent,
    FormatDescriptionEvent,
)
from pymysqlreplication.row_event import (
    TableMapEvent,
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)
from .logger import get_logger

logger = get_logger("BigTxnAnalyzer")


class BigTxnAnalyzer(object):
    """大事务分析器"""

    def __init__(self, connection_settings, binlog_file, top_n=20):
        """
        初始化大事务分析器

        Args:
            connection_settings: 数据库连接参数 dict
            binlog_file: 要分析的单个 Binlog 文件名 (如 'mysql-bin.000001')
            top_n: 保留的最大事务数量，默认 20
        """
        if not binlog_file:
            raise ValueError("必须指定要分析的 binlog_file")

        self.conn_settings = connection_settings.copy()
        if "charset" not in self.conn_settings:
            self.conn_settings["charset"] = "utf8mb4"

        self.binlog_file = binlog_file
        self.top_n = max(1, int(top_n))

        self.is_running = True
        self.progress_callback = None
        self.total_size = 0
        self.top_txns = []  # 记录 Top N 事务
        self.scanned_txn_count = 0

    def set_progress_callback(self, callback):
        """
        设置进度回调函数
        callback(percent: int, current_pos: int, total_size: int, txn_count: int, status_msg: str)
        """
        self.progress_callback = callback

    def stop(self):
        """请求停止分析"""
        logger.info(f"收到停止分析请求: {self.binlog_file}")
        self.is_running = False

    def _get_file_size_and_server_id(self):
        """连接数据库获取 binlog 文件大小及 server_id"""
        conn = pymysql.connect(**self.conn_settings)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT @@server_id")
                row = cursor.fetchone()
                if not row or not row[0]:
                    raise ValueError("无法获取数据库 server_id")
                server_id = row[0]

                cursor.execute("SHOW MASTER LOGS")
                logs = cursor.fetchall()
                # logs format: [(Log_name, File_size, ...)]
                file_size = 0
                file_exists = False
                for r in logs:
                    if r[0] == self.binlog_file:
                        file_exists = True
                        file_size = int(r[1])
                        break

                if not file_exists:
                    logger.warning(
                        f"目标文件 {self.binlog_file} 不在 SHOW MASTER LOGS 列表中，将使用默认大小估计"
                    )

                return server_id, file_size
        finally:
            conn.close()

    def analyze(self):
        """
        执行大事务分析

        Returns:
            list[dict]: 排序后的 Top N 事务列表
        """
        self.is_running = True
        self.top_txns = []
        self.scanned_txn_count = 0

        logger.info(f"开始大事务分析: file={self.binlog_file}, top_n={self.top_n}")

        server_id, self.total_size = self._get_file_size_and_server_id()
        logger.info(
            f"获取到 server_id={server_id}, 文件 {self.binlog_file} 大小={self.total_size} 字节"
        )

        stream_settings = self.conn_settings.copy()
        stream_settings.update(
            {
                "use_unicode": True,
                "charset": "utf8mb4",
                "sql_mode": "TRADITIONAL",
                "init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
            }
        )

        # 仅接收关键事件，提升性能
        interested_events = [
            QueryEvent,
            XidEvent,
            RotateEvent,
            FormatDescriptionEvent,
            TableMapEvent,
            WriteRowsEvent,
            UpdateRowsEvent,
            DeleteRowsEvent,
        ]

        stream = None
        try:
            stream = BinLogStreamReader(
                connection_settings=stream_settings,
                server_id=server_id,
                log_file=self.binlog_file,
                log_pos=4,
                only_events=interested_events,
                resume_stream=True,
                blocking=False,
                fail_on_table_metadata_unavailable=False,
                ignore_decode_errors=True,
                freeze_schema=False,
                verify_checksum=False,
            )

            # 当前事务状态跟踪
            txn = None
            last_end = 4
            last_pos = 4
            cur_time = ""
            cur_thread = ""

            def finish_txn(end_pos, incomplete=False):
                nonlocal txn
                if txn is None:
                    return
                self.scanned_txn_count += 1
                size = max(0, end_pos - txn["start"])
                rec = {
                    "size": size,
                    "start": txn["start"],
                    "end": end_pos,
                    "xid": txn["xid"],
                    "thread": txn["thread"],
                    "time": txn["time"],
                    "tables": txn["tables"],
                    "ops": txn["ops"],
                    "incomplete": incomplete,
                }

                # 维护 Top N 列表
                if len(self.top_txns) < self.top_n:
                    self.top_txns.append(rec)
                else:
                    # 替换掉当前最小的
                    min_idx = min(
                        range(len(self.top_txns)), key=lambda k: self.top_txns[k]["size"]
                    )
                    if rec["size"] > self.top_txns[min_idx]["size"]:
                        self.top_txns[min_idx] = rec

                txn = None

            event_count = 0
            for binlog_event in stream:
                if not self.is_running:
                    logger.info("用户停止分析")
                    break

                # 检查是否切换到了下一个 binlog 文件
                if stream.log_file and stream.log_file != self.binlog_file:
                    logger.info(
                        f"检测到 binlog 文件切换: {stream.log_file} != {self.binlog_file}，分析结束"
                    )
                    break

                event_count += 1
                cur_end_pos = getattr(getattr(binlog_event, "packet", None), "log_pos", last_end)
                if cur_end_pos:
                    last_end = cur_end_pos

                # 时间戳记录
                if hasattr(binlog_event, "timestamp") and binlog_event.timestamp:
                    try:
                        cur_time = datetime.datetime.fromtimestamp(
                            binlog_event.timestamp
                        ).strftime("%H:%M:%S")
                    except Exception:
                        pass

                # RotateEvent 检查
                if isinstance(binlog_event, RotateEvent):
                    if (
                        hasattr(binlog_event, "next_binlog")
                        and binlog_event.next_binlog
                        and binlog_event.next_binlog != self.binlog_file
                    ):
                        logger.info(
                            f"遇到 RotateEvent 到 {binlog_event.next_binlog}，结束文件分析"
                        )
                        break

                # QueryEvent 处理
                if isinstance(binlog_event, QueryEvent):
                    if hasattr(binlog_event, "slave_proxy_id"):
                        cur_thread = str(binlog_event.slave_proxy_id)

                    query = getattr(binlog_event, "query", "") or ""
                    query_upper = query.strip().upper()

                    if query_upper == "BEGIN" or query_upper.startswith("BEGIN"):
                        # 如果之前已有未闭合事务（例如异常崩溃或非标准日志），先结算之前的
                        if txn is not None:
                            finish_txn(last_pos, incomplete=True)
                        txn = {
                            "start": last_pos,
                            "time": cur_time,
                            "thread": cur_thread,
                            "xid": "",
                            "tables": Counter(),
                            "ops": Counter(),
                        }
                    elif query_upper == "COMMIT" or query_upper.startswith("COMMIT"):
                        finish_txn(last_end)
                    elif query_upper == "ROLLBACK" or query_upper.startswith("ROLLBACK"):
                        finish_txn(last_end)

                # TableMapEvent 处理
                elif isinstance(binlog_event, TableMapEvent):
                    if txn is not None:
                        schema = getattr(binlog_event, "schema", "")
                        table = getattr(binlog_event, "table", "")
                        table_name = f"`{schema}`.`{table}`"
                        txn["tables"][table_name] += 1

                # Row Events 处理
                elif isinstance(binlog_event, WriteRowsEvent):
                    if txn is not None:
                        txn["ops"]["Write_rows"] += 1
                elif isinstance(binlog_event, UpdateRowsEvent):
                    if txn is not None:
                        txn["ops"]["Update_rows"] += 1
                elif isinstance(binlog_event, DeleteRowsEvent):
                    if txn is not None:
                        txn["ops"]["Delete_rows"] += 1

                # XidEvent 处理 (事务提交)
                elif isinstance(binlog_event, XidEvent):
                    if txn is not None:
                        txn["xid"] = str(getattr(binlog_event, "xid", ""))
                        finish_txn(last_end)

                # 记录本事件结束点，作为下一事件的起始点
                if not (
                    isinstance(binlog_event, RotateEvent)
                    or isinstance(binlog_event, FormatDescriptionEvent)
                ):
                    last_pos = last_end

                # 周期性汇报进度
                if event_count % 100 == 0 and self.progress_callback:
                    pct = 0
                    if self.total_size > 0:
                        pct = min(100, int((last_end / self.total_size) * 100))
                    msg = f"正在扫描: {self.binlog_file} (已扫描 Pos: {last_end}, 事务数: {self.scanned_txn_count})"
                    self.progress_callback(pct, last_end, self.total_size, self.scanned_txn_count, msg)

            # 流处理结束，处理可能留在末尾未提交的事务
            finish_txn(last_end, incomplete=True)

            if self.progress_callback:
                msg = f"分析完成: 共扫描 {self.scanned_txn_count} 个事务"
                self.progress_callback(100, last_end, self.total_size, self.scanned_txn_count, msg)

        except Exception as e:
            logger.error(f"大事务分析异常: {str(e)}")
            raise e
        finally:
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass

        # 按事务大小降序排列
        self.top_txns.sort(key=lambda x: x["size"], reverse=True)
        logger.info(f"大事务分析完成，共返回 Top {len(self.top_txns)} 个事务")
        return self.top_txns
