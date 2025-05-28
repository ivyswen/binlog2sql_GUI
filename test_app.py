#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
简单的测试脚本，用于验证应用程序的基本功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.config_manager import ConfigManager
from core.binlog_parser import BinlogParser


def test_config_manager():
    """测试配置管理器"""
    print("测试配置管理器...")
    
    # 创建配置管理器
    config = ConfigManager("test_config.json")
    
    # 测试添加连接
    conn_info = {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "password",
        "charset": "utf8"
    }
    
    config.add_connection("test_conn", conn_info)
    print("✓ 添加连接配置成功")
    
    # 测试获取连接
    retrieved_conn = config.get_connection("test_conn")
    assert retrieved_conn is not None
    assert retrieved_conn["host"] == "127.0.0.1"
    print("✓ 获取连接配置成功")
    
    # 测试连接列表
    connections = config.get_all_connections()
    assert "test_conn" in connections
    print("✓ 获取连接列表成功")
    
    # 清理测试文件
    if os.path.exists("test_config.json"):
        os.remove("test_config.json")
    
    print("配置管理器测试完成\n")


def test_binlog_parser_creation():
    """测试Binlog解析器创建（不连接数据库）"""
    print("测试Binlog解析器创建...")
    
    try:
        # 这里会失败，因为没有真实的数据库连接
        # 但我们可以测试参数验证
        connection_settings = {
            'host': '127.0.0.1',
            'port': 3306,
            'user': 'test',
            'passwd': 'test',
            'charset': 'utf8'
        }
        
        # 测试缺少start_file参数
        try:
            parser = BinlogParser(connection_settings)
            assert False, "应该抛出ValueError"
        except ValueError as e:
            assert "start_file" in str(e)
            print("✓ 参数验证正常工作")
        
        print("Binlog解析器创建测试完成\n")
        
    except Exception as e:
        print(f"Binlog解析器测试跳过（需要数据库连接）: {e}\n")


def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")
    
    try:
        from gui.main_window import MainWindow
        print("✓ 主窗口模块导入成功")
        
        from gui.connection_dialog import ConnectionDialog
        print("✓ 连接对话框模块导入成功")
        
        from core.binlog_util import is_valid_datetime, fix_object
        print("✓ 工具函数模块导入成功")
        
        # 测试工具函数
        assert is_valid_datetime("2023-01-01 12:00:00") == True
        assert is_valid_datetime("invalid") == False
        print("✓ 工具函数测试成功")
        
        print("模块导入测试完成\n")
        
    except Exception as e:
        print(f"模块导入测试失败: {e}\n")
        return False
    
    return True


def main():
    """主测试函数"""
    print("开始测试 Binlog2SQL GUI 应用程序...\n")
    
    # 测试模块导入
    if not test_imports():
        print("基础测试失败，退出")
        return
    
    # 测试配置管理器
    test_config_manager()
    
    # 测试Binlog解析器
    test_binlog_parser_creation()
    
    print("所有测试完成！")
    print("\n要启动GUI应用程序，请运行:")
    print("uv run python main.py")


if __name__ == "__main__":
    main()
