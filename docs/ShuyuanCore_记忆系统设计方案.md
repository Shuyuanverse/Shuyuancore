# ShuyuanCore 记忆系统设计方案

**版本**: v1.0
**日期**: 2026-05-26
**来源**: 产品方案 v1.0 + 技术架构 v1.0 + API接口文档 v1.0 + 数据库Schema v1.0

---

## 一、设计原则

### 1.1 用户无感知
所有记忆管理操作全自动完成——写入、衰减、检索、唤醒均无需用户干预。用户只需正常对话，系统在后台完成记忆的生命周期管理。

### 1.2 信念场落地
六层记忆架构作为信念场（Belief Field）理念的具体实现：
- 每条记忆是一个**信念**（Belief），包含内容、置信度、来源、情感等元数据
- 信念随时间**自然衰减**（指数衰减函数）
- 信念之间通过**依赖关系**相互传播置信度
- 新证据可**推翻**旧信念（overthrow 机制）

### 1.3 平衡最好与不过度
- 不引入重型框架（如 FAISS、Milvus）
- SQLite FTS5 提供关键词检索，ChromaDB 提供语义检索
- jieba + SnowNLP 提供轻量级实体抽取与情感分析
- 优先使用成熟、轻量、社区活跃的 Python 库

---

## 二、数据模型

### 2.1 Belief 数据类

定义在 [src/core/interfaces.py](file:///workspace/src/core/interfaces.py#L8-L27)：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | `str` | — | 全局唯一 ID（UUID4） |
| `content` | `str` | — | 信念文本内容 |
| `source` | `str` | — | 来源（`user` / `assistant`） |
| `confidence` | `float` | `1.0` | 当前置信度（随时间衰减） |
| `base_confidence` | `float` | `1.0` | 基础置信度（衰减起点） |
| `last_accessed` | `int` | `0` | 最后访问时间（Unix 毫秒） |
| `memory_type` | `str` | `"chat"` | 记忆类型（identity / preference / fact / task / agreement / emotion / chat） |
| `layer` | `int` | `3` | 所在层（1-6） |
| `entities` | `list[str]` | `[]` | 从内容中提取的实体列表 |
| `emotion` | `float` | `0.5` | 情感极性（0=负面, 0.5=中性, 1=正面） |
| `depends_on` | `list[str]` | `[]` | 依赖的信念 ID 列表 |
| `child_belief_ids` | `list[str]` | `[]` | 子信念 ID 列表 |
| `superseded_by` | `str \| None` | `None` | 被哪个信念推翻 |
| `status` | `str` | `"active"` | 状态（active / superseded） |
| `is_composite` | `bool` | `False` | 是否为复合信念（多轮合并） |
| `timestamp` | `int` | `0` | 创建时的时间戳 |
| `metadata` | `dict[str, Any]` | `{}` | 扩展元数据 |

### 2.2 memory_type → layer 映射

定义在 [src/core/interfaces.py](file:///workspace/src/core/interfaces.py#L29-L37)：

| memory_type | 中文含义 | layer | 说明 |
|-------------|----------|-------|------|
| `identity` | 身份信息 | 1（核心记忆） | 姓名、职业、籍贯等长期不变的个人信息 |
| `preference` | 偏好 | 1（核心记忆） | 喜欢/讨厌/习惯等长期稳定的偏好 |
| `task` | 任务/目标 | 2（工作记忆） | 当前项目、任务状态、阶段性目标 |
| `agreement` | 约定/承诺 | 2（工作记忆） | 双方达成的约定、待办事项 |
| `fact` | 事实 | 3（长期历史） | 一般性事实陈述 |
| `chat` | 对话 | 3（长期历史） | 对话历史记录 |
| `emotion` | 情感 | 5（关系记忆） | 情感相关记录 |

---

## 三、数据库设计

### 3.1 beliefs 表

定义在 [src/memory/belief_store.py](file:///workspace/src/memory/belief_store.py#L60-L84) 的 `_init_tables()` 中：

```sql
CREATE TABLE IF NOT EXISTS beliefs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    confidence REAL NOT NULL DEFAULT 1.0,
    base_confidence REAL NOT NULL DEFAULT 1.0,
    last_accessed INTEGER NOT NULL DEFAULT 0,
    memory_type TEXT NOT NULL DEFAULT 'chat',
    layer INTEGER NOT NULL DEFAULT 3,
    entities TEXT DEFAULT '[]',
    emotion REAL NOT NULL DEFAULT 0.5,
    depends_on TEXT DEFAULT '[]',
    child_belief_ids TEXT DEFAULT '[]',
    superseded_by TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    is_composite INTEGER NOT NULL DEFAULT 0,
    timestamp INTEGER NOT NULL DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);
```

**字段说明**：
- `id`：UUID4 字符串
- `conversation_id`：所属会话 ID
- `entities` / `depends_on` / `child_belief_ids` / `metadata`：JSON 序列化存储
- `is_composite`：SQLite 无布尔型，使用 `0` / `1`
- `created_at` / `updated_at`：Unix 毫秒时间戳（符合规则 2.4 节）

### 3.2 FTS5 全文索引

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS beliefs_fts USING fts5(
    content,
    content='beliefs',
    content_rowid='rowid'
);
```

- 仅索引 `content` 字段
- 关联 `beliefs` 表的外部内容表（content= 语法）
- FTS5 查询失败时降级为 `LIKE` 模糊搜索

### 3.3 索引

| 索引名 | 字段 | 用途 |
|--------|------|------|
| `idx_beliefs_conversation` | `(conversation_id, layer, timestamp DESC)` | 按会话查询，分层排序 |
| `idx_beliefs_status` | `(status, confidence DESC)` | 按状态过滤，高置信度优先 |
| `idx_beliefs_layer` | `(layer, confidence DESC)` | 按层检索 |

---

## 四、置信度衰减

### 4.1 衰减公式

```
current_confidence = base_confidence × exp(-rate × elapsed_days)
```

其中：
- `elapsed_days` = `(now_ms - last_accessed_ms) / 86400000.0`
- `rate` = 对应层的衰减速率
- 结果下限：`0.1`（置信度永不归零）

### 4.2 各层衰减速率

定义在 [src/memory/decay.py](file:///workspace/src/memory/decay.py#L8-L16)：

| layer | 名称 | rate | 半衰期（约） | 说明 |
|-------|------|------|-------------|------|
| 1 | 核心记忆 | 0.0005 | 1386 天（~3.8 年） | 身份/偏好几乎不衰减 |
| 2 | 工作记忆 | 0.005 | 139 天（~4.6 月） | 任务/约定适度衰减 |
| 3 | 长期历史 | 0.01 | 69 天（~2.3 月） | 一般事实逐步遗忘 |
| 4 | 技能记忆 | 0.015 | 46 天（~1.5 月） | 技能细节较快衰减 |
| 5 | 关系记忆 | 0.01 | 69 天（~2.3 月） | 与 L3 一致 |
| 6 | 人格记忆 | 0.0 | ∞（永不衰减） | 人格锚点永久保留 |

### 4.3 实现

[src/memory/decay.py](file:///workspace/src/memory/decay.py) 中的 `current_confidence()` 函数在每次读取信念时实时计算当前置信度，不存储衰减后的值。`base_confidence` 保留原始置信度作为衰减起点。

已被推翻的信念（`status == "superseded"`）直接返回 `0.0`。

---

## 五、信念传播与推翻

### 5.1 置信度传播

定义在 [src/memory/propagation.py](file:///workspace/src/memory/propagation.py#L11-L41)：

**算法**：递归广度传播，带 visited 集合防环。

```
propagate_confidence(belief_id, delta):
    1. 读取当前信念
    2. belief.confidence += delta（钳制在 [0.0, 1.0]）
    3. belief.base_confidence = belief.confidence
    4. 递归传播到 depends_on 的信念：child_delta = delta × 0.3
    5. 递归传播到 child_belief_ids: child_delta = delta × 0.2
    6. visited 集合大小上限 1000，防止无限递归
```

**传播衰减系数**：
- 向父依赖传播：`× 0.3`（影响减弱）
- 向子信念传播：`× 0.2`（影响进一步减弱）

### 5.2 推翻机制

定义在 [src/memory/propagation.py](file:///workspace/src/memory/propagation.py#L44-L67)：

当新证据与旧信念矛盾时，执行 `overthrow`：
1. 旧信念状态改为 `"superseded"`
2. 旧信念的 `superseded_by` 指向新信念 ID
3. 新信念继承旧信念的依赖关系
4. 新信念的 `metadata` 中记录 `overthrow_reason` 和 `supersedes`

**示例**：用户先说"我叫张三"，后说"其实我不叫张三，我叫李四"：
- 信念 A：`[identity] 张三` → `status: superseded`, `superseded_by: B.id`
- 信念 B：`[identity] 李四` → `metadata: {overthrow_reason: "用户更正", supersedes: A.id}`

---

## 六、记忆写入三通道

### 6.1 规则通道（Rule-Based）

定义在 [src/memory/writer.py](file:///workspace/src/memory/writer.py#L13-L33) 的 `RuleBasedWriter`。

通过正则模式匹配自动提取关键信息，无需 LLM 参与：

| 模式 | memory_type | 基础置信度 | 示例 |
|------|-------------|-----------|------|
| `我叫/姓 \S+` | identity | 0.95 | `我叫小明` |
| `我喜欢/热爱 \S+` | preference | 0.85 | `我喜欢编程` |
| `记住: \S+` | fact | 0.9 | `记住: 项目截止日期是下周五` |
| `我的项目是 \S+` | task | 0.85 | `我的项目是AI助手` |
| `我的目标是 \S+` | agreement | 0.85 | `我的目标是学会Python` |
| `我的生日是 \S+` | fact | 0.9 | `我的生日是5月20日` |
| 共 12 条正则模式 | — | — | — |

**处理流程**：
1. 对每一条规则在输入文本中搜索
2. 匹配成功 → 调用 `IEntityExtractor` 抽取实体
3. 调用 `IEmotionAnalyzer` 分析情感
4. 根据 `_LAYER_MAP` 确定 layer
5. 写入 `beliefs` 表 + `beliefs_fts` 索引

### 6.2 手动通道（Manual）

定义在 [src/memory/writer.py](file:///workspace/src/memory/writer.py#L86-L137) 的 `ManualMemoryWriter`。

用户通过 `记住: ` 或 `Remember: ` 前缀主动写入记忆。

**格式**：
- 单条：`记住: 内容`
- 多条：`记住: 内容1，内容2; 内容3`

**特点**：
- 固定置信度 `0.9`
- 固定 memory_type 为 `"fact"`
- 固定 layer 为 `3`

### 6.3 AI 推理通道（Background）

定义在 [src/memory/writer.py](file:///workspace/src/memory/writer.py#L143-L188) 的 `AiInferenceWriter`。

LLM 输出的内容经过重要性评估后选择性写入：
- `importance >= 0.6` 阈值时才写入（可配置 `ai_importance_threshold`）
- 置信度 = importance 值
- layer = 3（长期历史）
- 支持附带 metadata

### 6.4 复合信念（Composite Belief）

定义在 [src/memory/writer.py](file:///workspace/src/memory/writer.py#L191-L258) 的 `CompositeBeliefDetector`。

**触发条件**：
- 连续对话轮次 >= 3 轮
- 合并文本长度 >= 100 字符
- 跨轮实体数量 >= 3 个

**产出**：
- `is_composite = True`
- `confidence = 0.7`（可配置 `composite_confidence`）
- content = 合并文本的前 500 字符
- metadata 记录 `turn_count`、`emotion_range`、`combined_length`

---

## 七、多维唤醒

### 7.1 唤醒分数公式

定义在 [src/memory/wake.py](file:///workspace/src/memory/wake.py#L44-L81) 的 `wake_score()`：

```
wake_score = (semantic × 0.5) + (keyword × 0.2) + (entity × 0.15) + (emotion × 0.1)
最终分数 = raw_score × 当前置信度
```

| 维度 | 权重 | 计算方法 |
|------|------|----------|
| 语义相似度（semantic） | 0.5 | Jaccard 相似度（token 集合交集/并集） |
| FTS5 关键词（keyword） | 0.2 | FTS5 rank 分数经 sigmoid 归一化 |
| 实体重叠（entity） | 0.15 | 用户消息实体与信念实体的 Jaccard |
| 情感匹配（emotion） | 0.1 | 1.0 - |用户情感 - 信念情感|，下限 0.5 |

### 7.2 唤醒就绪度

定义在 [src/memory/wake.py](file:///workspace/src/memory/wake.py#L94-L110) 的 `wake_readiness()`：

根据用户消息中的技术关键词密度判断是否需要唤醒相关记忆：

| 技术词密度 | 基础就绪度 |
|-----------|-----------|
| > 0.3 | 0.6 |
| > 0.15 | 0.4 |
| 其他 | 0.2 |

加上连续技术轮次的动量加成：`min(consecutive_tech_rounds × 0.1, 1.0)`

技术关键词包括：python, javascript, rust, go, java, typescript, react, docker, kubernetes, git, linux, api, sql, database, server, deploy, config, debug, test, 以及对应中文词。

### 7.3 频率控制

定义在 [src/memory/wake.py](file:///workspace/src/memory/wake.py#L113-L147) 的 `WakeFrequencyTracker`：

| 控制项 | 默认值 | 说明 |
|--------|--------|------|
| 单信念每小时唤醒上限 | 5 次 | `should_suppress()` 判断 |
| 会话窗口 | 300000ms（5 分钟） | 清空计数 |
| 信念跟踪窗口 | 3600000ms（1 小时） | 计数窗口 |

---

## 八、抽象接口

### 8.1 IEntityExtractor

定义在 [src/memory/interfaces.py](file:///workspace/src/memory/interfaces.py#L6-L9)：

```python
class IEntityExtractor(Protocol):
    def extract(self, text: str) -> list[str]: ...
```

### 8.2 IEmotionAnalyzer

```python
class IEmotionAnalyzer(Protocol):
    def analyze(self, text: str) -> float: ...
```

### 8.3 默认实现（W1）

定义在 [src/memory/extractor.py](file:///workspace/src/memory/extractor.py)：

| 接口 | 实现类 | 后端 | 说明 |
|------|--------|------|------|
| `IEntityExtractor` | `JiebaEntityExtractor` | jieba.posseg | 抽取名词性实体（n/nr/ns 等词性） |
| `IEmotionAnalyzer` | `SnowNlpEmotionAnalyzer` | SnowNLP.sentiments | 返回 [0, 1] 情感分数 |
| `IEntityExtractor` | `CompositeExtractor` | 多抽取器组合 | 去重合并多个抽取器结果 |

**依赖可选**：jieba / snownlp 未安装时返回空列表 / 0.5，不中断系统运行。

---

## 九、与现有模块集成

### 9.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    Agent (Phase 3)                    │
│  ┌──────────────────────────────────────────────────┐│
│  │  orchestrator.py │ agent.py │ conversation.py   ││
│  └────────┬──────────────────────────────┬──────────┘│
│           │ IBeliefStore / IReader       │            │
│           ▼                              ▼            │
│  ┌────────────────┐          ┌──────────────────┐     │
│  │  RuleBasedWriter │          │  BeliefReader    │     │
│  │  ManualMemoryWriter│        │  (IReader impl)  │     │
│  │  AiInferenceWriter│         └──────────────────┘     │
│  │  CompositeDetector│                                  │
│  └────────┬──────────┘                                  │
│           │                                              │
│           ▼                                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │          PersistentBeliefStore (IBeliefStore)     │   │
│  │  ┌─────────────┐  ┌──────────┐  ┌─────────────┐ │   │
│  │  │  beliefs 表  │  │ FTS5 索引│  │ decay.py    │ │   │
│  │  │ (SQLite)    │  │          │  │ propagation │ │   │
│  │  └─────────────┘  └──────────┘  └─────────────┘ │   │
│  └──────────────────────────────────────────────────┘   │
│           │                                              │
│           ▼                                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │   W1: JiebaEntityExtractor                      │   │
│  │      SnowNlpEmotionAnalyzer                     │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 9.2 PersistentBeliefStore

定义在 [src/memory/belief_store.py](file:///workspace/src/memory/belief_store.py#L41-L353)。

实现 `IBeliefStore` 接口：
- `add()` — 写入信念 + FTS5 同步索引
- `get()` — 按会话查询，按 layer 升序、时间戳降序排列
- `get_by_id()` — 按 ID 精确查询
- `update()` — 更新信念 + 重建 FTS5 索引
- `clear()` — 清除整个会话的信念 + FTS5 索引
- `remove()` — 删除单条信念 + FTS5 索引
- `search_similar()` — FTS5 全文检索（降级 LIKE 搜索）
- `propagate_confidence()` — 委托 propagation 模块
- `overthrow()` — 委托 propagation 模块
- `close()` — 关闭连接

**数据库连接初始化**：PRAGMA journal_mode=WAL, foreign_keys=ON, busy_timeout=5000（符合规则 2.4 节）。

### 9.3 BeliefReader

定义在 [src/memory/reader.py](file:///workspace/src/memory/reader.py#L21-L106)。

实现 `IReader` 接口，用于 Agent 上下文准备时读取记忆：

**排序策略**（按优先级）：
1. L1 核心记忆（identity/preference）：权重 `confidence × 1.0`
2. L2 工作记忆（task/agreement）：权重 `confidence × 0.9`
3. 语义检索命中的 L3+ 信念：权重 `confidence × relevance`
4. 其余 L3+ 信念：权重 `confidence × 0.5`

**Token 限制**：`max_tokens` 参数（默认 4000）控制注入上下文的记忆总量。

**输出格式**：`{"role": "system/assistant", "content": "[Layer][Type]: content"}`

### 9.4 Agent 集成

Agent 在以下时机调用记忆模块：
1. **上下文准备**（`_prepare_context`）：调用 `BeliefReader.read()` 注入相关记忆
2. **用户消息处理**：调用 `RuleBasedWriter.process()` 和 `ManualMemoryWriter.process()` 提取信念
3. **LLM 响应后**：调用 `AiInferenceWriter.process_llm_output()` 评估写入
4. **多轮对话**：调用 `CompositeBeliefDetector.process_multi_turn()` 合并复合信念

---

## 十、配置项

从 `config/default.yaml` 读取的记忆相关配置（[config/default.yaml](file:///workspace/config/default.yaml#L32-L49)）：

```yaml
memory:
  decay_rates:
    layer_1: 0.0005
    layer_2: 0.005
    layer_3: 0.01
    layer_4: 0.015
    layer_5: 0.01
    layer_6: 0.0
  confidence_floor: 0.1
  wake_threshold: 0.6
  readiness_threshold: 0.5
  max_wakeups_per_belief_per_day: 2
  max_wakeups_per_session: 5
  cooldown_base_minutes: 30
  ai_importance_threshold: 0.6
  ai_importance_working: 0.5
  composite_min_rounds: 3
  composite_confidence: 0.8
```

| 配置项 | 默认值 | 说明 | 关联模块 |
|--------|--------|------|----------|
| `decay_rates.layer_1` | 0.0005 | L1 衰减速率 | decay.py |
| `decay_rates.layer_2` | 0.005 | L2 衰减速率 | decay.py |
| `decay_rates.layer_3` | 0.01 | L3 衰减速率 | decay.py |
| `decay_rates.layer_4` | 0.015 | L4 衰减速率 | decay.py |
| `decay_rates.layer_5` | 0.01 | L5 衰减速率 | decay.py |
| `decay_rates.layer_6` | 0.0 | L6 衰减速率（永不衰减） | decay.py |
| `confidence_floor` | 0.1 | 置信度地板值 | decay.py |
| `wake_threshold` | 0.6 | 唤醒分数阈值 | wake.py |
| `readiness_threshold` | 0.5 | 唤醒就绪度阈值 | wake.py |
| `max_wakeups_per_belief_per_day` | 2 | 单信念每天最大唤醒次数 | wake.py |
| `max_wakeups_per_session` | 5 | 单会话最大唤醒次数 | wake.py |
| `cooldown_base_minutes` | 30 | 冷却基础时间（分钟） | wake.py |
| `ai_importance_threshold` | 0.6 | AI 推理写入重要性阈值 | writer.py |
| `ai_importance_working` | 0.5 | AI 推理写入工作记忆阈值 | writer.py |
| `composite_min_rounds` | 3 | 复合信念最少轮次 | writer.py |
| `composite_confidence` | 0.8 | 复合信念初始置信度 | writer.py |