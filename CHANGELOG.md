# Changelog

All notable changes to this project will be documented in this file.

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
