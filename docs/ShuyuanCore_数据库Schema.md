# ShuyuanCore 数据库 Schema

版本：v2.0 | 日期：2026-05-29
上次更新：补齐全部 16 个迁移版本，修正文档-迁移不一致问题

## 一、数据库选型

### 主数据库：SQLite + WAL 模式
- 单文件部署（`data/state.db`），零配置
- WAL 模式保证写入不阻塞读取
- FTS5 支持全文检索（messages、beliefs）

### 向量数据库：ChromaDB PersistentClient
- 持久化存储（`data/chroma/`）
- 自动 embedding（DashScope text-embedding-v2，1536 维）
- 支持 metadata 过滤

---

## 二、SQLite 表结构（按迁移版本排序）

### 2.1 beliefs 表（0001）

**信念存储** — 记忆系统的核心存储层，支持多层级记忆、置信度衰减、信念传播与覆盖。

```sql
CREATE TABLE beliefs (
    id                TEXT PRIMARY KEY,          -- UUID
    conversation_id   TEXT NOT NULL,             -- 关联对话 ID
    content           TEXT NOT NULL,             -- 信念内容
    source            TEXT(16) NOT NULL,         -- 来源：chat/extract/merge/manual
    confidence        REAL NOT NULL DEFAULT 1.0, -- 当前置信度
    base_confidence   REAL NOT NULL DEFAULT 1.0, -- 基础置信度
    last_accessed     INTEGER NOT NULL DEFAULT 0,-- 最后访问时间戳
    memory_type       TEXT(16) NOT NULL DEFAULT 'chat',  -- chat/task/skill/identity
    layer             INTEGER NOT NULL DEFAULT 3,-- 记忆层级：1-6
    entities          TEXT NOT NULL DEFAULT '[]', -- 关联实体 JSON
    emotion           REAL NOT NULL DEFAULT 0.5, -- 情感关联值
    depends_on        TEXT NOT NULL DEFAULT '[]', -- 依赖的信念 ID 列表
    child_belief_ids  TEXT NOT NULL DEFAULT '[]', -- 子信念 ID 列表
    superseded_by     TEXT(64),                  -- 被哪个信念覆盖
    status            TEXT(16) NOT NULL DEFAULT 'active', -- active/superseded
    is_composite      INTEGER NOT NULL DEFAULT 0,-- 是否为复合信念
    timestamp         INTEGER NOT NULL DEFAULT 0,-- 事件时间戳
    metadata_json     TEXT NOT NULL DEFAULT '{}', -- 元数据 JSON
    user_id           TEXT NOT NULL DEFAULT 'anonymous', -- 用户 ID（0005 添加）
    conversation_date TEXT(10),                  -- 对话日期 YYYY-MM-DD（0008 添加）
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL
);
CREATE INDEX idx_beliefs_layer ON beliefs(layer);
CREATE INDEX idx_beliefs_status ON beliefs(status);
CREATE INDEX idx_beliefs_memory_type ON beliefs(memory_type);
CREATE INDEX idx_beliefs_conversation_layer ON beliefs(conversation_id, layer);
CREATE INDEX idx_beliefs_user_id ON beliefs(user_id);
CREATE INDEX idx_beliefs_user_conversation ON beliefs(user_id, conversation_id, layer);
-- FTS5 全文检索
CREATE VIRTUAL TABLE beliefs_fts USING fts5(content, content='beliefs', content_rowid='rowid');
```

### 2.2 evolution_proposals & drift_history 表（0002）

**人格演化提议和漂移历史** — 人格模块中记录演化提议和风格漂移检测历史。

```sql
CREATE TABLE evolution_proposals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id        TEXT(100) NOT NULL,
    proposal_id       TEXT(100) NOT NULL UNIQUE,
    dimension         TEXT(100) NOT NULL,        -- 演化维度
    current_value     REAL NOT NULL,             -- 当前值
    proposed_value    REAL NOT NULL,             -- 建议值
    delta             REAL NOT NULL,             -- 变化量
    trigger_type      TEXT(50) NOT NULL,         -- 触发方式
    reason            TEXT,                      -- 提议理由
    consistency_score REAL NOT NULL DEFAULT 0.0, -- 一致性评分
    status            TEXT(20) NOT NULL DEFAULT 'pending', -- pending/accepted/rejected
    created_at        TEXT NOT NULL              -- ISO 时间戳
);
CREATE INDEX idx_ep_persona ON evolution_proposals(persona_id);
CREATE INDEX idx_ep_status ON evolution_proposals(persona_id, status);

CREATE TABLE drift_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id          TEXT(100) NOT NULL,
    drift_score         REAL NOT NULL,           -- 漂移分数
    alert_level         TEXT(20) NOT NULL,        -- none/warn/calibrate/severe
    dimensions          TEXT,                     -- 各维度变化 JSON
    calibration_applied INTEGER NOT NULL DEFAULT 0, -- 是否已校准
    created_at          TEXT NOT NULL             -- ISO 时间戳
);
CREATE INDEX idx_dh_persona ON drift_history(persona_id);
CREATE INDEX idx_dh_created ON drift_history(persona_id, created_at);
```

### 2.3 skill_nodes, skill_edges & skill_usage 表（0003）

**技能系统** — 技能图谱的核心存储，包含技能节点、有向边和使用记录。

```sql
CREATE TABLE skill_nodes (
    node_id           TEXT(64) PRIMARY KEY,
    name              TEXT(128) NOT NULL UNIQUE,
    node_type         TEXT(16) NOT NULL DEFAULT 'skill',
    belief_id         TEXT(64) NOT NULL UNIQUE,   -- 关联的信念 ID
    description       TEXT NOT NULL DEFAULT '',
    tags              TEXT NOT NULL DEFAULT '[]',
    preconditions     TEXT NOT NULL DEFAULT '[]',
    causality_level0  TEXT NOT NULL DEFAULT '',
    causality_level1  TEXT NOT NULL DEFAULT '',
    causality_level2  TEXT NOT NULL DEFAULT '',
    boundaries        TEXT NOT NULL DEFAULT '[]',
    failure_modes     TEXT NOT NULL DEFAULT '[]',
    dependencies      TEXT NOT NULL DEFAULT '[]',
    version_history   TEXT NOT NULL DEFAULT '[]',
    source            TEXT(16) NOT NULL DEFAULT 'manual', -- （0007 添加） manual/extract/import
    status            TEXT(16) NOT NULL DEFAULT 'active',
    is_pinned         INTEGER NOT NULL DEFAULT 0,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL
);
CREATE INDEX idx_skill_nodes_status ON skill_nodes(status);
CREATE INDEX idx_skill_nodes_belief ON skill_nodes(belief_id);
CREATE INDEX idx_skill_nodes_name ON skill_nodes(name);
CREATE INDEX idx_skill_nodes_source ON skill_nodes(source);

CREATE TABLE skill_edges (
    edge_id    TEXT(64) PRIMARY KEY,
    from_node  TEXT(128) NOT NULL,
    to_node    TEXT(128) NOT NULL,
    edge_type  TEXT(20) NOT NULL DEFAULT 'enables', -- enables/conflicts/synergizes
    created_at INTEGER NOT NULL
);
CREATE INDEX idx_skill_edges_from ON skill_edges(from_node);
CREATE INDEX idx_skill_edges_to ON skill_edges(to_node);

CREATE TABLE skill_usage (
    usage_id        TEXT(64) PRIMARY KEY,
    skill_name      TEXT(128) NOT NULL,
    conversation_id TEXT(64) NOT NULL DEFAULT '',
    invoked_at      INTEGER NOT NULL,
    success         INTEGER,                      -- 0/1/null
    user_feedback   TEXT(16),                     -- positive/negative/null
    duration_ms     INTEGER
);
CREATE INDEX idx_skill_usage_name ON skill_usage(skill_name);
CREATE INDEX idx_skill_usage_conversation ON skill_usage(conversation_id);
```

### 2.4 approvals 表（0004）

**审批记录** — 敏感工具调用的审批请求持久化存储。

```sql
CREATE TABLE approvals (
    approval_id  TEXT(128) PRIMARY KEY,
    user_id      TEXT(64) NOT NULL,
    tool_name    TEXT(64) NOT NULL,
    params_json  TEXT NOT NULL DEFAULT '{}',
    status       TEXT(16) NOT NULL DEFAULT 'pending',  -- pending/approved/denied/expired
    approved     INTEGER,                              -- 0/1/null
    reason       TEXT NOT NULL DEFAULT '',
    resolved_by  TEXT(64) NOT NULL DEFAULT '',
    timeout      INTEGER NOT NULL DEFAULT 300,         -- 超时秒数
    stream_id    TEXT(64),                             -- 关联 SSE 流 ID
    created_at   REAL NOT NULL,
    resolved_at  REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX idx_approvals_user_id ON approvals(user_id);
CREATE INDEX idx_approvals_status ON approvals(user_id, status);
CREATE INDEX idx_approvals_stream ON approvals(stream_id);
```

### 2.5 audit_logs 表（0006）

**审计日志** — 全链路操作行为记录。

```sql
CREATE TABLE audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL,        -- tool_call/approve/deny/model_switch/login
    resource    TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '{}',
    result      TEXT NOT NULL DEFAULT 'success',  -- success/failure
    approved    INTEGER,              -- 0/1/null
    approval_id TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0.0,
    ip_address  TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    timestamp   REAL NOT NULL
);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
```

> **注意**：审计日志还有双层写入机制——内存缓存（最多 10000 条）+ 异步刷库。调用 `log()` 仅写缓存，调用 `log_async()` 或 `flush_all()` 才写入数据库。

### 2.6 working_memory_projects & working_memory_todos 表（0009）

**工作记忆** — L2 工作记忆的持久化存储。

```sql
CREATE TABLE working_memory_projects (
    id              TEXT(64) PRIMARY KEY,
    project_name    TEXT(255) NOT NULL UNIQUE,
    notes           TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    last_accessed_at INTEGER NOT NULL,
    is_archived     INTEGER NOT NULL DEFAULT 0,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_wmp_name ON working_memory_projects(project_name);
CREATE INDEX idx_wmp_accessed ON working_memory_projects(last_accessed_at);

CREATE TABLE working_memory_todos (
    id           TEXT(64) PRIMARY KEY,
    project_id   TEXT(64) NOT NULL,
    content      TEXT NOT NULL,
    status       TEXT(32) NOT NULL DEFAULT 'pending',  -- pending/in_progress/completed
    priority     INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    completed_at INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (project_id) REFERENCES working_memory_projects(id) ON DELETE CASCADE
);
CREATE INDEX idx_todos_project_status ON working_memory_todos(project_id, status);
CREATE INDEX idx_todos_priority ON working_memory_todos(priority);
```

### 2.7 user_models, user_goals, user_preferences & user_predictions 表（0010）

**用户心理模型** — 用户状态追踪、偏好管理和行为预测。

```sql
CREATE TABLE user_models (
    user_id            TEXT(64) PRIMARY KEY,
    emotional_state    REAL NOT NULL DEFAULT 0.5,    -- 0=消极, 1=积极
    engagement_level   REAL NOT NULL DEFAULT 0.5,    -- 0=低, 1=高
    trust_level        REAL NOT NULL DEFAULT 0.5,
    frustration_level  REAL NOT NULL DEFAULT 0.0,
    curiosity_level    REAL NOT NULL DEFAULT 0.5,
    state_updated_at   INTEGER NOT NULL DEFAULT 0,
    interaction_count  INTEGER NOT NULL DEFAULT 0,
    last_interaction_at INTEGER NOT NULL DEFAULT 0,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE user_goals (
    id           TEXT(64) PRIMARY KEY,
    user_id      TEXT(64) NOT NULL,
    content      TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 0,
    status       TEXT(32) NOT NULL DEFAULT 'active', -- active/completed/abandoned
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    completed_at INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (user_id) REFERENCES user_models(user_id) ON DELETE CASCADE
);
CREATE INDEX idx_user_goals_user_status ON user_goals(user_id, status);

CREATE TABLE user_preferences (
    user_id    TEXT(64) NOT NULL,
    category   TEXT(64) NOT NULL,       -- 偏好类别
    key        TEXT(255) NOT NULL,       -- 偏好键名
    value      TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source     TEXT(64) NOT NULL DEFAULT 'inferred',  -- inferred/explicit/manual
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, category, key),
    FOREIGN KEY (user_id) REFERENCES user_models(user_id) ON DELETE CASCADE
);

CREATE TABLE user_predictions (
    id                     TEXT(64) PRIMARY KEY,
    user_id                TEXT(64) NOT NULL,
    predicted_action       TEXT(255) NOT NULL,
    confidence             REAL NOT NULL,
    reasoning              TEXT,
    suggested_response     TEXT,
    alternative_actions_json TEXT NOT NULL DEFAULT '[]',
    metadata_json          TEXT NOT NULL DEFAULT '{}',
    is_correct             INTEGER,               -- 0/1/null（用户反馈）
    feedback_at            INTEGER,
    created_at             INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user_models(user_id) ON DELETE CASCADE
);
CREATE INDEX idx_user_predictions_user_created ON user_predictions(user_id, created_at);
```

### 2.8 evolution_modules & evolution_collaborations 表（0011）

**自演化模块** — 自演化系统的模块存储和协作追踪。

```sql
CREATE TABLE evolution_modules (
    id              TEXT(64) PRIMARY KEY,
    name            TEXT(255) NOT NULL,
    prompt_text     TEXT NOT NULL,
    memory_partition TEXT(255),
    skill_subgraph  TEXT,
    task_type       TEXT(64),
    trigger_count   INTEGER NOT NULL DEFAULT 0,
    last_trigger_at INTEGER,
    status          TEXT(32) NOT NULL DEFAULT 'active', -- active/archived
    created_at      INTEGER NOT NULL,
    archived_at     INTEGER,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_em_name ON evolution_modules(name);
CREATE INDEX idx_em_last_trigger ON evolution_modules(last_trigger_at);

CREATE TABLE evolution_collaborations (
    id           TEXT(64) PRIMARY KEY,
    from_module  TEXT(64) NOT NULL,
    to_module    TEXT(64) NOT NULL,
    timestamp    INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_collaboration_modules ON evolution_collaborations(from_module, to_module);
CREATE INDEX idx_collaboration_timestamp ON evolution_collaborations(timestamp);
```

### 2.9 hard_facts 表（0012）

**硬事实** — 经过验证的不可变事实，用于风格保护和对话一致性。

```sql
CREATE TABLE hard_facts (
    id                 TEXT(64) PRIMARY KEY,
    content            TEXT NOT NULL,
    category           TEXT(64) NOT NULL,
    sub_category       TEXT(64),
    confidence         REAL NOT NULL DEFAULT 1.0,
    source             TEXT(64) NOT NULL,
    verified           INTEGER NOT NULL DEFAULT 0,  -- 0=未验证, 1=已验证
    verification_count INTEGER NOT NULL DEFAULT 0,
    last_verified_at   INTEGER,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_hard_facts_category_sub ON hard_facts(category, sub_category);
CREATE INDEX idx_hard_facts_verified ON hard_facts(verified);
```

### 2.10 messages 表（0013 ★ 新增）

**对话消息** — 所有对话消息的持久化存储，包含 FTS5 全文检索。

```sql
CREATE TABLE messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT(64) NOT NULL,
    user_id      TEXT(64) NOT NULL,
    platform     TEXT(32) NOT NULL DEFAULT 'cli',  -- cli/telegram/wechat/feishu/dingtalk/qq
    role         TEXT(16) NOT NULL,                -- user/assistant/system/tool
    content      TEXT NOT NULL,
    tokens_used  INTEGER NOT NULL DEFAULT 0,
    tool_calls   TEXT,                              -- JSON: [{"name":"terminal","params":"ls"}]
    metadata_json TEXT,                             -- JSON: {"model":"qwen-max"}
    temperature  REAL NOT NULL DEFAULT 0.7,
    created_at   INTEGER NOT NULL                   -- unix timestamp (ms)
);
CREATE INDEX idx_messages_session_created ON messages(session_id, created_at);
CREATE INDEX idx_messages_user_created ON messages(user_id, created_at);

-- FTS5 全文检索虚拟表 + 自动同步触发器
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id'
);
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
```

### 2.11 sessions 表（0013 ★ 新增）

**对话会话** — 会话级元数据管理。

```sql
CREATE TABLE sessions (
    id            TEXT(64) PRIMARY KEY,         -- UUID
    user_id       TEXT(64) NOT NULL,
    platform      TEXT(32) NOT NULL DEFAULT 'cli',
    title         TEXT(255),                    -- 会话标题
    identity_id   TEXT(64) NOT NULL DEFAULT 'default',
    current_model TEXT(64) NOT NULL DEFAULT 'dashscope/qwen-max',
    message_count INTEGER NOT NULL DEFAULT 0,
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    status        TEXT(16) NOT NULL DEFAULT 'active',  -- active/archived/deleted
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    archived_at   INTEGER
);
CREATE INDEX idx_sessions_user_updated ON sessions(user_id, updated_at);
CREATE INDEX idx_sessions_status ON sessions(status, updated_at);
```

### 2.12 decisions & decision_patterns 表（0014 ★ 新增）

**决策记录与模式** — L5 关系记忆的核心，记录决策上下文并从中提取行为模式。

```sql
CREATE TABLE decisions (
    id           TEXT(64) PRIMARY KEY,
    user_id      TEXT(64) NOT NULL,
    session_id   TEXT(64),                      -- 关联会话（可选）
    context      TEXT NOT NULL,                  -- 当时在做什么
    options      TEXT NOT NULL,                  -- JSON 数组：["方案A","方案B"]
    chosen       TEXT NOT NULL,                  -- 最终选择
    reason       TEXT NOT NULL,                  -- 选择原因
    state_at_time TEXT,                          -- 当时状态 JSON
    verified     TEXT(16) NOT NULL DEFAULT 'pending',  -- correct/wrong/pending/unknown
    tags         TEXT,                           -- JSON 标签
    created_at   INTEGER NOT NULL
);
CREATE INDEX idx_decisions_user_created ON decisions(user_id, created_at);
CREATE INDEX idx_decisions_tags ON decisions(tags);

CREATE TABLE decision_patterns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern      TEXT NOT NULL,                  -- "高压下偏好简化方案"
    confidence   REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 1,
    last_used_at INTEGER,
    created_at   INTEGER NOT NULL
);
CREATE INDEX idx_dp_created ON decision_patterns(created_at);
```

### 2.13 goals 表（0014 ★ 新增）

**目标追踪** — 跨轮次持久化目标管理，支持层级子目标和依赖关系。

```sql
CREATE TABLE goals (
    id             TEXT(64) PRIMARY KEY,
    user_id        TEXT(64) NOT NULL,
    session_id     TEXT(64),                     -- null=全局目标
    description    TEXT NOT NULL,
    status         TEXT(16) NOT NULL DEFAULT 'active',  -- active/completed/abandoned
    progress       REAL NOT NULL DEFAULT 0.0,    -- 0-100
    dependencies   TEXT,                          -- JSON: ["goal_001"]
    parent_goal_id TEXT(64),                      -- 父目标 ID
    auto_created   INTEGER NOT NULL DEFAULT 0,    -- 1=Agent 自动创建
    created_at     INTEGER NOT NULL,
    completed_at   INTEGER
);
CREATE INDEX idx_goals_user_status ON goals(user_id, status, created_at);
```

### 2.14 jobs 表（0015 ★ 新增）

**定时任务** — cron / 条件触发 / 任务链的持久化存储。

```sql
CREATE TABLE jobs (
    id                TEXT(64) PRIMARY KEY,
    name              TEXT(255) NOT NULL,
    schedule          TEXT NOT NULL,              -- cron 表达式或自然语言
    cron_parsed       TEXT(64),                   -- 解析后标准 cron
    prompt            TEXT NOT NULL,               -- 执行提示
    skill             TEXT(128),                   -- 预加载技能名
    deliver_to        TEXT,                        -- JSON 数组：目标平台
    is_active         INTEGER NOT NULL DEFAULT 1,
    execution_count   INTEGER NOT NULL DEFAULT 0,
    last_run_at       INTEGER,
    next_run_at       INTEGER NOT NULL,
    chain_next_job_id TEXT(64),                    -- 任务链后继
    condition_trigger TEXT,                        -- JSON 条件配置
    condition_state   TEXT(16) NOT NULL DEFAULT 'standby',  -- standby/triggered/cooldown
    no_agent          INTEGER NOT NULL DEFAULT 0,  -- 1=不消耗 LLM
    timeout_seconds   INTEGER NOT NULL DEFAULT 300,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL
);
CREATE INDEX idx_jobs_active_next ON jobs(is_active, next_run_at);
CREATE INDEX idx_jobs_condition ON jobs(condition_state);
```

### 2.15 personas 表（0016 ★ 新增）

**人格档案** — 编译后的人格档案存储。

```sql
CREATE TABLE personas (
    id              TEXT(64) PRIMARY KEY,
    name            TEXT(255) NOT NULL,
    description     TEXT,
    profile         TEXT NOT NULL,                -- JSON：完整人格档案
    style_vector    TEXT,                          -- JSON：风格向量
    anchor_vector   TEXT,                          -- JSON：决策锚点向量
    created_from    TEXT(32) NOT NULL DEFAULT 'manual',  -- compile/import/manual
    source_text_hash TEXT(64),                     -- 输入文本 hash
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
CREATE INDEX idx_personas_name ON personas(name);
```

### 2.16 identities 表（0016 ★ 新增）

**身份管理** — 多身份矩阵，支持通用模式和人格模式。

```sql
CREATE TABLE identities (
    id           TEXT(64) PRIMARY KEY,
    name         TEXT(255) NOT NULL,
    mode         TEXT(16) NOT NULL DEFAULT 'general',  -- general/persona
    type         TEXT(16) NOT NULL DEFAULT 'work',     -- work/study/research/custom
    persona_id   TEXT(64),                              -- 关联人格 ID
    profile_path TEXT,                                  -- 身份数据路径
    memory_path  TEXT,                                  -- L1 核心记忆路径
    is_active    INTEGER NOT NULL DEFAULT 0,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);
CREATE INDEX idx_identities_mode_active ON identities(mode, is_active);
```

### 2.17 curator_runs 表（0016 ★ 新增）

**Curator 运行记录** — 技能回收器的执行快照。

```sql
CREATE TABLE curator_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    phase            TEXT(16) NOT NULL DEFAULT 'phase1',  -- phase1/phase2
    skills_examined  INTEGER NOT NULL DEFAULT 0,
    skills_retained  INTEGER NOT NULL DEFAULT 0,
    skills_patched   INTEGER NOT NULL DEFAULT 0,
    skills_merged    INTEGER NOT NULL DEFAULT 0,
    skills_archived  INTEGER NOT NULL DEFAULT 0,
    skills_flagged   INTEGER NOT NULL DEFAULT 0,          -- 需人工审查
    iterations       INTEGER NOT NULL DEFAULT 0,
    snapshot_path    TEXT,                                 -- tar.gz 快照路径
    started_at       INTEGER NOT NULL,
    completed_at     INTEGER
);
CREATE INDEX idx_curator_runs_started ON curator_runs(started_at);
```

---

## 三、迁移版本链一览

| 版本 | 文件 | 依赖 | 操作 | 涉及表 |
|------|------|------|------|--------|
| 0001 | add_beliefs_table | — | CREATE | beliefs, beliefs_fts |
| 0002 | add_persona_tables | 0001 | CREATE | evolution_proposals, drift_history |
| 0003 | add_skill_tables | 0002 | CREATE | skill_nodes, skill_edges, skill_usage |
| 0004 | add_approvals_table | 0003 | CREATE | approvals |
| 0005 | add_user_id_to_beliefs | 0004 | ALTER | beliefs +user_id |
| 0006 | add_audit_logs_table | 0005 | CREATE | audit_logs |
| 0007 | add_source_to_skill_nodes | 0006 | ALTER | skill_nodes +source |
| 0008 | add_conversation_date_to_beliefs | 0007 | ALTER | beliefs +conversation_date |
| 0009 | add_working_memory_tables | 0008 | CREATE | working_memory_projects, working_memory_todos |
| 0010 | add_user_model_tables | 0009 | CREATE | user_models, user_goals, user_preferences, user_predictions |
| 0011 | add_evolution_tables | 0010 | CREATE | evolution_modules, evolution_collaborations |
| 0012 | add_hard_facts_table | 0011 | CREATE | hard_facts |
| **0013** | **add_messages_and_sessions** | **0012** | **CREATE** | **messages, messages_fts, sessions** |
| **0014** | **add_decisions_and_goals** | **0013** | **CREATE** | **decisions, decision_patterns, goals** |
| **0015** | **add_jobs_table** | **0014** | **CREATE** | **jobs** |
| **0016** | **add_persona_and_identity_tables** | **0015** | **CREATE** | **personas, identities, curator_runs** |

> 加粗行（0013~0016）为本轮新增的迁移版本，用于补齐文档中描述的但实际缺失的表。

---

## 四、ChromaDB 集合设计

### 4.1 集合概览

| 集合名 | 用途 | Embedding | 元数据字段 | 预期数据量 |
|--------|------|-----------|-----------|-----------|
| long_term_memory | Agent 提炼的长期记忆 | DashScope 1536维 | source, timestamp, topic, importance | 数百条 |
| conversations | 对话记录的 embedding | DashScope 1536维 | session_id, user_id, role, timestamp | 数千至数万条 |

### 4.2 统一检索策略

**方案 A（推荐）：统一集合 + metadata 区分**
```
将所有数据存入一个集合，用 metadata.type 区分：
- "long_term" → 长期记忆
- "conversation" → 对话记录
```

**方案 B：统一检索接口**
```python
def search_memory(query, top_k=10):
    results_long = chroma_long_term.query(query, n_results=top_k)
    results_conv = chroma_conversations.query(query, n_results=top_k)
    return merge_deduplicate(results_long, results_conv)[:top_k]
```

### 4.3 去重机制

```python
similarity = cosine_similarity(new_embedding, existing_embeddings)
if max(similarity) > 0.95:
    skip()   # 视为重复，跳过写入
else:
    insert() # 写入
```

---

## 五、数据流示例

### 5.1 对话写入流程
```
用户发送消息
→ Gateway 接收 → Agent 处理
→ messages 表（SQLite）+ messages_fts（FTS5 自动同步）
→ sessions 表更新（message_count++, updated_at）
→ 对话结束 → 复盘 LLM 提取关键信息
→ beliefs 表写入（layer 判断：核心/工作/长期）
→ ChromaDB 统一集合（长期记忆 + 对话记录）
```

### 5.2 记忆检索流程
```
用户提问
→ Agent 准备上下文
→ FTS5 关键词检索：SELECT * FROM messages_fts WHERE content MATCH ?
→ ChromaDB 向量检索：collection.query(query_embedding, n_results=5)
→ beliefs 表检索：按 layer+置信度排序
→ 合并去重，按相关性排序 → 注入 context
```

### 5.3 技能提炼流程
```
任务完成 → 判断值得提炼
→ skill_nodes 表插入节点
→ skill_edges 表建立因果关系边
→ beliefs 表建立关联信念
→ curator_runs 记录 Curator 运行
```

### 5.4 人格编译流程
```
输入资料（100字~100万字）
→ personas 表插入人格档案
→ identities 表关联（人格模式）
→ drift_history 记录漂移检测
→ evolution_proposals 记录演化提议
```

---

## 六、索引总览

| 表 | 索引 | 用途 |
|----|------|------|
| beliefs | idx_beliefs_layer | 按层级查记忆 |
| beliefs | idx_beliefs_status | 按状态查信念 |
| beliefs | idx_beliefs_memory_type | 按记忆类型查 |
| beliefs | idx_beliefs_conversation_layer | 按会话+层级组合查 |
| beliefs | idx_beliefs_user_id | 按用户查信念 |
| beliefs | idx_beliefs_user_conversation | 用户+会话+层级组合查 |
| evolution_proposals | idx_ep_persona | 按人格查演化提议 |
| evolution_proposals | idx_ep_status | 按人格+状态查 |
| drift_history | idx_dh_persona | 按人格查漂移 |
| drift_history | idx_dh_created | 按人格+时间查 |
| skill_nodes | idx_skill_nodes_status | 按状态查技能 |
| skill_nodes | idx_skill_nodes_belief | 按关联信念查 |
| skill_nodes | idx_skill_nodes_name | 按名称查技能 |
| skill_nodes | idx_skill_nodes_source | 按来源查（新增） |
| skill_edges | idx_skill_edges_from | 按源节点查边 |
| skill_edges | idx_skill_edges_to | 按目标节点查边 |
| skill_usage | idx_skill_usage_name | 按技能名查使用 |
| skill_usage | idx_skill_usage_conversation | 按对话查使用 |
| approvals | idx_approvals_user_id | 按用户查审批 |
| approvals | idx_approvals_status | 按状态查审批 |
| approvals | idx_approvals_stream | 按 SSE 流查 |
| audit_logs | idx_audit_logs_timestamp | 按时间查审计 |
| working_memory_projects | idx_wmp_name | 按项目名查 |
| working_memory_projects | idx_wmp_accessed | 按访问时间查 |
| working_memory_todos | idx_todos_project_status | 按项目+状态查待办 |
| working_memory_todos | idx_todos_priority | 按优先级查 |
| user_goals | idx_user_goals_user_status | 按用户+状态查目标 |
| user_predictions | idx_user_predictions_user_created | 按用户+时间查预测 |
| evolution_modules | idx_em_name | 按名称查模块 |
| evolution_modules | idx_em_last_trigger | 按触发时间查 |
| evolution_collaborations | idx_collaboration_modules | 按模块对查协作 |
| evolution_collaborations | idx_collaboration_timestamp | 按时间查协作 |
| hard_facts | idx_hard_facts_category_sub | 按分类查事实 |
| hard_facts | idx_hard_facts_verified | 按验证状态查 |
| messages | idx_messages_session_created | 按会话查消息 |
| messages | idx_messages_user_created | 按用户查消息 |
| sessions | idx_sessions_user_updated | 按用户查会话 |
| sessions | idx_sessions_status | 按状态查活跃会话 |
| decisions | idx_decisions_user_created | 按用户查决策 |
| decisions | idx_decisions_tags | 按标签查决策 |
| decision_patterns | idx_dp_created | 查决策模式 |
| goals | idx_goals_user_status | 按用户查目标 |
| jobs | idx_jobs_active_next | 查活跃任务 |
| jobs | idx_jobs_condition | 查条件触发任务 |
| personas | idx_personas_name | 按名称查人格 |
| identities | idx_identities_mode_active | 按模式查身份 |
| curator_runs | idx_curator_runs_started | 查 Curator 运行记录 |

---

*文档结束 | ShuyuanCore 数据库 Schema v2.0 | 2026-05-29*
*包含 16 个迁移版本，共 30+ 张数据表，文档与迁移完全一致*