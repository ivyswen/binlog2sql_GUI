#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MySQL版本检测脚本
自动检测MySQL版本并推荐合适的分支
"""

import json
import pymysql
import sys
import subprocess
import os

def detect_mysql_version():
    """检测MySQL版本并推荐分支"""
    try:
        # 读取配置文件
        config_file = 'config.json'
        if not os.path.exists(config_file):
            print("❌ 未找到config.json文件")
            print("请先运行GUI程序并配置数据库连接")
            return
            
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if not config.get('connections'):
            print("❌ 未找到数据库连接配置")
            print("请先在GUI中配置数据库连接")
            return
        
        # 获取第一个连接配置
        conn_name = list(config['connections'].keys())[0]
        conn_settings = config['connections'][conn_name]
        
        print(f"🔍 检测MySQL版本 (连接: {conn_name})")
        print(f"主机: {conn_settings['host']}:{conn_settings['port']}")
        
        # 连接数据库
        connection = pymysql.connect(**conn_settings)
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            
            cursor.execute("SELECT @@version_comment")
            comment = cursor.fetchone()[0]
        
        connection.close()
        
        # 解析版本号
        major_version = int(version.split('.')[0])
        minor_version = int(version.split('.')[1])
        
        print(f"\n📊 MySQL版本信息:")
        print(f"版本: {version}")
        print(f"类型: {comment}")
        
        # 推荐分支
        print(f"\n🎯 分支推荐:")
        if major_version >= 8:
            print(f"✅ 推荐使用: mysql-8.0 分支")
            print(f"命令: git checkout mysql-8.0")
            print(f"原因: MySQL {major_version}.{minor_version} 需要 mysql-replication>=1.0.0")
            recommended_branch = "mysql-8.0"
        else:
            print(f"✅ 推荐使用: main 分支")
            print(f"命令: git checkout main")
            print(f"原因: MySQL {major_version}.{minor_version} 需要 mysql-replication<=0.45.1")
            recommended_branch = "main"
        
        # 检查当前分支
        try:
            result = subprocess.run(['git', 'branch', '--show-current'], 
                                  capture_output=True, text=True, check=True)
            current_branch = result.stdout.strip()
            
            print(f"\n🌿 当前分支: {current_branch}")
            
            if recommended_branch != current_branch:
                print("⚠️ 警告: 当前分支可能不兼容您的MySQL版本")
                print(f"建议切换到: {recommended_branch}")
                
                # 询问是否自动切换
                response = input(f"\n是否自动切换到 {recommended_branch} 分支? (y/N): ")
                if response.lower() == 'y':
                    try:
                        subprocess.run(['git', 'checkout', recommended_branch], check=True)
                        print(f"✅ 已切换到 {recommended_branch} 分支")
                        
                        # 更新依赖
                        print("🔄 更新依赖...")
                        subprocess.run(['uv', 'sync'], check=True)
                        print("✅ 依赖更新完成")
                        
                    except subprocess.CalledProcessError as e:
                        print(f"❌ 切换分支失败: {e}")
            else:
                print("✅ 当前分支与MySQL版本兼容")
                
        except subprocess.CalledProcessError:
            print("无法检测当前Git分支")
        
        return major_version
        
    except FileNotFoundError:
        print("❌ 未找到config.json文件")
        print("请先运行GUI程序并配置数据库连接")
    except Exception as e:
        print(f"❌ 检测失败: {str(e)}")
        print("请检查数据库连接配置是否正确")
        return None

def show_branch_info():
    """显示分支信息"""
    print("\n📚 分支信息:")
    print("┌─────────────────┬──────────────────┬─────────────────────┐")
    print("│ MySQL版本       │ 推荐分支         │ mysql-replication   │")
    print("├─────────────────┼──────────────────┼─────────────────────┤")
    print("│ 5.5, 5.6, 5.7   │ main             │ 0.45.1              │")
    print("│ 8.0+            │ mysql-8.0        │ >=1.0.9             │")
    print("└─────────────────┴──────────────────┴─────────────────────┘")

def main():
    """主函数"""
    print("🚀 MySQL版本检测工具")
    print("=" * 50)
    
    # 检查是否在Git仓库中
    if not os.path.exists(".git"):
        print("❌ 当前目录不是Git仓库")
        show_branch_info()
        return
    
    # 检测MySQL版本
    mysql_version = detect_mysql_version()
    
    # 显示分支信息
    show_branch_info()
    
    if mysql_version:
        print(f"\n💡 提示:")
        if mysql_version >= 8:
            print("- MySQL 8.0需要设置 binlog_row_metadata=FULL 和 binlog_row_image=FULL")
            print("- 确保使用 mysql-8.0 分支以获得最佳兼容性")
        else:
            print("- MySQL 5.7使用经过充分测试的稳定版本")
            print("- 确保使用 main 分支以获得最佳兼容性")

if __name__ == "__main__":
    main()
