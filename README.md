# Binlog2SQL GUI

基于PySide6开发的MySQL Binlog解析工具，提供图形化界面来解析MySQL binlog文件并生成对应的SQL语句。

## 功能特性

- 🖥️ **图形化界面** - 友好的GUI界面，易于使用
- 🔗 **连接管理** - 支持保存和管理多个数据库连接配置
- 📊 **实时解析** - 实时解析binlog并显示生成的SQL语句
- 🔄 **回滚支持** - 支持生成回滚SQL语句（flashback模式）
- 🎯 **精确过滤** - 支持按时间、数据库、表、SQL类型等条件过滤
- 💾 **结果导出** - 支持将解析结果导出到文件
- ⚙️ **配置保存** - 自动保存窗口设置和解析配置
- 📝 **日志记录** - 使用loguru记录详细日志，按天分割，便于问题排查
- 🛡️ **错误处理** - 完善的UTF-8解码错误处理，使用ignore模式避免解析中断

## 核心功能

### 数据库连接管理
- 新建、编辑、删除数据库连接配置
- 连接测试功能
- 自动保存最后使用的连接

### Binlog解析配置
- **文件范围**: 指定起始和结束binlog文件及位置
- **时间范围**: 按时间段过滤binlog事件
- **数据库过滤**: 只解析指定数据库的事件
- **表过滤**: 只解析指定表的事件
- **SQL类型**: 选择要解析的SQL类型（INSERT/UPDATE/DELETE）

### 解析选项
- **只显示DML**: 只显示数据操作语句，忽略DDL
- **生成回滚SQL**: 生成用于数据回滚的SQL语句
- **不包含主键**: 生成的INSERT语句不包含主键字段
- **回滚间隔**: 设置回滚SQL之间的延迟时间

## 安装要求

- Python 3.11+
- PySide6
- PyMySQL
- mysql-replication
- loguru

## 安装步骤

1. 克隆项目：
```bash
git clone <repository-url>
cd binlog2sql_GUI
```

2. 使用uv安装依赖：
```bash
uv sync
```

或者使用pip安装：
```bash
pip install pyside6 pymysql mysql-replication==0.44.0 loguru
```

## 使用方法

1. 启动应用程序：
```bash
uv run python main.py
```

2. 配置数据库连接：
   - 点击"新建"按钮创建数据库连接
   - 填写数据库连接信息
   - 点击"测试连接"验证连接
   - 保存连接配置

3. 配置解析参数：
   - 选择数据库连接
   - 设置binlog文件范围
   - 配置时间过滤条件
   - 选择要解析的SQL类型
   - 设置其他解析选项

4. 开始解析：
   - 点击"开始解析"按钮
   - 在右侧面板查看解析结果
   - 可以随时点击"停止解析"中断解析

5. 结果处理：
   - 复制全部结果到剪贴板
   - 保存结果到文件
   - 清空当前结果

## MySQL配置要求

为了使用binlog解析功能，需要确保MySQL配置正确：

1. 启用binlog：
```sql
-- 在my.cnf中添加
log-bin = mysql-bin
binlog-format = ROW
```

2. 创建具有REPLICATION权限的用户：
```sql
CREATE USER 'binlog_user'@'%' IDENTIFIED BY 'password';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'binlog_user'@'%';
FLUSH PRIVILEGES;
```

## 项目结构

```
binlog2sql_GUI/
├── main.py                 # 应用程序入口
├── gui/                    # GUI模块
│   ├── __init__.py
│   ├── main_window.py      # 主窗口
│   ├── connection_dialog.py # 连接配置对话框
│   └── config_manager.py   # 配置管理器
├── core/                   # 核心功能模块
│   ├── __init__.py
│   ├── binlog_parser.py    # Binlog解析器
│   ├── binlog_util.py      # 工具函数
│   └── logger.py           # 日志配置模块
├── logs/                   # 日志目录（自动创建）
│   ├── binlog2sql_YYYY-MM-DD.log  # 按天分割的主日志
│   └── error_YYYY-MM-DD.log       # 错误日志
├── test_app.py            # 测试脚本
├── pyproject.toml          # 项目配置
├── README.md              # 说明文档
└── USAGE_EXAMPLE.md       # 使用示例
```

## 基于开源项目

本项目的核心解析功能基于 [danfengcao/binlog2sql](https://github.com/danfengcao/binlog2sql) 项目，在此基础上开发了图形化界面。

## 日志功能

### 日志配置
- **自动创建**: 应用启动时自动创建 `logs` 目录
- **按天分割**: 日志文件按天自动分割，格式为 `binlog2sql_YYYY-MM-DD.log`
- **错误日志**: 单独记录错误日志到 `error_YYYY-MM-DD.log`
- **自动清理**: 保留30天的日志文件，自动压缩旧日志
- **异步写入**: 使用异步写入，不影响应用性能

### 日志级别
- **控制台**: 显示INFO及以上级别的日志
- **文件**: 记录DEBUG及以上级别的详细日志
- **错误文件**: 只记录ERROR级别的日志

### 日志内容
- 应用启动和关闭
- 数据库连接状态
- 解析任务的开始和结束
- 解析参数和配置信息
- 错误信息和异常堆栈
- 用户操作记录

### UTF-8解码错误处理
- 使用 `decode('utf-8', 'ignore')` 处理解码错误
- 自动跳过无法解码的字节，避免解析中断
- 在日志中记录解码错误的详细信息

## 注意事项

1. 确保MySQL服务器启用了binlog功能
2. 使用的数据库用户需要有REPLICATION权限
3. 解析大量binlog数据时可能需要较长时间
4. 建议在测试环境中先验证解析结果的正确性

## 许可证

本项目采用MIT许可证。