# Binlog2SQL GUI 项目开发与多分支规范

## 1. 多分支依赖隔离与兼容原则
本项目通过分支隔离支持不同 MySQL 版本：
- `master` 分支：适配 MySQL 5.5/5.6/5.7，依赖 `mysql-replication==0.46.0`。
- `mysql-8.0` 分支：适配 MySQL 8.0+，依赖 `mysql-replication>=1.0.9`。

### 规则要求：
1. **禁止硬编码版本专有参数**：跨版本或在 `core/` 模块创建通用解析/分析逻辑时，必须使用 `inspect.signature` 对第三方库（尤其是 `BinLogStreamReader.__init__`）入参做动态探测与自适应传递，避免因驱动升级导致关键字参数报错（如 `fail_on_table_metadata_unavailable`）。
2. **跨分支功能同步规范**：新功能开发完成后，若需同步至另一分支（如从 `master` 到 `mysql-8.0` 或反向），务必：
   - 检查目标分支的 `pyproject.toml` 依赖差异；
   - 切换分支后执行 `uv sync` 同步虚拟环境；
   - 运行单元测试（`tests/`）验证动态兼容性后再完成提交。

## 2. 编码与环境规范
- 操作系统为 Windows，编辑与合并代码时注意换行符统一（避免因 CRLF/LF 不一致产生伪冲突）。
