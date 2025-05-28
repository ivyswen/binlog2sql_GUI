#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
快速设置脚本
帮助用户根据MySQL版本快速配置正确的分支和依赖
"""

import os
import sys
import subprocess
import json

def run_command(cmd, check=True):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        if check:
            print(f"❌ 命令执行失败: {e}")
            print(f"错误输出: {e.stderr}")
            sys.exit(1)
        return e

def detect_mysql_version_from_config():
    """从配置文件检测MySQL版本"""
    try:
        if not os.path.exists('config.json'):
            return None
            
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if not config.get('connections'):
            return None
        
        # 获取第一个连接配置
        conn_name = list(config['connections'].keys())[0]
        conn_settings = config['connections'][conn_name]
        
        import pymysql
        connection = pymysql.connect(**conn_settings)
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
        
        connection.close()
        
        major_version = int(version.split('.')[0])
        return major_version, version
        
    except Exception:
        return None

def get_current_branch():
    """获取当前Git分支"""
    try:
        result = run_command('git branch --show-current', check=False)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None

def setup_mysql57():
    """设置MySQL 5.7环境"""
    print("🔧 配置MySQL 5.7环境...")
    
    # 切换到main分支
    run_command('git checkout main')
    
    # 更新依赖
    print("📦 更新依赖到MySQL 5.7兼容版本...")
    run_command('uv remove mysql-replication', check=False)
    run_command('uv add "mysql-replication==0.45.1"')
    
    print("✅ MySQL 5.7环境配置完成")

def setup_mysql80():
    """设置MySQL 8.0环境"""
    print("🔧 配置MySQL 8.0环境...")
    
    # 检查mysql-8.0分支是否存在
    result = run_command('git branch -r | grep mysql-8.0', check=False)
    if result.returncode != 0:
        print("📝 创建mysql-8.0分支...")
        run_command('git checkout -b mysql-8.0')
    else:
        run_command('git checkout mysql-8.0')
    
    # 更新依赖
    print("📦 更新依赖到MySQL 8.0兼容版本...")
    run_command('uv remove mysql-replication', check=False)
    run_command('uv add "mysql-replication>=1.0.9"')
    
    print("✅ MySQL 8.0环境配置完成")

def interactive_setup():
    """交互式设置"""
    print("🤔 无法自动检测MySQL版本，请手动选择:")
    print("1. MySQL 5.5/5.6/5.7")
    print("2. MySQL 8.0+")
    
    while True:
        choice = input("请选择 (1 或 2): ").strip()
        if choice == '1':
            setup_mysql57()
            break
        elif choice == '2':
            setup_mysql80()
            break
        else:
            print("❌ 无效选择，请输入 1 或 2")

def main():
    """主函数"""
    print("🚀 Binlog2SQL GUI 快速设置")
    print("=" * 40)
    
    # 检查是否在Git仓库中
    if not os.path.exists(".git"):
        print("❌ 当前目录不是Git仓库")
        sys.exit(1)
    
    # 检查是否安装了uv
    result = run_command('uv --version', check=False)
    if result.returncode != 0:
        print("❌ 未找到uv包管理器")
        print("请先安装uv: https://docs.astral.sh/uv/getting-started/installation/")
        sys.exit(1)
    
    current_branch = get_current_branch()
    print(f"📍 当前分支: {current_branch or '未知'}")
    
    # 尝试自动检测MySQL版本
    mysql_info = detect_mysql_version_from_config()
    
    if mysql_info:
        major_version, full_version = mysql_info
        print(f"🔍 检测到MySQL版本: {full_version}")
        
        if major_version >= 8:
            print("➡️ 推荐使用MySQL 8.0分支")
            response = input("是否自动配置MySQL 8.0环境? (Y/n): ")
            if response.lower() != 'n':
                setup_mysql80()
            else:
                interactive_setup()
        else:
            print("➡️ 推荐使用MySQL 5.7分支")
            response = input("是否自动配置MySQL 5.7环境? (Y/n): ")
            if response.lower() != 'n':
                setup_mysql57()
            else:
                interactive_setup()
    else:
        print("⚠️ 无法自动检测MySQL版本")
        print("可能的原因:")
        print("- 未配置数据库连接")
        print("- 数据库连接失败")
        print("- config.json文件不存在")
        
        interactive_setup()
    
    print("\n" + "=" * 40)
    print("🎉 设置完成!")
    print("\n📋 后续步骤:")
    print("1. 启动应用: uv run python main.py")
    print("2. 配置数据库连接")
    print("3. 开始解析binlog")
    
    print("\n💡 提示:")
    print("- 运行 'python detect_mysql_version.py' 可以检测MySQL版本")
    print("- 查看 MYSQL_VERSION_COMPATIBILITY.md 了解更多信息")

if __name__ == "__main__":
    main()
