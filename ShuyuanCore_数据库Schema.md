# ShuyuanCore 数据库 Schema
版本：v1.0 | 日期：2026-05-26
## 一、数据库选型
### 主数据库：SQLite + WAL模式
- 单文件部署（data/state.db），零配置
- WAL模式保证写入不阻塞读取
- FTS5支持全文检索
### 向量数据库：ChromaDB PersistentClient
- 持久化存储（data/chroma/）
- 自动embedding（DashScope text-embedding-v2，1536维）
- 支持metadata过滤
## 二、SQLite 表结构
### 2.1 消息表
**// sql**-- messages: 所有对话消息
CREATE TABLE messages (
id INTEGER PRIMARY KEY AUTOINCREMENT,
session_id TEXT NOT NULL,
user_id TEXT NOT NULL,
platform TEXT NOT NULL DEFAULT 'cli', -- cli/telegram/wechat/feishu/...
role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
content TEXT NOT NULL,
tokens_used INTEGER DEFAULT 0, -- 本次消耗的token数
tool_calls TEXT, -- JSON数组：[{"name": "terminal", "params": "ls"}]
metadata TEXT, -- JSON：{"model": "qwen-max", "persona_id": null}
temperature REAL DEFAULT 0.7,
created_at INTEGER NOT NULL -- unix timestamp (ms)
);
-- 核心索引
CREATE INDEX idx_messages_session ON messages(session_id, created_at DESC);
CREATE INDEX idx_messages_user ON messages(user_id, created_at DESC);
-- messages_fts: FTS5全文检索（虚拟表，自动同步）
CREATE VIRTUAL TABLE messages_fts USING fts5(
content,
content='messages',
content_rowid='id'
);
-- FTS5触发器：自动同步
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
### 2.2 会话表
**// sql**-- sessions: 对话会话
CREATE TABLE sessions (
id TEXT PRIMARY KEY, -- UUID
user_id TEXT NOT NULL,
platform TEXT NOT NULL DEFAULT 'cli',
title TEXT, -- 会话标题（LLM自动总结或用户手动设置）
title_source TEXT DEFAULT 'auto' CHECK(title_source IN ('auto', 'manual')),
identity_id TEXT DEFAULT 'default', -- 当前身份ID
current_model TEXT DEFAULT 'dashscope/qwen-max',
message_count INTEGER DEFAULT 0,
total_tokens INTEGER DEFAULT 0,
status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted')),
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL,
archived_at INTEGER
);
CREATE INDEX idx_sessions_user ON sessions(user_id, updated_at DESC);
CREATE INDEX idx_sessions_status ON sessions(status, updated_at DESC);
### 2.3 决策记录表
**// sql**-- decisions: 决策上下文记录（L5关系记忆）
CREATE TABLE decisions (
id TEXT PRIMARY KEY,
user_id TEXT NOT NULL,
session_id TEXT,
context TEXT NOT NULL, -- "当时在做什么"
options TEXT NOT NULL, -- JSON数组：["方案A", "方案B", "方案C"]
chosen TEXT NOT NULL, -- 最终选择
reason TEXT NOT NULL, -- 为什么选这个
state_at_time TEXT, -- 当时的状态（JSON）
verified TEXT DEFAULT 'pending' CHECK(verified IN ('correct', 'wrong', 'pending', 'unknown')),
tags TEXT, -- JSON标签：["架构决策", "技术选型"]
created_at INTEGER NOT NULL
);
CREATE INDEX idx_decisions_user ON decisions(user_id, created_at DESC);
CREATE INDEX idx_decisions_tags ON decisions(tags) WHERE tags IS NOT NULL;
### 2.4 决策模式表
**// sql**-- decision_patterns: 从决策中提取的模式
CREATE TABLE decision_patterns (
id INTEGER PRIMARY KEY AUTOINCREMENT,
pattern TEXT NOT NULL, -- "高压下偏好简化方案"
confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
sample_count INTEGER DEFAULT 1,
last_used_at INTEGER,
created_at INTEGER NOT NULL
);
CREATE INDEX idx_dp_user ON decision_patterns(created_at DESC);
### 2.5 定时任务表
**// sql**-- jobs: 定时任务（cron/条件触发/任务链）
CREATE TABLE jobs (
id TEXT PRIMARY KEY,
schedule TEXT NOT NULL, -- cron表达式或自然语言解析结果
cron_parsed TEXT, -- 解析后的标准cron（如 "0 8 * * *"）
prompt TEXT NOT NULL, -- 执行提示
skill TEXT, -- 预加载技能名
deliver_to TEXT, -- JSON数组：["telegram", "wechat"]，null=当前会话
deliver_mode TEXT DEFAULT 'current' CHECK(deliver_mode IN ('current', 'all', 'platforms')),
is_active INTEGER DEFAULT 1 CHECK(is_active IN (0, 1)),
execution_count INTEGER DEFAULT 0,
last_run_at INTEGER,
next_run_at INTEGER NOT NULL,
chain_next_job_id TEXT, -- 任务链：下一步任务ID
condition_trigger TEXT, -- JSON条件触发配置：{"type": "cpu_usage", "threshold": 80, "operator": ">"}
condition_state TEXT DEFAULT 'standby' CHECK(condition_state IN ('standby', 'triggered', 'cooldown')),
no_agent INTEGER DEFAULT 0 CHECK(no_agent IN (0, 1)), -- 1=确定性操作不消耗LLM
timeout_seconds INTEGER DEFAULT 300,
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL,
FOREIGN KEY (chain_next_job_id) REFERENCES jobs(id)
);
CREATE INDEX idx_jobs_active ON jobs(is_active, next_run_at);
CREATE INDEX idx_jobs_condition ON jobs(condition_state) WHERE condition_trigger IS NOT NULL;
### 2.6 目标追踪表
**// sql**-- goals: 跨轮次持久目标
CREATE TABLE goals (
id TEXT PRIMARY KEY,
user_id TEXT NOT NULL,
session_id TEXT, -- null=全局目标
description TEXT NOT NULL,
status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'abandoned')),
progress REAL DEFAULT 0 CHECK(progress >= 0 AND progress <= 100),
dependencies TEXT, -- JSON数组：["goal_001"]，依赖的其他目标
parent_goal_id TEXT, -- 父目标ID（子目标）
auto_created INTEGER DEFAULT 0, -- 1=Agent自动创建（/goal命令）
created_at INTEGER NOT NULL,
completed_at INTEGER,
FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
);
CREATE INDEX idx_goals_user ON goals(user_id, status, created_at DESC);
### 2.7 审计日志表
**// sql**-- audit_log: 行为审计（所有工具调用和敏感操作）
CREATE TABLE audit_log (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id TEXT NOT NULL,
action TEXT NOT NULL, -- "tool_call", "approve", "deny", "model_switch"
target TEXT, -- 操作对象："terminal", "apr_001"
details TEXT, -- JSON详情：{"command": "rm -rf", "params": {}}
ip_address TEXT,
platform TEXT DEFAULT 'cli',
result TEXT DEFAULT 'success', -- success/failure/pending
error_message TEXT,
created_at INTEGER NOT NULL
);
CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_log(action, created_at DESC);
### 2.8 审批记录表
**// sql**-- approvals: 危险命令审批记录
CREATE TABLE approvals (
id TEXT PRIMARY KEY, -- apr_001
tool_name TEXT NOT NULL,
command TEXT NOT NULL,
requested_by TEXT NOT NULL,
approved_by TEXT,
status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'denied', 'expired')),
expires_at INTEGER NOT NULL, -- 审批超时时间（默认15分钟）
result TEXT, -- 执行结果
executed_at INTEGER,
created_at INTEGER NOT NULL
);
CREATE INDEX idx_approvals_status ON approvals(status, created_at DESC);
### 2.9 模块演化表
**// sql**-- evolution_modules: 自演化产生的模块
CREATE TABLE evolution_modules (
id TEXT PRIMARY KEY,
name TEXT NOT NULL,
trigger_count INTEGER DEFAULT 0,
trigger_window_start INTEGER NOT NULL, -- 首次触发时间
status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived')),
last_activated_at INTEGER,
archived_at INTEGER,
created_at INTEGER NOT NULL
);
CREATE INDEX idx_evolution_status ON evolution_modules(status, created_at DESC);
### 2.10 演化历史表
**// sql**-- evolution_history: 模块演化操作记录
CREATE TABLE evolution_history (
id INTEGER PRIMARY KEY AUTOINCREMENT,
type TEXT NOT NULL CHECK(type IN ('born', 'fused', 'archived', 'activated')),
module TEXT, -- 主模块名
modules TEXT, -- fuser操作：["code_reasoning", "arch_analysis"]
result TEXT, -- fuser操作产生的新模块名
trigger_count INTEGER, -- born操作时：触发次数
description TEXT,
timestamp INTEGER NOT NULL
);
CREATE INDEX idx_ev_history ON evolution_history(timestamp DESC);
### 2.11 人格档案表
**// sql**-- personas: 编译的人格档案
CREATE TABLE personas (
id TEXT PRIMARY KEY,
name TEXT NOT NULL,
description TEXT,
profile TEXT NOT NULL, -- JSON：完整人格档案
style_vector TEXT, -- JSON：256维风格向量
anchor_vector TEXT, -- JSON：256维决策锚点向量
created_from TEXT, -- 来源："compile" | "import" | "manual"
source_text_hash TEXT, -- 输入文本的hash（用于检测重复编译）
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL
);
CREATE INDEX idx_personas_name ON personas(name);
### 2.12 身份表
**// sql**-- identities: 多身份管理（双维度身份矩阵）
CREATE TABLE identities (
id TEXT PRIMARY KEY,
name TEXT NOT NULL,
mode TEXT NOT NULL CHECK(mode IN ('general', 'persona')), -- general=通用模式, persona=人格模式
type TEXT DEFAULT 'work' CHECK(type IN ('work', 'study', 'research', 'custom')), -- 通用模式子类型
persona_id TEXT, -- 人格模式时关联的人格ID（NULL=通用模式）
profile_path TEXT, -- 身份数据存储路径：data/identities/work/等
memory_path TEXT, -- L1核心记忆路径：data/identities/work/MEMORY.md
is_active INTEGER DEFAULT 0, -- 1=当前激活的身份
sort_order INTEGER DEFAULT 0,
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL,
FOREIGN KEY (persona_id) REFERENCES personas(id)
);
CREATE INDEX idx_identities_mode ON identities(mode, is_active);
### 2.13 技能表
**// sql**-- skills: 技能元数据
CREATE TABLE skills (
id TEXT PRIMARY KEY,
name TEXT NOT NULL UNIQUE,
description TEXT,
version TEXT DEFAULT '1.0',
status TEXT DEFAULT 'active' CHECK(status IN ('active', 'stale', 'archived', 'pinned')),
type TEXT DEFAULT 'agent' CHECK(type IN ('agent', 'manual', 'hub')), -- 来源标记
usage_count INTEGER DEFAULT 0,
last_used_at INTEGER,
file_path TEXT NOT NULL, -- 技能文件路径：data/skills/skill-name.md
parent_skill TEXT, -- 合并/归档时的关联
expires_at INTEGER, -- 过时标记的时间
created_at INTEGER NOT NULL,
updated_at INTEGER NOT NULL,
FOREIGN KEY (parent_skill) REFERENCES skills(id)
);
CREATE INDEX idx_skills_status ON skills(status, updated_at DESC);
CREATE INDEX idx_skills_type ON skills(type);
### 2.14 Curator运行记录表
**// sql**-- curator_runs: Curator每次运行的快照
CREATE TABLE curator_runs (
id INTEGER PRIMARY KEY AUTOINCREMENT,
phase TEXT NOT NULL CHECK(phase IN ('phase1', 'phase2')),
skills_examined INTEGER DEFAULT 0,
skills_retained INTEGER DEFAULT 0,
skills_patched INTEGER DEFAULT 0,
skills_merged INTEGER DEFAULT 0,
skills_archived INTEGER DEFAULT 0,
skills_flagged INTEGER DEFAULT 0, -- "需人工审查"标记数
iterations INTEGER DEFAULT 0, -- phase2实际迭代次数
snapshot_path TEXT, -- tar.gz快照路径
started_at INTEGER NOT NULL,
completed_at INTEGER
);
CREATE INDEX idx_curator_runs ON curator_runs(started_at DESC);
### 2.15 漂移检测记录表
**// sql**-- drift_records: 风格漂移检测历史
CREATE TABLE drift_records (
id INTEGER PRIMARY KEY AUTOINCREMENT,
persona_id TEXT,
drift_score REAL NOT NULL,
action TEXT, -- "none", "warn", "calibrate", "severe"
details TEXT, -- JSON：{校准前后的风格向量差异}
created_at INTEGER NOT NULL
);
CREATE INDEX idx_drift_persona ON drift_records(persona_id, created_at DESC);
## 三、ChromaDB 集合设计
### 3.1 集合概览
|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **集合名** | **用途** | **Embedding** | **元数据字段** | **预期数据量** |
| long\_term\_memory | Agent提炼的长期记忆 | DashScope 1536维 | source, timestamp, topic, importance | 数百条 |
| conversations | 对话记录的embedding | DashScope 1536维 | session\_id, user\_id, role, timestamp | 数千至数万条 |
### 3.2 统一检索策略
⚠️ **ECS实战教训**：ShuyuanVerse的conversations集合与long\_term\_memory集合分离，search\_long\_term只检索long\_term\_memory集合，导致对话记录检索入口缺失。
**ShuyuanCore解决方案**：
方案A（推荐）：统一集合 + metadata区分
```
将所有数据存入一个集合，用metadata.type区分：
- "long_term" → 长期记忆
- "conversation" → 对话记录
```
方案B：统一检索接口
```python
def search_memory(query, top_k=10):
    """统一检索：同时搜索两个集合"""
    results_long = chroma_long_term.query(query, n_results=top_k)
    results_conv = chroma_conversations.query(query, n_results=top_k)
    return merge_deduplicate(results_long, results_conv)[:top_k]
```
### 3.3 去重机制
写入前检查：
```python
# 计算新embedding与已有记录的余弦相似度
similarity = cosine_similarity(new_embedding, existing_embeddings)
if max(similarity) > 0.95:
    skip()  # 视为重复，跳过写入
else:
    insert()  # 写入
```
### 3.4 写入流程
1. 对话结束 → 复盘LLM提取关键信息
2. DashScope API生成embedding（1536维）
3. 去重检查（相似度>0.95视为重复）
4. 写入ChromaDB（统一集合，metadata区分类型）
5. 同时写入SQLite messages表 + FTS5索引
## 四、数据流示例
### 4.1 对话写入流程
用户发送消息
→ Gateway接收 → Agent处理
→ messages表（SQLite）+ messages\_fts（FTS5自动同步）
→ sessions表更新（message\_count++, updated\_at）
→ 对话结束 → 复盘LLM提取关键信息
→ ChromaDB统一集合（长期记忆 + 对话记录，metadata.type区分）
→ 去重检查（相似度>0.95跳过）
### 4.2 记忆检索流程
用户提问
→ Agent准备上下文
→ FTS5关键词检索：SELECT * FROM messages_fts WHERE content MATCH ?
→ ChromaDB向量检索：collection.query(query_embedding, n_results=5)
→ 合并去重，按相关性排序
→ 注入context
### 4.3 技能提炼流程
任务完成 → 判断值得提炼
→ skills表插入元数据
→ data/skills/ 写入SKILL.md文件
→ data/graph/skill\_graph.json 更新因果图
→ curator\_runs 记录Curator运行（7天周期）
### 4.4 人格编译流程
输入资料（100字~100万字）
→ personas表插入档案
→ drift\_records 记录漂移检测
→ identities表关联（如果是人格模式身份）
## 五、Schema版本管理
```python
# schema_version: 记录数据库schema版本，支持迁移
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
applied_at INTEGER NOT NULL
);
```
## 六、索引总览
|  |  |  |
| --- | --- | --- |
| **表** | **索引** | **用途** |
| messages | idx\_messages\_session | 按会话查消息（时间倒序） |
| messages | idx\_messages\_user | 按用户查消息 |
| messages | messages\_fts(FTS5虚拟表) | 全文检索 |
| sessions | idx\_sessions\_user | 按用户查会话 |
| sessions | idx\_sessions\_status | 按状态查活跃会话 |
| decisions | idx\_decisions\_user | 按用户查决策记录 |
| decisions | idx\_decisions\_tags | 按标签查决策 |
| decision\_patterns | idx\_dp\_user | 查决策模式 |
| jobs | idx\_jobs\_active | 查活跃任务+下次执行时间 |
| jobs | idx\_jobs\_condition | 查条件触发任务 |
| goals | idx\_goals\_user | 按用户查目标 |
| audit\_log | idx\_audit\_user | 按用户查审计日志 |
| audit\_log | idx\_audit\_action | 按操作类型查审计 |
| approvals | idx\_approvals\_status | 按状态查审批 |
| evolution\_modules | idx\_evolution\_status | 查活跃/归档模块 |
| evolution\_history | idx\_ev\_history | 查演化历史 |
| personas | idx\_personas\_name | 按名称查人格 |
| identities | idx\_identities\_mode | 按模式查身份 |
| skills | idx\_skills\_status | 按状态查技能 |
| skills | idx\_skills\_type | 按来源类型查技能 |
| curator\_runs | idx\_curator\_runs | 查Curator运行记录 |
| drift\_records | idx\_drift\_persona | 按人格查漂移记录 |
*文档结束 | ShuyuanCore 数据库 Schema v1.0 | 2026-05-26*
本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
