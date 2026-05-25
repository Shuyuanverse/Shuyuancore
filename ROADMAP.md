# ShuyuanCore 开发路线图

**版本**: v1.0
**生效日期**: 2026-05-25
**来源**: [DEVELOPMENT_RULES.md](./DEVELOPMENT_RULES.md) v1.0 第 4.2 节 + `docs/` 四份核心规范

> 状态标记：`[ ] 待开始` `[🔄] 进行中` `[✅] 已完成` `[⚠️] 需返工`

---

## Phase 1: 基础设施（Infrastructure）

*开发顺序依据规则 4.2.1*

### 配置管理（`src/config.py`）

- [✅] 定义 13 个嵌套 Pydantic 模型（对齐技术架构第六章全部配置节点）
- [✅] 实现 YAML 加载和 `${ENV_VAR}` 环境变量替换（`_load_yaml`）
- [✅] 实现 12 个 `@field_validator` 锁定参数校验器（对齐规则 2.3 节锁定表）
- [✅] 实现单例 `get_settings()` 和 `reload_settings()`
- [✅] 编写 `config/default.yaml` 完整默认配置（162 行）
- [✅] 初始化 `pyproject.toml`（pydantic-settings, pyyaml, pytest, ruff 等）
- [✅] 编写单元测试 `tests/test_config.py`（31 个用例全部通过）
- [✅] 提交架构自评报告 `reports/arch_review_config.md`

### 异常体系（`src/exceptions.py`）

- [✅] 定义基类 `ShuyuanCoreError`（code, http_status, message, detail, to_dict()）
- [✅] 定义 11 个分类异常 + 24 个具体异常（对齐 API 错误码 1.2 节，共 24 个错误码）
- [✅] 异常消息中英双语（`"中文 / English"` 格式）
- [✅] 实现 `to_dict()` API 友好序列化
- [✅] 编写单元测试 `tests/test_exceptions.py`（135 个用例全部通过）
- [✅] 提交架构自评报告 `reports/arch_review_exceptions.md`

### 日志系统（`src/logging.py`）

- [ ] 实现基础日志配置（控制台输出 + 文件输出，从 `Settings.deploy` 读取 log_level）
- [ ] 实现请求/关联 ID 自动注入（correlation ID / request ID，trace context 穿透）
- [ ] 实现日志轮转（`RotatingFileHandler`，单文件 50MB，保留 5 个 — 对齐 `LogRotationConfig`）
- [ ] 实现结构化日志输出（`structlog` JSON 格式，生产环境用，开发环境用彩色控制台）
- [ ] 实现敏感信息过滤（API Key / Token 自动打码，依据规则 5.5 安全准则）
- [ ] 集成 `src/config.py`：从 `DeployConfig.log_level` / `LogRotationConfig` 读取参数
- [ ] 编写单元测试 `tests/test_logging.py`
- [ ] 提交架构自评报告

---

## Phase 2: 模型层（Models）

*开发顺序依据规则 4.2.2*

### 模型提供者接口（`src/models/interfaces.py`）

- [ ] 定义 `IModelProvider` 抽象基类（`chat()`, `embed()`, `embed_batch()` — 依据技术架构 2.2 节）
- [ ] 定义 `ProviderRegistry` 注册表类（注册/发现/状态检查）

### DashScope 提供者（`src/models/dashscope.py`）

- [ ] 实现 `DashScopeProvider(IModelProvider)`（依据 `ModelsConfig.providers.dashscope`）
- [ ] 实现 OpenAI 兼容 API 调用（base_url + API Key — 依据技术架构 2.2 节）
- [ ] 实现 text-embedding-v2 嵌入服务（1536 维 — 依据技术架构 2.2 节 & 规则 2.3 节）
- [ ] 添加超时和重试机制（默认 30s 超时，3 次重试 — 依据规则 5.5）

### DeepSeek 提供者（`src/models/deepseek.py`）

- [ ] 实现 `DeepSeekProvider(IModelProvider)`
- [ ] 实现 OpenAI 兼容 API 调用
- [ ] 添加超时和重试机制

### OpenAI 兼容提供者（`src/models/openai_compat.py`）

- [ ] 实现通用 `OpenAICompatProvider`，支持任意 OpenAI-compatible endpoint
- [ ] Ollama 子类 `OllamaProvider`（base_url http://localhost:11434）

### 模型路由与主备切换（`src/models/router.py`）

- [ ] 实现任务类型 → 模型路由表（code/chat/math/embedding/tool/review — 对齐 `ModelRoutingConfig`）
- [ ] 实现主备切换逻辑（timeout/5xx/429 → 自动切换备选模型）
- [ ] 实现模型连接健康检查
- [ ] 编写单元测试 `tests/test_models/`
- [ ] 提交架构自评报告

---

## Phase 3: 核心 Agent（Core）

*开发顺序依据规则 4.2.3*

### Agent 主循环（`src/core/agent.py`）

- [ ] 实现 `Agent` 主类骨架（依据技术架构 2.1 节 Agent 主循环 7 步流程）
- [ ] 实现 `chat(message, user_id, platform)` — 主对话入口
- [ ] 实现 `_prepare_context(message, user_id)` — 上下文准备（注入核心记忆 + 检索历史 + 匹配技能）

### 上下文管理（`src/core/context.py`）

- [ ] 实现上下文窗口管理（依据技术架构 2.1 节步骤 [2]）
- [ ] 实现动态压缩（达到容量阈值时压缩低优先级记忆 — 依据技术架构 L1 核心记忆节）
- [ ] 实现上下文 token 计数预估

### 对话管理（`src/core/conversation.py`）

- [ ] 实现 `ConversationManager`（SQLite CRUD：创建/获取/归档/删除会话）
- [ ] 实现消息管理（保存/检索消息，分页支持 — 对齐 API 3.1 节）
- [ ] 实现会话级联删除（删除对话时级联删除 messages + ChromaDB 向量 — 依据规则 2.2 节）
- [ ] 实现游标分页（cursor-based pagination — 对齐 API 响应格式）

### 三 LLM 分工编排（`src/core/orchestrator.py`）

- [ ] 实现主 LLM 执行路径（实时交互 — 依据技术架构 2.1 节三 LLM 分工表）
- [ ] 实现复盘 LLM 异步路径（后台总结/提炼/更新）
- [ ] 实现工具 LLM 调用路径（参数构造 + 结果解析）
- [ ] 编写单元测试 `tests/test_core/`
- [ ] 提交架构自评报告

---

## Phase 4: 记忆系统（Memory）— L1 + L3 优先

*开发顺序依据规则 4.2.4*

### 记忆存取接口（`src/memory/interfaces.py`）

- [ ] 定义 `IMemoryStore` 抽象基类（read/write/delete/search — 依据规则 2.2 节）
- [ ] 定义 `IEmbeddingService` 抽象基类

### L1 核心记忆（`src/memory/core_memory.py`）

- [ ] 实现 `CoreMemory` 类（MEMORY.md ~2200 字符 + USER.md ~1375 字符 — 依据技术架构 L1 节）
- [ ] 实现会话开始时冻结快照注入（下次会话生效）
- [ ] 实现动态压缩（80% 容量阈值时自动合并压缩 — 依据技术架构）
- [ ] 实现防注入安全扫描（正则黑名单 + 关键字符过滤）

### L3 长期历史 — SQLite（`src/memory/store.py`）

- [ ] 实现 SQLite 数据库初始化（PRAGMA journal_mode=WAL, foreign_keys=ON, busy_timeout=5000 — 依据规则 2.4 节）
- [ ] 实现 `conversations` 和 `messages` 表创建（对齐数据库 Schema 2.1/2.2 节）
- [ ] 实现 `messages_fts` FTS5 全文索引（对齐 L3 架构）
- [ ] 实现消息 CRUD 操作
- [ ] 实现 FTS5 关键词检索（`fts5_search_limit=10` — 对齐配置）

### L3 长期历史 — ChromaDB（`src/memory/chroma_store.py`）

- [ ] 实现 ChromaDB PersistentClient 初始化（`data/chroma/`）
- [ ] 实现 `long_term_memory` 和 `conversations` 两个集合创建
- [ ] 实现向量写入（写入前去重检查 >0.95 — 依据规则 2.3 节 & API 文档）

### Embedding 服务（`src/memory/embedding.py`）

- [ ] 实现 `EmbeddingService`（依据技术架构 L3 Embedding 服务设计）
- [ ] 实现 DashScope text-embedding-v2 调用（方案一，1536 维）
- [ ] 实现 sentence-transformers 本地模型降级（方案二，384 维）
- [ ] 实现批量嵌入 + 进度日志（batch_size=20 — 依据规则 2.5 节 & 配置）

### 统一检索接口（`src/memory/search.py`）

- [ ] 实现 FTS5 + ChromaDB 双引擎检索合并去重排序
- [ ] 实现 L3 长期历史 + conversations 双集合统一搜索（依据技术架构 ECS 教训）
- [ ] 编写单元测试 `tests/test_memory/`
- [ ] 提交架构自评报告

---

## Phase 5: 人格编译与风格保护（Persona）

*开发顺序依据规则 4.2.5*

### 人格接口（`src/persona/interfaces.py`）

- [ ] 定义 `IPersonaCompiler` 抽象基类
- [ ] 定义 `IStyleGuard` 抽象基类

### 人格编译引擎（`src/persona/compiler.py`）

- [ ] 实现输入校验（100 字 ~ 100 万字 — 依据规则 2.3 节 & 产品方案）
- [ ] 实现身份文件管理（CORE.md / SOUL.md — 依据技术架构 2.5 节）
- [ ] 实现人格编码（256 维 × 7 维度风格编码 — 依据规则 2.3 节）
- [ ] 实现多身份支持（最多 5 个，shared/independent 层划分 — 依据技术架构）
- [ ] 实现语言样本管理（500-1000 条，按场景分类 — 依据规则 2.3 节）

### 风格保护（`src/persona/style_guard.py`）

- [ ] 实现风格向量对比（当前输出 vs 锚点 — 依据技术架构 L6 人格记忆）
- [ ] 实现松刹车保护层（drift_threshold=0.25，超过强制校准 — 依据规则 2.3 节锁定表）
- [ ] 审查 Agent 集成点预留（review_drift_threshold=0.15 — 依据技术架构补充）

### 人格记忆存储（`src/persona/persona_memory.py`）

- [ ] 实现 `data/memories/persona.json` 读写（style_anchors + trajectory + drift_history）
- [ ] 实现漂移检测历史记录
- [ ] 编写单元测试 `tests/test_persona/`
- [ ] 提交架构自评报告

---

## Phase 6: 技能系统（Skills）— 先手动

*开发顺序依据规则 4.2.6*

### 技能存取接口（`src/skills/interfaces.py`）

- [ ] 定义 `ISkillStore` 抽象基类
- [ ] 定义 `ISkillGraph` 抽象基类（因果图）

### 手动技能管理（`src/skills/manager.py`）

- [ ] 实现技能 CRUD（创建/读取/更新/删除技能文档 Markdown+YAML）
- [ ] 实现技能版本记录
- [ ] 实现渐进式披露（Level 0/1/2 — 依据技术架构 2.3 节）

### 因果技能图（`src/skills/graph.py`）

- [ ] 实现图结构存储（`data/graph/skill_graph.json` — 依据技术架构 L4 节）
- [ ] 实现技能节点管理（9 个字段：前置条件/因果链/边界/失败模式/依赖/版本/验证/来源/关联）
- [ ] 实现因果图遍历推理（前置条件判断 → 因果链推理 → 跨领域迁移）

### 技能市场兼容（`src/skills/market.py`）

- [ ] 实现 agentskills.io 开放标准兼容（安装/卸载/安全扫描— 依据技术架构 2.3 节）
- [ ] 实现技能质量评分（使用人数/成功率/更新时间）

### Curator 回收（`src/skills/curator.py`）

- [ ] 实现定时回收（7 天触发 — 依据技术架构 Curator 节）
- [ ] 实现 Phase 1 确定性操作（30 天过时 / 90 天归档，无 LLM）
- [ ] 实现 Phase 2 LLM 审查（最多 3 次迭代，保留/修补/合并/归档）
- [ ] 实现 Pin 保护 + tar.gz 快照

### 自动技能提炼（`src/skills/engine.py`）

- [ ] 实现任务难度驱动判断（是否值得提炼 — 依据技术架构 2.3 节提炼流程）
- [ ] 实现技能文档自动生成（Markdown+YAML）
- [ ] 实现因果抽取（额外一次 LLM 调用，Level 0/1/2 分层）
- [ ] 实现质量门控（可验证性/因果链自洽/与已有技能不冲突）
- [ ] 编写单元测试 `tests/test_skills/`
- [ ] 提交架构自评报告

---

## Phase 7: 工具系统（Tools）

*开发顺序依据规则 4.2.7*

### 工具接口（`src/tools/interfaces.py`）

- [ ] 定义 `ITool` 抽象基类（execute/validate/describe）
- [ ] 定义 `ToolRegistry` 注册表（注册/发现/状态/依赖检查）

### 核心工具实现

- [ ] 实现 `TerminalTool`（shell 命令执行，危险命令审批 — 依据安全规则）
- [ ] 实现 `FileOpsTool`（文件读写/搜索/列出目录）
- [ ] 实现 `WebTool`（HTTP 请求/网页抓取/搜索）
- [ ] 实现 `MemoryTool`（查询/写入/删除记忆 — 调用 src/memory/ 接口）
- [ ] 实现 `SkillsTool`（加载/执行技能 — 调用 src/skills/ 接口）

### 扩展工具实现（14 个，按需分批）

- [ ] 数据库操作工具（SQL 查询/迁移/备份）
- [ ] Git 操作工具
- [ ] API 调试工具
- [ ] 文档生成工具
- [ ] 社交媒体工具（小红书/抖音/微博/微信公众号）
- [ ] Email 工具
- [ ] 日历工具
- [ ] 电子表格工具
- [ ] 翻译工具
- [ ] 项目管理工具
- [ ] 知识库工具
- [ ] 文件转换工具
- [ ] 监控工具
- [ ] 图表生成工具

### 工具执行基础设施

- [ ] 实现工具执行沙箱隔离（依据安全配置 sandbox=docker）
- [ ] 实现工具审批流程（危险命令 → 15 分钟超时审批 — 依据安全规则）
- [ ] 实现工具执行审计日志（`audit_log` 表写入 — 依据规则 5.4 节）
- [ ] 编写单元测试 `tests/test_tools/`
- [ ] 提交架构自评报告

---

## Phase 8: 多智能体协作（Agents）

*开发顺序依据规则 4.2.8*

### 协调器（`src/agents/coordinator.py`）

- [ ] 实现复杂度判断逻辑（简单 → 单链 / 复杂 → 多视角 — 依据技术架构 2.4 节）
- [ ] 实现三种执行模式（快速/平衡/深度 — 依据技术架构）

### 单链执行（`src/agents/single_chain.py`）

- [ ] 实现决策 Agent → 审查 Agent 管道（漂移阈值 0.15 — 依据技术架构）
- [ ] 实现审查 Agent 质量检查（风格一致性 + 输出质量）

### 多视角推理（`src/agents/multi_view.py`）

- [ ] 实现并行视角推理（2-5 个视角，Agent 根据复杂度自定 — 依据规则 2.3 节）
- [ ] 实现仲裁 Agent（综合各方论据 + 用户模型适配 → 最终建议）
- [ ] 实现每条链独立模型/记忆/技能调用

### 子代理管理（`src/agents/sub_agent.py`）

- [ ] 实现隔离 Agent 实例（独立沙箱 + 独立会话）
- [ ] 实现并行子代理上限（最多 5 个 — 依据规则 2.3 节）
- [ ] 实现消息队列通信（子代理 ↔ 主 Agent）
- [ ] 编写单元测试 `tests/test_agents/`
- [ ] 提交架构自评报告

---

## Phase 9: 网关与 API（Gateway）— CLI + REST 优先

*开发顺序依据规则 4.2.9*

### CLI 接口（`src/gateway/cli.py` 或 `cli.py`）

- [ ] 实现交互式 REPL（`shuyuancore chat` 命令）
- [ ] 实现单次查询模式（`shuyuancore ask "问题"`）
- [ ] 实现会话管理命令（list/create/switch/delete）
- [ ] 实现配置管理命令（`shuyuancore config`）

### REST API（`src/gateway/api.py`）

- [ ] 实现 FastAPI 应用骨架 + 中间件链（CORS / 请求日志 / 错误处理）
- [ ] 实现统一响应格式（`{code, message, data}` — 对齐 API 文档通用规范）
- [ ] 实现 `/health` 健康检查端点（对齐 `HealthCheckConfig`）
- [ ] 实现 `/conversations` CRUD（对齐 API 3.1 节 GET/POST/DELETE）
- [ ] 实现 `/conversations/{id}/messages`（对齐 API 3.1 节，含 FTS5 搜索 + 分页）
- [ ] 实现 `/chat` 对话端点（流式 SSE + 非流式）
- [ ] 实现 `/skills` 技能管理端点
- [ ] 实现 `/tools` 工具调用端点
- [ ] 实现 `/approvals` 审批操作端点
- [ ] 实现 `/cron` 定时任务端点
- [ ] 实现 `/config` 配置查看端点

### 平台适配器（按需后置）

- [ ] Telegram Bot 适配器（`src/gateway/telegram.py`）
- [ ] 微信适配器
- [ ] 企业微信适配器
- [ ] 飞书适配器
- [ ] 钉钉适配器
- [ ] QQ 适配器
- [ ] 编写单元测试 `tests/test_gateway/`
- [ ] 提交架构自评报告

---

## Phase 10: 部署与测试（Deploy & Test）

*开发顺序依据规则 4.2.10*

### 部署基础设施

- [ ] Systemd 服务脚本（`deploy/shuyuancore.service`）
- [ ] Nginx 反向代理配置（`deploy/nginx.conf`）
- [ ] Docker 容器化（`Dockerfile` + `docker-compose.yml`）
- [ ] 部署文档（安装方式：curl_bash/pip/homebrew/docker/source/cloud — 依据 `DeployConfig`）

### 自动化测试

- [ ] 实现全模块集成测试（API 端到端流程）
- [ ] 实现回归测试套件
- [ ] 配置 CI/CD 流水线（pytest + ruff + mypy）

### 数据迁移与回填

- [ ] 实现 Alembic 配置 + 初始迁移脚本（依据规则 2.5 节）
- [ ] 实现 ChromaDB 历史回填脚本（断点续传/批处理 20 条/幂等执行 — 依据规则 2.5 节）
- [ ] 实现备份脚本 + 恢复命令（`shuyuancore restore` — 依据安全规则）

### 最终验收

- [ ] 全量单元测试通过率 100%
- [ ] 核心模块行覆盖率 ≥ 85%（`src/config.py`, `src/models/`, `src/core/agent.py`, `src/memory/` — 依据规则 4.4 节）
- [ ] mypy --strict 零错误（渐近目标）
- [ ] ruff lint 零错误
- [ ] smoke test：服务启动 + `/health` 返回 200
- [ ] 提交最终验收报告

---

## 统计总览

| Phase | 模块 | 任务数 | 状态 |
|---|---|---|---|
| Phase 1 | 基础设施 | 20 | 12 ✅ / 8 ⬜ |
| Phase 2 | 模型层 | 10 | 全部待开始 |
| Phase 3 | 核心 Agent | 9 | 全部待开始 |
| Phase 4 | 记忆系统 | 14 | 全部待开始 |
| Phase 5 | 人格编译 | 10 | 全部待开始 |
| Phase 6 | 技能系统 | 10 | 全部待开始 |
| Phase 7 | 工具系统 | 7 + 14 ext | 全部待开始 |
| Phase 8 | 多智能体 | 6 | 全部待开始 |
| Phase 9 | 网关与 API | 18 | 全部待开始 |
| Phase 10 | 部署与测试 | 9 | 全部待开始 |
| **合计** | | **~113** | **12 ✅ / ~101 ⬜** |