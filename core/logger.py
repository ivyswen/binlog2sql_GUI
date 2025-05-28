#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from loguru import logger


def setup_logger():
    """配置loguru日志器"""
    
    # 移除默认的控制台处理器
    logger.remove()
    
    # 创建logs目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 控制台日志 - 只显示INFO及以上级别
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True
    )
    
    # 文件日志 - 按天分割，保留30天
    logger.add(
        os.path.join(log_dir, "binlog2sql_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # 每天午夜轮转
        retention="30 days",  # 保留30天
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
        enqueue=True  # 异步写入
    )
    
    # 错误日志单独记录
    logger.add(
        os.path.join(log_dir, "error_{time:YYYY-MM-DD}.log"),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True
    )
    
    # 记录启动信息
    logger.info("Binlog2SQL GUI 应用程序启动")
    logger.info(f"日志目录: {os.path.abspath(log_dir)}")
    
    return logger


def get_logger(name=None):
    """获取logger实例"""
    if name:
        return logger.bind(name=name)
    return logger


# 全局logger实例
app_logger = setup_logger()
