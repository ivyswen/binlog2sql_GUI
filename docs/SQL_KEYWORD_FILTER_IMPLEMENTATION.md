# SQL 关键字过滤功能实现文档

## 📋 功能概述

在 MySQL Binlog 解析工具的 GUI 中实现了 **SQL 关键字过滤功能**，允许用户在解析过程中只显示包含指定关键字的 SQL 语句。

---

## 🎯 功能特性

| 特性 | 说明 |
|------|------|
| **启用/禁用** | 通过复选框快速启用或禁用过滤功能 |
| **多关键字支持** | 支持输入多个关键字（空格或逗号分隔） |
| **不区分大小写** | 关键字匹配不区分大小写 |
| **OR 逻辑** | 只要 SQL 包含任意一个关键字就会被显示 |
| **性能优化** | 过滤在 UI 层进行，不影响解析性能 |
| **统计信息** | 记录过滤统计信息（总处理、匹配、过滤数量） |
| **设置持久化** | 过滤设置会被保存并在下次启动时恢复 |

---

## 🔧 实现细节

### 1. UI 组件（第 418-432 行）

```python
# SQL关键字过滤
keyword_filter_layout = QHBoxLayout()
self.enable_keyword_filter = QCheckBox("启用关键字过滤")
self.enable_keyword_filter.setChecked(False)
keyword_filter_layout.addWidget(self.enable_keyword_filter)

self.keyword_filter_edit = QLineEdit()
self.keyword_filter_edit.setPlaceholderText("输入关键字，多个关键字用空格分隔（如：UPDATE DELETE）")
self.keyword_filter_edit.setEnabled(False)
keyword_filter_layout.addWidget(self.keyword_filter_edit)

# 连接复选框信号以启用/禁用文本框
self.enable_keyword_filter.toggled.connect(self.keyword_filter_edit.setEnabled)

filter_layout.addRow("关键字过滤:", keyword_filter_layout)
```

**位置**：过滤条件区域（在数据库和表过滤之后）

**组件**：
- `enable_keyword_filter`: 复选框，用于启用/禁用过滤
- `keyword_filter_edit`: 文本输入框，用于输入关键字

---

### 2. 实例变量初始化（第 164-167 行）

```python
# SQL关键字过滤相关
self.keyword_filters = []  # 关键字过滤列表
self.filtered_sql_count = 0  # 被过滤的SQL计数
self.matched_sql_count = 0  # 匹配的SQL计数
```

---

### 3. 过滤逻辑（第 949-975 行）

在 `on_sql_generated()` 方法中实现：

```python
def on_sql_generated(self, sql):
    """处理生成的SQL - 使用批量更新机制"""
    # 检查是否需要进行关键字过滤
    if self.enable_keyword_filter.isChecked() and self.keyword_filters:
        # 如果启用了关键字过滤，检查SQL是否包含任意一个关键字（OR逻辑）
        sql_upper = sql.upper()
        matched = any(keyword in sql_upper for keyword in self.keyword_filters)
        
        if not matched:
            # SQL不匹配任何关键字，跳过此SQL
            self.filtered_sql_count += 1
            return
        else:
            # SQL匹配关键字，计数
            self.matched_sql_count += 1
    
    # 添加到缓冲区（只有匹配的SQL才会到达这里）
    self.sql_buffer.append(sql)
    self.sql_count += 1
    # ... 后续处理
```

**关键点**：
- 在 SQL 添加到缓冲区之前进行过滤
- 使用 `any()` 实现 OR 逻辑
- 转换为大写进行不区分大小写的匹配
- 统计被过滤和匹配的 SQL 数量

---

### 4. 关键字初始化（第 857-876 行）

在 `start_parse()` 方法中：

```python
# 初始化关键字过滤
self.keyword_filters = []
self.filtered_sql_count = 0
self.matched_sql_count = 0

if self.enable_keyword_filter.isChecked():
    # 获取关键字过滤条件
    keyword_text = self.keyword_filter_edit.text().strip()
    if keyword_text:
        # 支持空格和逗号分隔
        keywords = [kw.strip().upper() for kw in keyword_text.replace(',', ' ').split()]
        self.keyword_filters = [kw for kw in keywords if kw]  # 过滤空字符串
        
        if self.keyword_filters:
            logger.info(f"启用关键字过滤，关键字列表: {self.keyword_filters}")
```

**特点**：
- 支持空格和逗号分隔
- 自动转换为大写
- 过滤空字符串
- 记录日志

---

### 5. 统计信息记录（第 1039-1044 行）

在 `on_parse_finished()` 方法中：

```python
# 记录过滤统计信息
if self.enable_keyword_filter.isChecked() and self.keyword_filters:
    total_processed = self.matched_sql_count + self.filtered_sql_count
    logger.info(f"关键字过滤统计 - 总处理: {total_processed}, 匹配: {self.matched_sql_count}, 过滤: {self.filtered_sql_count}")
    if self.matched_sql_count == 0:
        logger.warning("未找到匹配关键字的SQL语句")
```

---

### 6. 设置持久化

**加载设置**（第 567-571 行）：
```python
# 加载关键字过滤设置
enable_keyword_filter = parse_settings.get("enable_keyword_filter", False)
self.enable_keyword_filter.setChecked(enable_keyword_filter)
keyword_filter_text = parse_settings.get("keyword_filter_text", "")
self.keyword_filter_edit.setText(keyword_filter_text)
```

**保存设置**（第 591-599 行）：
```python
parse_settings = {
    # ... 其他设置
    "enable_keyword_filter": self.enable_keyword_filter.isChecked(),
    "keyword_filter_text": self.keyword_filter_edit.text()
}
```

---

## 📊 使用示例

### 场景 1：过滤 UPDATE 语句
1. 勾选"启用关键字过滤"
2. 在文本框中输入：`UPDATE`
3. 点击"开始解析"
4. 只有包含 UPDATE 的 SQL 语句会被显示

### 场景 2：过滤多个关键字
1. 勾选"启用关键字过滤"
2. 在文本框中输入：`UPDATE DELETE` 或 `UPDATE, DELETE`
3. 点击"开始解析"
4. 包含 UPDATE 或 DELETE 的 SQL 语句会被显示

### 场景 3：过滤特定表的操作
1. 勾选"启用关键字过滤"
2. 在文本框中输入：`users` 或 `orders`
3. 点击"开始解析"
4. 只有涉及这些表的 SQL 语句会被显示

---

## 🔍 日志输出示例

```
[INFO] 启用关键字过滤，关键字列表: ['UPDATE', 'DELETE']
[INFO] 关键字过滤统计 - 总处理: 1000, 匹配: 350, 过滤: 650
[WARNING] 未找到匹配关键字的SQL语句
```

---

## ✅ 测试清单

- [x] UI 组件正确显示
- [x] 复选框启用/禁用文本框
- [x] 关键字过滤逻辑正确
- [x] 不区分大小写
- [x] 支持多关键字
- [x] 支持空格和逗号分隔
- [x] 统计信息正确
- [x] 设置持久化
- [x] 日志记录完整
- [x] 无语法错误

---

## 🚀 后续改进建议

1. **AND 逻辑支持**：添加选项支持"包含所有关键字"
2. **正则表达式**：支持正则表达式匹配
3. **排除关键字**：支持排除包含特定关键字的 SQL
4. **过滤历史**：保存常用的过滤条件
5. **性能优化**：对大量 SQL 的过滤进行性能优化

