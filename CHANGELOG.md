# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-06-04

### Added

- Add an Evidence-Belief Lattice retrieval path for long-memory grounding.
- Add a persistent `memory_evidence` ledger with FTS5 indexing and migration `0017`.
- Add configurable EBL retrieval limits, rescue multiplier, channel weights, and temporal-neighbor window.
- Add regression coverage for evidence mirroring, linked evidence expansion, temporal-neighbor recall, and Reader EBL routing.

### Changed

- Prefer grounded Evidence Ledger context in `Reader` and `BeliefReader` when supported by the belief store, while preserving the previous belief-only fallback.
- Link structured beliefs to nearby raw chat evidence so synthesized memories can be traced back to concrete conversation turns.

## [1.2.0] - 2026-06-01

### Fixed

- **P0 级 7 项（第一轮）**：
  - propagation 传播过程中 `base_confidence` 被错误覆盖
  - wake 中文 tokenization 改为 `jieba.lcut` 分词
  - `PersistentBeliefStore.add()` FTS5 rowid 并发竞争（改用 `RETURNING rowid`）
  - `messages` 表 Alembic 迁移 schema 与运行时 DDL 冲突
  - MCP Server `handle_request` 绕过 `ToolRegistry` 安全校验/审批/审计全流程
  - crypto tool `verify` 操作假实现（现在使用 `hmac.compare_digest` 做真实签名比较）
  - `require_approval` 参数在 `register()` 中被忽略

- **P1 级 8 项（第二轮）**：
  - `get_similar_task_count()` 信念计数增加时间窗口过滤
  - `persona_memory.py` `deactivate_anchor`/`delete_anchor` 改用 `cursor.rowcount` 替代 `total_changes`
  - 4 个社交媒体工具（douyin/xiaohongshu/weibo/wechat_mp）`execute()` 签名兼容 `ITool` 接口
  - git tool 全部 6 处 `subprocess.run` 替换为 `asyncio.create_subprocess_exec`
  - `user_preferences` 复合主键增加 `user_id`
  - sandbox 代码执行从 `-c`/`-e` 参数传递改为 stdin 传递防止注入
  - `WakeFrequencyTracker` 计数从单值改为时间戳列表记录
  - `evolution/__init__.py` 导入不存在的 `EvolutionTrigger` 阻塞测试执行

- **P0 级 7 项（第三轮）**：
  - Agent 后台任务使用 `_spawn_background_task()` + `shutdown()` 管理，销毁时无任务泄漏
  - `BeliefStore` + `PersistentBeliefStore` 添加 `max_beliefs=10000` 上限及 LRU/SQL 淘汰
  - `drift_history` 从全量 JSON 序列化改为独立表，INSERT INTO 替代，性能不再随记录数劣化
  - 15+ 文件硬编码数据库路径统一从 `config.database.db_path` 读取
  - router.py 魔术字符串 `_MODE_CHAT` 等替换为 `class AgentMode(StrEnum)`
  - 3 个虚假空接口（`IMemoryStore`/`IPersonaGuard`/`ISkillEngine`）充实为有意义的抽象契约
  - migrations 0012/0014/0016 中 7 张预留表添加 "reserved for future functionality" 注释

### Changed

- **数据库路径统一配置**：新增 `DatabaseConfig` 到 `config.py`，`config/default.yaml` 添加 `database.db_path` 配置项，支持多实例部署
- **后台任务管理**：Agent 添加 `_spawn_background_task()` 辅助方法和 `shutdown()` 清理方法，所有 `create_task` 统一分发
- **信念存储内存上限**：`max_beliefs=10000` 默认上限，内存/持久化两层淘汰策略
- **drift_history 性能优化**：新增 `drift_history` 表（自增 PK + 外键 + 复合索引），`record_drift` INSERT INTO，`get_drift_history` 从表 SELECT
- **NoOp 实现更新**：`NoOpMemoryStore`/`NoOpPersonaGuard`/`NoOpSkillEngine` 实现新接口方法

## [1.1.0] - 2026-05-31

### Added

- 定时任务系统（src/cron/）：CronScheduler 调度器，SQLite 持久化，cron 表达式解析，重试逻辑
- 预测式建模（src/prediction/）：Predictor 规则+LLM 预测引擎，FeedbackCollector 反馈分析
- 9 个安全模块：auth（API Key 认证）、confirm（二次确认）、encryption（Fernet 加密）、network_isolation（网络白名单）、output_filter（输出过滤）、privacy（隐私脱敏）、rate_limit（令牌桶限流）、rollback（操作回滚）、session_isolation（会话隔离）
- 网关模块：BaseAdapter 适配器基类、Gateway 网关主类、OpenAI 兼容代理、企业微信适配器
- 核心模块：ConversationManager（对话管理）、CoreRouter（消息路由）、LongTermMemory（FTS5 长期记忆）、MemoryStore（统一记忆入口）
- MCP 支持：MCPClient/MCPServer 协议实现
- PyTorch 统一兼容模块（src/persona/_torch_compat.py），提取公共降级逻辑
- `tests/test_cron/` 测试套件

### Changed

- **社交媒体工具合规改造**：xiaohongshu/douyin/weibo/wechat_mp 工具添加 `_USE_OFFICIAL_API` 开关，默认禁用非公开 API 爬取，需配置官方 API Key
- **README/ROADMAP/SECURITY 修正**：消除虚假声明，所有描述与代码实现一致
- **依赖配置**：dashscope/jieba/snownlp/numpy 移至可选依赖，删除未使用的 emoji 依赖
- **CI 配置**：添加环境变量占位，排除 benchmark 测试
- **Alembic 配置**：配置 sqlalchemy.url，添加 get_url() 函数
- **delegation.py 持久化**：从内存存储改为 aiosqlite 持久化
- **audit.py 自动刷盘**：添加后台定时刷盘任务
- **adjustment_history.py**：从同步 sqlite3 改为 aiosqlite 异步
- **core/belief_store.py**：实现 search_similar/propagate_confidence/overthrow 方法，添加使用指引
- **architecture**: 提取 HMAC 游标编解码到 src/security/cursor.py

### Fixed

- 31 个空文件填充为生产级实现
- 7 个文档问题的更新修复（docs/ 状态声明）
- 56 处旧名「agentx」引用全部替换为「shuyuancore」
- 40 处宽泛 except Exception 替换为具体异常类型或添加 logger.exception
- 空文件 deploy/nginx/agentx.conf 已删除

## [1.0.0] - 2026-05-29

### Added

- Initial open-source release of ShuyuanCore
- Apache 2.0 license, contributing guide, code of conduct, and security policy
- GitHub Actions CI (pytest, ruff, mypy)
- `shuyuancore` CLI entry point via `pip install -e .`

### Changed

- Repository URLs point to `https://github.com/Shuyuanverse/Shuyuancore`
- Copyright holder: 山野 (Shuyuanverse)
- README: clarify implemented vs planned platform integrations
- Removed runtime artifacts from version control; improved `.gitignore`

### Fixed

- Lint issues in persona modules for CI ruff checks
