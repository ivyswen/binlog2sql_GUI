#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
日志功能演示脚本
展示loguru日志系统的各种功能
"""

import sys
import os
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.logger import get_logger

def demo_logging():
    """演示日志功能"""
    
    # 获取不同模块的logger
    main_logger = get_logger("Demo")
    parser_logger = get_logger("BinlogParser")
    gui_logger = get_logger("MainWindow")
    
    print("=== Binlog2SQL GUI 日志功能演示 ===\n")
    
    # 演示不同级别的日志
    print("1. 演示不同级别的日志:")
    main_logger.debug("这是DEBUG级别的日志 - 只在文件中记录")
    main_logger.info("这是INFO级别的日志 - 控制台和文件都会记录")
    main_logger.warning("这是WARNING级别的日志")
    main_logger.error("这是ERROR级别的日志 - 会同时记录到错误日志文件")
    
    print("\n2. 演示模拟应用程序流程:")
    
    # 模拟应用启动
    main_logger.info("应用程序启动")
    
    # 模拟数据库连接
    parser_logger.info("连接数据库: 192.168.1.100:3306")
    parser_logger.info("数据库连接成功, server_id: 12345")
    
    # 模拟用户操作
    gui_logger.info("用户开始解析binlog")
    parser_logger.info("初始化Binlog解析器: host=192.168.1.100, start_file=mysql-bin.000001")
    
    # 模拟解析过程
    parser_logger.info("开始解析binlog")
    parser_logger.info("解析参数: start_file=mysql-bin.000001, start_pos=4")
    parser_logger.info("时间范围: 2025-05-27 00:00:00 - 2025-05-28 00:00:00")
    parser_logger.info("过滤条件: schemas=['test_db'], tables=['users']")
    parser_logger.info("SQL类型: ['INSERT', 'UPDATE', 'DELETE'], flashback=False")
    
    # 模拟处理进度
    for i in range(1, 6):
        time.sleep(0.5)
        parser_logger.debug(f"处理进度: {i*20}%")
    
    # 模拟完成
    parser_logger.info("binlog解析完成")
    gui_logger.info("解析任务完成")
    
    print("\n3. 演示错误处理:")
    
    # 模拟各种错误
    try:
        # 模拟连接错误
        raise ConnectionError("无法连接到数据库: 连接超时")
    except Exception as e:
        parser_logger.error(f"数据库连接失败: {str(e)}")
    
    try:
        # 模拟解码错误
        raise UnicodeDecodeError("utf-8", b'\xe7', 140, 141, "unexpected end of data")
    except Exception as e:
        parser_logger.error(f"UTF-8解码错误: {str(e)}")
    
    try:
        # 模拟文件不存在错误
        raise FileNotFoundError("binlog文件不存在: mysql-bin.000999")
    except Exception as e:
        parser_logger.error(f"文件错误: {str(e)}")
    
    print("\n4. 演示结构化日志:")
    
    # 使用bind添加上下文信息
    context_logger = main_logger.bind(user_id="admin", session_id="abc123")
    context_logger.info("用户登录成功")
    context_logger.info("开始解析任务", task_id="task_001", binlog_file="mysql-bin.000001")
    
    print("\n5. 日志文件位置:")
    log_dir = os.path.abspath("logs")
    print(f"日志目录: {log_dir}")
    
    if os.path.exists(log_dir):
        log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
        if log_files:
            print("当前日志文件:")
            for log_file in sorted(log_files):
                file_path = os.path.join(log_dir, log_file)
                file_size = os.path.getsize(file_path)
                print(f"  - {log_file} ({file_size} bytes)")
        else:
            print("暂无日志文件")
    
    print("\n=== 演示完成 ===")
    print("请查看 logs/ 目录下的日志文件:")
    print("- binlog2sql_YYYY-MM-DD.log: 主日志文件")
    print("- error_YYYY-MM-DD.log: 错误日志文件")
    
    main_logger.info("日志演示完成")


if __name__ == "__main__":
    demo_logging()
