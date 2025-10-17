# MySQL版本兼容性管理方案

## 问题描述

当前项目使用 `mysql-replication==0.46.0`，但该版本无法同时支持MySQL 5.7和MySQL 8.0：
- MySQL 5.7: 需要 `mysql-replication<=0.45.1`
- MySQL 8.0: 需要 `mysql-replication>=1.0.0`

## 解决方案：Git分支策略

### 分支结构

```
main (MySQL 5.7 兼容)
├── mysql-5.7 (当前分支，保持兼容MySQL 5.7)
└── mysql-8.0 (新分支，支持MySQL 8.0)
```

### 实施步骤

#### 1. 创建MySQL 8.0分支

```bash
# 创建并切换到MySQL 8.0分支
git checkout -b mysql-8.0

# 更新依赖到支持MySQL 8.0的版本
uv remove mysql-replication
uv add "mysql-replication>=1.0.9"

# 提交更改
git add .
git commit -m "feat: 升级mysql-replication到1.0.9以支持MySQL 8.0"
```

#### 2. 保持主分支支持MySQL 5.7

```bash
# 切换回主分支
git checkout main

# 确保使用兼容MySQL 5.7的版本
uv remove mysql-replication
uv add "mysql-replication==0.45.1"

# 提交更改
git add .
git commit -m "fix: 固定mysql-replication版本为0.45.1以确保MySQL 5.7兼容性"
```

#### 3. 创建版本标识

在每个分支的README中添加版本标识：

**主分支 (MySQL 5.7)**:
```markdown
# Binlog2SQL GUI - MySQL 5.7版本

> ⚠️ 此版本专为MySQL 5.7设计，不支持MySQL 8.0
> 如需MySQL 8.0支持，请切换到 `mysql-8.0` 分支
```

**MySQL 8.0分支**:
```markdown
# Binlog2SQL GUI - MySQL 8.0版本

> ⚠️ 此版本专为MySQL 8.0设计，不支持MySQL 5.7
> 如需MySQL 5.7支持，请切换到 `main` 分支
```

### 依赖版本对照表

| MySQL版本 | 分支名称 | mysql-replication版本 | 状态 |
|-----------|----------|----------------------|------|
| 5.7       | main     | 0.45.1               | 稳定 |
| 8.0       | mysql-8.0| 1.0.9                | 开发中 |

### 开发工作流

#### 功能开发
1. **通用功能**: 在主分支开发，然后合并到mysql-8.0分支
2. **版本特定功能**: 在对应分支开发

#### 合并策略
```bash
# 将主分支的通用功能合并到MySQL 8.0分支
git checkout mysql-8.0
git merge main --no-ff -m "merge: 同步主分支的通用功能"

# 解决可能的依赖冲突
# 手动处理pyproject.toml中的mysql-replication版本差异
```

### 发布策略

#### 版本命名
- **MySQL 5.7版本**: `v1.0.0-mysql57`
- **MySQL 8.0版本**: `v1.0.0-mysql80`

#### 发布流程
```bash
# MySQL 5.7版本发布
git checkout main
git tag v1.0.0-mysql57
git push origin v1.0.0-mysql57

# MySQL 8.0版本发布
git checkout mysql-8.0
git tag v1.0.0-mysql80
git push origin v1.0.0-mysql80
```

### 用户使用指南

#### 下载对应版本
```bash
# MySQL 5.7用户
git clone -b main <repository-url>
# 或
git clone -b v1.0.0-mysql57 <repository-url>

# MySQL 8.0用户
git clone -b mysql-8.0 <repository-url>
# 或
git clone -b v1.0.0-mysql80 <repository-url>
```

#### 环境检测脚本
可以创建一个自动检测MySQL版本的脚本：

```python
import pymysql

def detect_mysql_version(connection_settings):
    """检测MySQL版本并推荐对应分支"""
    try:
        conn = pymysql.connect(**connection_settings)
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            
        major_version = int(version.split('.')[0])
        
        if major_version >= 8:
            print(f"检测到MySQL {version}")
            print("推荐使用: mysql-8.0 分支")
            print("命令: git checkout mysql-8.0")
        else:
            print(f"检测到MySQL {version}")
            print("推荐使用: main 分支")
            print("命令: git checkout main")
            
        conn.close()
        return major_version
        
    except Exception as e:
        print(f"检测MySQL版本失败: {e}")
        return None
```

### 维护策略

1. **主要开发**: 在主分支进行，确保MySQL 5.7兼容性
2. **定期同步**: 每周将主分支的通用改进合并到mysql-8.0分支
3. **测试覆盖**: 两个分支都需要完整的测试覆盖
4. **文档维护**: 保持两个分支的文档同步更新

### 优势

1. **清晰分离**: 每个分支专注于特定MySQL版本
2. **独立发布**: 可以独立发布和维护不同版本
3. **用户友好**: 用户可以根据需要选择合适的分支
4. **维护简单**: 避免了复杂的条件判断和兼容性代码

### 注意事项

1. **依赖冲突**: 合并时注意处理pyproject.toml的差异
2. **测试环境**: 需要准备MySQL 5.7和8.0的测试环境
3. **文档同步**: 确保两个分支的文档保持一致
4. **用户沟通**: 在README中明确说明版本选择指南
