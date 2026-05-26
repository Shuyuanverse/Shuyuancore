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

### 日志系统（`src/logging.py`）— ✅ 已完成

- [✅] 实现基础日志配置（控制台输出 + 文件输出，从 `Settings.deploy` 读取 log_level）
- [✅] 实现请求/关联 ID 自动注入（correlation ID / request ID，trace context 穿透）
- [✅] 实现日志轮转（`RotatingFileHandler`，单文件 50MB，保留 5 个 — 对齐 `LogRotationConfig`）
- [✅] 实现结构化日志输出（`structlog` JSON 格式，生产环境用，开发环境用彩色控制台）
- [✅] 实现敏感信息过滤（API Key / Token 自动打码，依据规则 5.5 安全准则）
- [✅] 集成 `src/config.py`：从 `DeployConfig.log_level` / `LogRotationConfig` 读取参数
- [✅] 编写 31 个单元测试 `tests/test_logging.py`
- [✅] 提交架构自评报告（已合并到 Phase 2 报告中）

### ⚠️ 技术债务（Phase 1）

- **TODO**: 签名 `_setup_logging` 参数与环境配置解耦，后续若新增 `DeployConfig.environment` 字段可切换 dev/prod 模式
- **TODO**: colorlog 彩色控制台输出在 structlog 环境下可进一步美化

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

- [✅] ~~**`src/logging.py` 依赖缺失**：`_client.py` 和 `router.py` 回退到标准 `logging`，后续集成结构化日志~~
- **`chat_stream` 未在单元测试中覆盖**：建议 Phase 9 集成时补充端到端测试
- **Router 不支持配置热加载**：后续可通过 `/config/reload` 端点扩展

---

## Phase 3: 核心 Agent（基于信念场退化实现）

*开发顺序依据规则 4.2.3*

### 3.1 信念存储（`src/core/belief_store.py`）
- [✅] 定义 `Belief` 数据类（字段：id, content, source, confidence, timestamp, dependencies, metadata）
- [✅] 实现 `BeliefStore` 类（内存字典，以 conversation_id 分区），提供 add/get/clear 等方法
- [✅] 编写单元测试 `tests/test_core/test_belief_store.py`

### 3.2 信念读出器（`src/core/reader.py`）
- [✅] 实现 `Reader` 类，接收 BeliefStore，提供 `read(conversation_id, user_query=None, max_tokens=4000)` 方法
- [✅] 读出逻辑：按时间倒序取最近 N 条信念，拼接 content 作为上下文
- [✅] 编写单元测试 `tests/test_core/test_reader.py`

### 3.3 工具调用集成（信念场中的工具）
- [✅] 修改 Agent 类，在 LLM 流式响应中实时检测 tool_calls（按已批准方案）
- [✅] 执行工具并将结果作为 Belief(source="tool") 添加到信念存储
- [✅] 将工具结果追加到上下文，继续 LLM 生成
- [✅] 编写单元测试 `tests/test_core/test_tool_integration.py`

### 3.4 Agent 主类（`src/core/agent.py`）
- [✅] Agent.__init__ 依赖注入：model_provider, belief_store, reader, tool_registry
- [✅] 实现 chat_stream(message, conversation_id=None) 方法：
  - 自动生成 conversation_id
  - 将用户消息作为 Belief(source="user") 添加到存储
  - 调用 reader.read() 获取上下文
  - 实现流式工具调用循环（实时检测 tool_calls）
  - yield 每个 token
  - 将最终回复作为 Belief(source="assistant") 添加到存储
  - 异步触发 _background_update（空实现）
- [✅] 编写单元测试 `tests/test_core/test_agent.py`

### 技术债务
- [⚠️] 信念存储仅内存，未持久化（Phase 4）
- [⚠️] 置信度固定为 1.0，无动态更新
- [⚠️] 未实现依赖传播和相关性排序

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

- [✅] 实现 `feature_flags.py` — 功能开关（从 `Settings.persona.feature_flags` 读取）
- [✅] 实现 `profile.py` — 数据结构定义（StyleDimensions, PersonaProfile）
- [✅] 实现 `perception.py` — 感知层（零 LLM 纯规则，6 类情绪，difflib 重复检测）
- [✅] 实现 `hard_fact_guard.py` — 硬事实防护（写入 beliefs 表 L1, memory_type='identity'）
- [✅] 创建 Alembic 迁移脚本（evolution_proposals, drift_history 表）
- [✅] 编写基础设施测试文件（test_feature_flags, test_perception, test_hard_fact_guard）

### 编译核心（Phase 2）

- [✅] 实现 `identity_prompt.py` — 身份 prompt 构建器
- [✅] 实现 `style_encoder.py` — 风格 7 维度编码器输出 StyleDimensions
- [✅] 实现 `anchor_manager.py` — 锚点版本管理（128 维风格 + 256 维决策锚点）
- [✅] 实现 `protection.py` — 风格保护流水线（漂移检测 + 校准指令 + 审视与调整）
- [✅] 编写编译核心测试文件（test_style_encoder, test_protection, test_anchor_manager）

### 编译器（Phase 3）

- [✅] 实现 `compiler.py` — 人格编译入口（通用模式 + 人格模式）
- [✅] 实现 `compile_generic` — 通用模式编译（从对话记录生成风格+决策锚点）
- [✅] 实现 `compile_persona` — 人格模式编译（从指定文本生成完整档案）
- [✅] 编写编译器测试文件

### 自主演化与管线编排（Phase 4）

- [✅] 实现 `autonomous_evolution.py` — 自主演化提议引擎（三档审核）
- [✅] 实现 `pipeline.py` — 全管线编排（同步感知 + 异步后台）
- [✅] 集成 Agent 主循环示例代码（chat_stream 中注入感知、风格保护、校准指令）
- [✅] 编写演化与管线测试文件（test_autonomous_evolution, test_pipeline）

### 技术债务

- **风格锚点暂未持久化到 beliefs 表**：当前为内存缓存，后续可写入 L6 信念
- **漂移检测为纯规则**：未使用 LLM 辅助提高精度
- **决策锚点 PCA 降维需 sklearn**：不可用时回退到截取前 256 维

---

## Phase 6: 技能系统（Skills）— ✅ 已完成

*开发顺序依据规则 4.2.6*

### 技能存取接口（`src/skills/interfaces.py`）

- [✅] 定义 `ISkillStore` 抽象基类
- [✅] 定义 `ISkillGraph` 抽象基类（因果图）

### 手动技能管理（`src/skills/manager.py`）

- [✅] 实现技能 CRUD（创建/读取/更新/删除技能文档 Markdown+YAML）
- [✅] 实现 `PersistentSkillStore`（SQLite 持久化 + 信念表关联）
- [✅] 实现 `PersistentSkillGraph`（因果图边管理 + 信念依赖同步）
- [✅] 实现技能版本记录
- [✅] 实现因果图边同步到 `beliefs.depends_on`

### 因果技能图（`src/skills/matcher.py`）

- [✅] 实现技能匹配（精确匹配 → 向量检索 → 前置条件检查 → 按置信度排序）
- [✅] 实现 200ms 超时保护
- [✅] 实现技能注入到 Agent system prompt

### 技能导入导出（`src/skills/importer.py`）

- [✅] 实现技能包导出（Markdown+JSON → `.zip`，含 manifest.json）
- [✅] 实现技能包导入（manifest 校验、依赖检查、重名策略）

### Curator 回收（`src/skills/curator.py`）

- [✅] 实现确定性回收（30天→stale，90天→archived，跳过 pinned）
- [✅] 实现置信度递减（-0.1，不低于 0.1）

### 自动技能提炼（`src/skills/extractor.py`）

- [✅] 实现价值分数计算（耗时/纠正/完善/跨会话/人格/错误恢复/工具失败率）
- [✅] 实现 LLM 生成技能内容（`qwen-turbo`）
- [✅] 实现"单次对话最多提炼 1 个技能"
- [✅] 集成到 Agent._background_update 异步调用

### Agent 集成

- [✅] 技能匹配注入 system prompt（chat_stream）
- [✅] 技能调用置信度更新
- [✅] 因果图边同步到 `beliefs.depends_on`

### 数据模型与迁移

- [✅] 创建 `SkillNode`, `SkillEdge`, `SkillUsage` 数据类
- [✅] 创建 Alembic 迁移 0003（`skill_nodes`, `skill_edges`, `skill_usage` 表）
- [✅] 技能信念统一映射（`layer=4`, `memory_type='skill'`）

### 测试覆盖

- [✅] 编写 6 个测试文件（test_manager, test_extractor, test_matcher, test_curator, test_importer, test_integration）
- [✅] 共 50 个测试用例全部通过
- [✅] 独立数据库隔离（临时文件，`:memory:`）
- [✅] 模拟外部依赖（LLM、向量检索）

### 配置更新

- [✅] SkillsConfig 新增 4 个配置项（`matching_timeout_ms`, `value_score_threshold`, `correction_keywords`, `refinement_keywords`）

### ⚠️ 技术债务

- **Curator LLM 审查未实现**：留到 Phase 7+
- **向量检索依赖现有信念集合**：无独立技能 ChromaDB 集合
- **置信度更新为同步**：写入 `beliefs` 表后需异步传播
- **`_try_exact_match` 使用独立 DB 连接**：无连接池
- **技能 Markdown 文件无 BCP-47 语言标记**：后续可扩展
- **导入未支持 source='community' 自动覆盖**：当前仅依据 version_history 判断

---

## Phase 7: 工具系统（Tools）

*开发顺序依据规则 4.2.7*

### 工具接口（`src/tools/interfaces.py`）

- [✅] 定义 `ITool` 抽象基类（execute/validate/describe）
- [✅] 定义 `IToolRegistry` 注册表接口（register/get/list/execute）
- [✅] 定义 `ToolResult`, `ToolSpec`, `ToolParameter` 数据类

### 工具执行基础设施

- [✅] 实现工具执行沙箱隔离（`src/tools/sandbox.py` → `src/security/sandbox.py`，Docker 沙箱 + 本地降级）
- [✅] 实现工具审批流程（`src/tools/approval.py` → `src/security/approval.py`，5 分钟超时 — 依据安全规则）
- [✅] 实现工具执行审计日志（`src/security/audit.py`，参数脱敏、内存存储）
- [✅] 实现 `ToolRegistry` 注册表（`src/tools/registry.py`，注册/发现/执行管道/审批集成/审计）

### Stage 1 核心工具实现

- [✅] 实现 `TerminalTool`（shell 命令执行，危险命令审批 — 依据安全规则）
- [✅] 实现 `FileOpsTool`（文件读写/搜索/列出目录/删除，路径安全检测）
- [✅] 实现 `ProcessTool`（进程列表/终止）
- [✅] 实现 `CodeExecTool`（Python/JavaScript 代码沙箱执行，强制 Docker）
- [✅] 实现 `MemoryTool`（记忆查询/写入/删除 — 调用 src/memory/ 接口）
- [✅] 实现 `SkillsTool`（技能列表/获取/创建/更新/删除/执行 — 调用 src/skills/ 接口）

### Stage 1 配置与异常更新

- [✅] 更新 `src/config.py` — 新增 `ToolsConfig`（12 个配置项）
- [✅] 更新 `config/default.yaml` — 新增 `tools:` 配置段
- [✅] 更新 `src/exceptions.py` — 新增 `ToolSandboxError`，修复 `ToolApprovalTimeoutError` 超时描述
- [✅] 更新 `pyproject.toml` — 新增可选依赖分组（tools/playwright/office/ocr/chart/crypto/media/all）
- [✅] 创建 `src/security/approval.py` — ApprovalManager（异步审批 + 超时）
- [✅] 创建 `src/security/audit.py` — AuditLogger（审计日志 + 参数脱敏）
- [✅] 创建 `src/security/sandbox.py` — SandboxExecutor（Docker 优先 + 本地降级）

### Stage 1 测试覆盖

- [✅] `tests/test_tools/test_core.py` — 20 个用例（覆盖 interfaces/approval/audit/sandbox/registry）
- [✅] `tests/test_tools/test_terminal.py` — 9 个用例（覆盖执行/验证/危险检测/沙箱不可用）
- [✅] `tests/test_tools/test_file_ops.py` — 8 个用例（覆盖 read/write/delete/list/路径安全）
- [✅] `tests/test_tools/test_process.py` — 6 个用例（覆盖 list/kill/validations）
- [✅] `tests/test_tools/test_code_exec.py` — 8 个用例（覆盖 python/js/沙箱不可用）
- [✅] `tests/test_tools/test_memory_tool.py` — 6 个用例（覆盖 search/write/delete）
- [✅] `tests/test_tools/test_skills_tool.py` — 6 个用例（覆盖 list/create/delete）

### ⚠️ 技术债务（Stage 1）

- [⚠️] **security/approval.py 全局单例**：ApprovalManager 使用模块级单例，多用户场景下需改为用户级
- [⚠️] **AuditLogger 内存存储**：日志在内存中，未持久化到 SQLite，高频场景会丢失日志
- [⚠️] **SandboxExecutor Docker 缓存锁定**：_docker_available 缓存后不会重新检测
- [⚠️] **TerminalTool 本地降级**：Docker 不可用时返回"需要审批"错误，需 Agent 循环配合而非自动触发审批
- [⚠️] **memory/skills 工具依赖**：依赖的具体 store 在当前可能不完整，使用 try/except ImportError 处理
- [⚠️] **Docker/Playwright 等可选依赖**：`shuyuancore[tools]` 等扩展包需用户手动安装
- [⚠️] **架构自评报告**：已提交 `reports/arch_review_tools_stage1.md`

### 后续 Stage（待实现）

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
| Phase 3 | 核心 Agent | 14 | 14 ✅ |
| Phase 4 | 记忆系统 | 16 + 10 项技术债务 | 16 ✅ |
| Phase 5 | 人格编译 | 14 + 3 项技术债务 | 14 ✅ |
| Phase 6 | 技能系统 | 10 | 全部待开始 |
| Phase 7 | 工具系统 | 7 + 14 ext | 全部待开始 |
| Phase 8 | 多智能体 | 6 | 全部待开始 |
| Phase 9 | 网关与 API | 18 | 全部待开始 |
| Phase 10 | 部署与测试 | 9 | 全部待开始 |
| **合计** | | **~119 + 10** | **52 ✅ / ~67 ⬜** |
