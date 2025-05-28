#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MySQL版本分支设置脚本
自动化创建和配置MySQL 5.7和8.0的分支
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def run_command(cmd, check=True):
    """执行命令并返回结果"""
    print(f"执行命令: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        if result.stdout:
            print(f"输出: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        print(f"错误输出: {e.stderr}")
        if check:
            sys.exit(1)
        return e

def check_git_status():
    """检查Git状态"""
    result = run_command("git status --porcelain", check=False)
    if result.returncode == 0 and result.stdout.strip():
        print("⚠️ 工作目录有未提交的更改:")
        print(result.stdout)
        response = input("是否继续? (y/N): ")
        if response.lower() != 'y':
            print("操作已取消")
            sys.exit(0)

def create_mysql57_branch():
    """创建并配置MySQL 5.7分支"""
    print("\n🔧 配置MySQL 5.7分支 (main)")
    
    # 确保在main分支
    run_command("git checkout main")
    
    # 更新pyproject.toml为MySQL 5.7兼容版本
    pyproject_content = """[project]
name = "binlog2sql-gui"
version = "0.1.0"
description = "MySQL Binlog to SQL GUI Tool - MySQL 5.7 Compatible Version"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "loguru>=0.7.3",
    "mysql-replication==0.45.1",  # 最后一个稳定支持MySQL 5.7的版本
    "pymysql>=1.1.1",
    "pyside6>=6.9.0",
]

[dependency-groups]
dev = [
    "nuitka>=2.7.4",
]
"""
    
    with open("pyproject.toml", "w", encoding="utf-8") as f:
        f.write(pyproject_content)
    
    # 更新README
    readme_content = """# Binlog2SQL GUI - MySQL 5.7版本

> ⚠️ **重要提示**: 此版本专为MySQL 5.7设计，不支持MySQL 8.0
> 
> 如需MySQL 8.0支持，请切换到 `mysql-8.0` 分支:
> ```bash
> git checkout mysql-8.0
> ```

## 支持的MySQL版本
- ✅ MySQL 5.5
- ✅ MySQL 5.6  
- ✅ MySQL 5.7
- ❌ MySQL 8.0 (请使用mysql-8.0分支)

## 依赖版本
- mysql-replication: 0.45.1
- pymysql: >=1.1.1
- PySide6: >=6.9.0

## 安装和使用

### 环境要求
- Python 3.11+
- MySQL 5.7 (启用binlog)

### 安装步骤
```bash
# 克隆项目 (MySQL 5.7版本)
git clone -b main <repository-url>
cd binlog2sql_GUI

# 安装依赖
uv sync

# 启动应用
uv run python main.py
```

## 版本选择指南

| 您的MySQL版本 | 推荐分支 | 命令 |
|---------------|----------|------|
| 5.5, 5.6, 5.7 | main | `git checkout main` |
| 8.0+ | mysql-8.0 | `git checkout mysql-8.0` |

---

*更多详细信息请参考 [MYSQL_VERSION_COMPATIBILITY.md](MYSQL_VERSION_COMPATIBILITY.md)*
"""
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    # 提交更改
    run_command("git add .")
    run_command('git commit -m "feat: 配置MySQL 5.7兼容分支"')
    
    print("✅ MySQL 5.7分支配置完成")

def create_mysql80_branch():
    """创建并配置MySQL 8.0分支"""
    print("\n🔧 创建MySQL 8.0分支")
    
    # 创建新分支
    run_command("git checkout -b mysql-8.0")
    
    # 更新pyproject.toml为MySQL 8.0兼容版本
    pyproject_content = """[project]
name = "binlog2sql-gui"
version = "0.1.0"
description = "MySQL Binlog to SQL GUI Tool - MySQL 8.0 Compatible Version"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "loguru>=0.7.3",
    "mysql-replication>=1.0.9",  # 支持MySQL 8.0的版本
    "pymysql>=1.1.1",
    "pyside6>=6.9.0",
]

[dependency-groups]
dev = [
    "nuitka>=2.7.4",
]
"""
    
    with open("pyproject.toml", "w", encoding="utf-8") as f:
        f.write(pyproject_content)
    
    # 更新README
    readme_content = """# Binlog2SQL GUI - MySQL 8.0版本

> ⚠️ **重要提示**: 此版本专为MySQL 8.0设计，不支持MySQL 5.7
> 
> 如需MySQL 5.7支持，请切换到 `main` 分支:
> ```bash
> git checkout main
> ```

## 支持的MySQL版本
- ❌ MySQL 5.5, 5.6, 5.7 (请使用main分支)
- ✅ MySQL 8.0+

## 依赖版本
- mysql-replication: >=1.0.9
- pymysql: >=1.1.1
- PySide6: >=6.9.0

## MySQL 8.0特殊配置

### 必需的MySQL配置
```ini
[mysqld]
server-id = 1
log_bin = /var/log/mysql/mysql-bin.log
binlog_expire_logs_seconds = 864000
max_binlog_size = 100M
binlog-format = ROW
binlog_row_metadata = FULL  # MySQL 8.0必需
binlog_row_image = FULL     # MySQL 8.0必需
```

### 安装步骤
```bash
# 克隆项目 (MySQL 8.0版本)
git clone -b mysql-8.0 <repository-url>
cd binlog2sql_GUI

# 安装依赖
uv sync

# 启动应用
uv run python main.py
```

## 版本选择指南

| 您的MySQL版本 | 推荐分支 | 命令 |
|---------------|----------|------|
| 5.5, 5.6, 5.7 | main | `git checkout main` |
| 8.0+ | mysql-8.0 | `git checkout mysql-8.0` |

## MySQL 8.0新特性支持

- ✅ 改进的binlog元数据
- ✅ 更好的字符集支持
- ✅ 增强的安全性
- ✅ 性能优化

---

*更多详细信息请参考 [MYSQL_VERSION_COMPATIBILITY.md](MYSQL_VERSION_COMPATIBILITY.md)*
"""
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    # 提交更改
    run_command("git add .")
    run_command('git commit -m "feat: 创建MySQL 8.0兼容分支"')
    
    print("✅ MySQL 8.0分支创建完成")

def create_version_detection_script():
    """创建MySQL版本检测脚本"""
    print("\n🔧 创建版本检测脚本")
    
    script_content = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MySQL版本检测脚本
自动检测MySQL版本并推荐合适的分支
"""

import json
import pymysql
import sys

def detect_mysql_version():
    """检测MySQL版本并推荐分支"""
    try:
        # 读取配置文件
        with open('config.json', 'r', encoding='utf-8') as f:
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
        
        print(f"\\n📊 MySQL版本信息:")
        print(f"版本: {version}")
        print(f"类型: {comment}")
        
        # 推荐分支
        print(f"\\n🎯 分支推荐:")
        if major_version >= 8:
            print(f"✅ 推荐使用: mysql-8.0 分支")
            print(f"命令: git checkout mysql-8.0")
            print(f"原因: MySQL {major_version}.{minor_version} 需要 mysql-replication>=1.0.0")
        else:
            print(f"✅ 推荐使用: main 分支")
            print(f"命令: git checkout main")
            print(f"原因: MySQL {major_version}.{minor_version} 需要 mysql-replication<=0.45.1")
        
        # 检查当前分支
        import subprocess
        try:
            result = subprocess.run(['git', 'branch', '--show-current'], 
                                  capture_output=True, text=True, check=True)
            current_branch = result.stdout.strip()
            
            print(f"\\n🌿 当前分支: {current_branch}")
            
            if major_version >= 8 and current_branch != 'mysql-8.0':
                print("⚠️ 警告: 当前分支可能不兼容您的MySQL版本")
            elif major_version < 8 and current_branch != 'main':
                print("⚠️ 警告: 当前分支可能不兼容您的MySQL版本")
            else:
                print("✅ 当前分支与MySQL版本兼容")
                
        except subprocess.CalledProcessError:
            print("无法检测当前Git分支")
        
    except FileNotFoundError:
        print("❌ 未找到config.json文件")
        print("请先运行GUI程序并配置数据库连接")
    except Exception as e:
        print(f"❌ 检测失败: {str(e)}")
        print("请检查数据库连接配置是否正确")

if __name__ == "__main__":
    detect_mysql_version()
'''
    
    with open("detect_mysql_version.py", "w", encoding="utf-8") as f:
        f.write(script_content)
    
    # 使脚本可执行
    os.chmod("detect_mysql_version.py", 0o755)
    
    print("✅ 版本检测脚本创建完成")

def main():
    """主函数"""
    print("🚀 MySQL版本分支设置脚本")
    print("=" * 50)
    
    # 检查是否在Git仓库中
    if not os.path.exists(".git"):
        print("❌ 当前目录不是Git仓库")
        sys.exit(1)
    
    # 检查Git状态
    check_git_status()
    
    # 创建分支和配置
    create_mysql57_branch()
    create_mysql80_branch()
    create_version_detection_script()
    
    # 切换回main分支
    run_command("git checkout main")
    
    print("\n" + "=" * 50)
    print("🎉 分支设置完成!")
    print("\n📋 后续步骤:")
    print("1. 运行版本检测: python detect_mysql_version.py")
    print("2. 根据MySQL版本切换分支:")
    print("   - MySQL 5.7: git checkout main")
    print("   - MySQL 8.0: git checkout mysql-8.0")
    print("3. 安装依赖: uv sync")
    print("4. 启动应用: uv run python main.py")
    
    print("\n📚 更多信息请查看: MYSQL_VERSION_COMPATIBILITY.md")

if __name__ == "__main__":
    main()
