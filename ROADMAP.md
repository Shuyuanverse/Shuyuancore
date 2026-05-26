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

## Phase 2: 模型层（Models）— ✅ 已完成

*开发顺序依据规则 4.2.2*

### 模型提供者接口（`src/models/interfaces.py`）

- [✅] 定义 `IModelProvider` 抽象基类（`chat()`, `chat_stream()`, `embed()`, `check_health()` — 依据技术架构 2.2 节）
- [✅] 定义数据类 `ChatResult`, `EmbeddingResult`, `HealthStatus`, `ChatStreamEvent`
- [✅] 定义 `ProviderRegistry` 注册表类（register/get/list_providers/check_all）

### DashScope 提供者（`src/models/dashscope.py`）

- [✅] 实现 `DashScopeProvider(IModelProvider)`（依据 `ModelsConfig.providers.dashscope`）
- [✅] 实现 OpenAI 兼容 API 调用（base_url dashscope.aliyuncs.com/compatible-mode/v1）
- [✅] 实现 text-embedding-v2 嵌入服务（1536 维 — 依据技术架构 2.2 节 & 规则 2.3 节）
- [✅] 实现 `chat_stream` 流式对话
- [✅] 添加超时和重试机制（默认 30s 超时，3 次重试，指数退避 — 依据规则 5.5）

### DeepSeek 提供者（`src/models/deepseek.py`）

- [✅] 实现 `DeepSeekProvider(IModelProvider)`（chat only，embed 抛出 NotImplementedError）
- [✅] 实现 OpenAI 兼容 API 调用（base_url api.deepseek.com/v1）
- [✅] 实现 `chat_stream` 流式对话
- [✅] 添加超时和重试机制

### OpenAI 兼容提供者（`src/models/openai_compat.py`）

- [✅] 实现通用 `OpenAICompatProvider`，支持任意 OpenAI-compatible endpoint
- [✅] `OllamaProvider` 子类（base_url http://localhost:11434，Ollama 原生 API /api/chat）
- [✅] 支持可选的 embedding_model 参数

### 模型路由与主备切换（`src/models/router.py`）

- [✅] 实现任务类型 → 模型路由表（6 类：code/chat/math/embedding/tool/review — 对齐 `ModelRoutingConfig`）
- [✅] 实现主备切换逻辑（超时/5xx → 自动切换备选，连续 3 次 429 触发切换，5 分钟自动恢复）
- [✅] 实现模型连接健康检查（`check_health()` 全量遍历注册表）
- [✅] 实现 `switch_model(role, model_spec)` API 函数（供 Phase 9 FastAPI 挂载）
- [✅] 实现 `get_current_models()`, `get_routing_rules()` 查询接口

### CLI 命令行（`cli.py`）

- [✅] 实现 `model switch <role> <model>` 切换模型
- [✅] 实现 `model list` 查看当前模型配置
- [✅] 实现 `model routing` 查看路由规则
- [✅] 实现 `health` 查看 Provider 健康状态

### 单元测试

- [✅] 编写 48 个单元测试（5 个测试文件，覆盖所有正常/异常路径）
- [✅] 测试主备切换正常和双失败场景
- [✅] 所有 214 个测试通过（48 新增 + 166 旧测试），ruff 零错误

### 架构自评报告

- [✅] 提交架构自评报告 `reports/arch_review_models.md`

### ⚠️ 技术债务

- **`src/logging.py` 依赖缺失**：`_client.py` 和 `router.py` 回退到标准 `logging`，后续集成结构化日志
- **`chat_stream` 未在单元测试中覆盖**：建议 Phase 9 集成时补充端到端测试
- **Router 不支持配置热加载**：后续可通过 `/config/reload` 端点扩展

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

## Phase 4: 记忆系统（Memory）— ✅ 已完成

*开发顺序依据规则 4.2.4*

### 记忆存取接口（`src/memory/interfaces.py`）

- [✅] 定义 `IEntityExtractor` 和 `IEmotionAnalyzer` Protocol 接口（依据规则 2.2 节）
- [✅] 定义 `IBeliefStore` 和 `IReader` 抽象基类（位于 `src/core/interfaces.py`）

### L1 核心记忆（`src/memory/core_memory.py`）

- [✅] 创建 `core_memory.py` 骨架文件（待后续实现 MEMORY.md + USER.md 注入）
- [✅] `BeliefReader` 实现 L1 优先排序策略（layer=1 权重最高）

### L3 长期历史 — SQLite（`src/memory/belief_store.py`）

- [✅] 实现 SQLite 数据库初始化（PRAGMA journal_mode=WAL, foreign_keys=ON, busy_timeout=5000 — 依据规则 2.4 节）
- [✅] 实现 `beliefs` 表创建（20 个字段，对齐 Belief 数据类）
- [✅] 实现 `beliefs_fts` FTS5 全文索引
- [✅] 实现完整 CRUD（add/get/get_by_id/update/clear/remove）
- [✅] 实现 FTS5 关键词检索 + LIKE 降级策略
- [✅] 实现 `propagate_confidence` 和 `overthrow` 委托

### 置信度衰减（`src/memory/decay.py`）

- [✅] 实现指数衰减公式（`base_confidence × exp(-rate × elapsed_days)`）
- [✅] 实现 6 层差异化衰减速率（L1=0.0005 ~ L6=0.0）
- [✅] 实现置信度地板值 0.1

### 信念传播与推翻（`src/memory/propagation.py`）

- [✅] 实现递归置信度传播（visited 集合防环，上限 1000）
- [✅] 实现推翻机制（status=superseded + superseded_by + metadata 记录）

### 记忆写入三通道（`src/memory/writer.py`）

- [✅] 实现规则通道（`RuleBasedWriter`：12 条正则模式，无 LLM 参与）
- [✅] 实现手动通道（`ManualMemoryWriter`：`记住:` 前缀）
- [✅] 实现 AI 推理通道（`AiInferenceWriter`：importance >= 0.6 阈值）
- [✅] 实现复合信念检测（`CompositeBeliefDetector`：>=3 轮，>=100 字符，>=3 实体）

### 多维唤醒（`src/memory/wake.py`）

- [✅] 实现唤醒分数公式（semantic 0.5 + keyword 0.2 + entity 0.15 + emotion 0.1）
- [✅] 实现唤醒就绪度（技术关键词密度 + 动量加成）
- [✅] 实现频率控制（`WakeFrequencyTracker`：单信念上限 5 次/小时）

### 实体抽取与情感分析（`src/memory/extractor.py`）

- [✅] 实现 `JiebaEntityExtractor`（jieba.posseg 名词性实体）
- [✅] 实现 `SnowNlpEmotionAnalyzer`（SnowNLP 情感分数）
- [✅] 实现 `CompositeExtractor`（多抽取器合并去重）

### 统一检索接口（`src/memory/reader.py`）

- [✅] 实现 `BeliefReader(IReader)`：按 layer 优先级排序 + token 限制 + FTS5 检索
- [✅] Agent 集成点预留（通过 IReader 接口注入）

### 架构自评报告

- [✅] 提交架构自评报告 `reports/arch_review_memory.md`

### ⚠️ 技术债务

- **L3 ChromaDB 未实现**：`chroma_store.py` 为骨架文件，向量检索已用内存索引实现，可选切换 ChromaDB
- [✅] **Embedding 服务实现**：已用 DashScope text-embedding-v2 + 重试逻辑实现，集成到 belief_store 写入流程
- [✅] **向量检索实现**：`VectorStore` 内存索引 + ChromaDB 可选后端，`search_similar` 优先语义检索
- [✅] **配置驱动**：`decay.py` 衰减速率、`writer.py` 阈值、`wake.py` 唤醒参数从 `config/default.yaml` 统一读取
- [✅] **单元测试覆盖**：`tests/test_memory/` 下 10 个测试文件共 104 个用例，覆盖全局核心逻辑路径
- **Alembic 迁移脚本不完整**：beliefs_fts 虚拟表的创建未纳入迁移管理
- **并发写入冲突风险**：PersistentBeliefStore 使用单一 aiosqlite Connection，无连接池
- **FTS5 同步索引效率**：每次写入同步更新 FTS5 索引，高频场景下可能成为瓶颈

---

## Phase 5: 人格编译与风格保护（Persona）

*开发顺序依据规则 4.2.5*

### 基础设施（Phase 1）

- [ ] 实现 `feature_flags.py` — 功能开关（从 `Settings.persona.feature_flags` 读取）
- [ ] 实现 `profile.py` — 数据结构定义（StyleDimensions, PersonaProfile）
- [ ] 实现 `perception.py` — 感知层（零 LLM 纯规则，6 类情绪，difflib 重复检测）
- [ ] 实现 `hard_fact_guard.py` — 硬事实防护（写入 beliefs 表 L1, memory_type='identity'）
- [ ] 创建 Alembic 迁移脚本（evolution_proposals, drift_history 表）
- [ ] 编写基础设施测试文件

### 编译核心（Phase 2）

- [ ] 实现 `identity_prompt.py` — 身份 prompt 构建器
- [ ] 实现 `style_encoder.py` — 风格 7 维度编码器输出 StyleDimensions
- [ ] 实现 `anchor_manager.py` — 锚点版本管理（128 维风格 + 256 维决策锚点）
- [ ] 实现 `protection.py` — 风格保护流水线（漂移检测 + 校准指令 + 审视与调整）
- [ ] 编写编译核心测试文件

### 编译器（Phase 3）

- [ ] 实现 `compiler.py` — 人格编译入口（通用模式 + 人格模式）
- [ ] 实现 `compile_generic` — 通用模式编译（从对话记录生成风格+决策锚点）
- [ ] 实现 `compile_persona` — 人格模式编译（从指定文本生成完整档案）
- [ ] 编写编译器测试文件

### 自主演化与管线编排（Phase 4）

- [ ] 实现 `autonomous_evolution.py` — 自主演化提议引擎（三档审核）
- [ ] 实现 `pipeline.py` — 全管线编排（同步感知 + 异步后台）
- [ ] 集成 Agent 主循环（chat_stream 中注入感知、风格保护、校准指令）
- [ ] 编写演化与管线测试文件

### 技术债务

- **风格锚点暂未持久化到 beliefs 表**：当前为内存缓存，后续可写入 L6 信念
- **漂移检测为纯规则**：未使用 LLM 辅助提高精度
- **决策锚点 PCA 降维需 sklearn**：不可用时回退到截取前 256 维

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
| Phase 2 | 模型层 | 10 | 10 ✅ |
| Phase 3 | 核心 Agent | 9 | 全部待开始 |
| Phase 4 | 记忆系统 | 16 + 10 项技术债务 | 16 ✅ |
| Phase 5 | 人格编译 | 10 | 全部待开始 |
| Phase 6 | 技能系统 | 10 | 全部待开始 |
| Phase 7 | 工具系统 | 7 + 14 ext | 全部待开始 |
| Phase 8 | 多智能体 | 6 | 全部待开始 |
| Phase 9 | 网关与 API | 18 | 全部待开始 |
| Phase 10 | 部署与测试 | 9 | 全部待开始 |
| **合计** | | **~119 + 10** | **38 ✅ / ~81 ⬜** |
