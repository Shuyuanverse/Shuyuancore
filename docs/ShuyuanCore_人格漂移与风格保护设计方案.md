# ShuyuanCore 人格漂移与风格保护设计方案

版本：v1.0 | 日期：2026-05-26

## 一、设计目标

1. **风格一致性**：Agent 在长期运行中保持输出风格与人格锚点一致，不随对话轮次增加而逐渐漂移。
2. **长期运行不漂移**：通过双层阈值机制（审视层 0.15、保护层 0.25）和自动校准指令，确保长期运行的偏离率 ≤ 20%。
3. **可解释性**：每次漂移检测和校准行为均可追溯、可审计，通过 `drift_history` 表记录完整历史。

## 二、核心概念

### 2.1 风格锚点（128 维）

风格锚点表示 Agent 的语言风格特征，通过以下方式生成：

- **输入**：`StyleDimensions`（7 维基础值：formality, warmth, directness, playfulness, detail_orientation, emotional_expression, pace）
- **扩展方法**：7 维 → 固定映射扩展至 128 维
  - 每个基础维度值保留
  - 每个维度生成 18 个高斯噪声变体（`np.random.seed(42)` 固定种子确保可复现）
  - 截取或填充至 128 维

### 2.2 决策锚点（256 维）

决策锚点表示 Agent 的决策逻辑和价值取向，通过以下方式生成：

- **输入**：文本内容（如 CORE.md、对话记录等）
- **生成方法**：DashScope `text-embedding-v2`（1536 维）→ PCA 降维至 256 维
- **降级方案**：若 sklearn 不可用，直接截取前 256 维

### 2.3 漂移分数计算

漂移分数通过余弦距离（Cosine Distance）计算：

```python
cosine_distance = 1 - (dot_product(v1, v2) / (norm(v1) * norm(v2)))
```

- 范围：[0, 2]，值越大表示漂移越严重
- 实际使用中通常在 [0, 0.5] 范围内

### 2.4 双层阈值

| 层级 | 阈值 | 行为 | 来源文件 |
|------|------|------|----------|
| 审视层（审查 Agent） | 0.15 | 记录轻微漂移日志，不干预 | `config/default.yaml` |
| 保护层（风格保护） | 0.25 | 强制生成校准指令，注入下一轮 prompt | `config/default.yaml` |

设计依据：
- 0.15 作为预警线：当风格开始偏离时可察觉但无需干预
- 0.25 作为强制线：偏离已显著，必须校准
- 两层形成梯度，避免一刀切，给 Agent 留出自然表达的空间

## 三、检测流程

### 3.1 主流程

```
Agent 回复生成
       │
       ▼
[1] 提取回复风格向量（fast 规则提取，不调用 LLM）
       │
       ▼
[2] 计算与风格锚点的余弦距离
       │
       ├── drift < 0.15 ──────► 正常通过
       │
       ├── 0.15 ≤ drift < 0.25 ──► 记录轻微漂移日志
       │                             不修改回复
       │
       └── drift ≥ 0.25 ──────► 生成校准指令
                                   注入下一轮 system prompt
```

### 3.2 调用入口

在 `src/persona/protection.py` 中实现 `StyleProtectionPipeline`：

```python
class StyleProtectionPipeline:
    def check_and_adjust(
        self, response_text: str, profile: PersonaProfile,
        perception: PerceptionResult = None
    ) -> ProtectionResult:
        # 1. 提取回复风格向量
        # 2. 计算余弦距离
        # 3. 双层阈值判断
        # 4. 审视 + 调整
        # 5. 返回结果
```

## 四、校准指令生成

### 4.1 指令格式

```
【风格校准】请注意在接下来的对话中保持以下风格特征：
- 正式度：{formality}（1-10）
- 温暖度：{warmth}（1-10）
- 直接度：{directness}（1-10）
- 趣味度：{playfulness}（1-10）
- 细节取向度：{detail_orientation}（1-10）
- 情感表达度：{emotional_expression}（1-10）
- 节奏度：{pace}（1-10）

当前漂移：{drift_score:.2f}（阈值：0.25）
```

### 4.2 注入方式

校准指令注入到下一轮对话的 system prompt 末尾。在 `Agent.chat_stream()` 中：

```python
if self._calibration_prompt:
    system_prompt += f"\n\n{self._calibration_prompt}"
    self._calibration_prompt = ""
```

### 4.3 连续漂移告警

连续 3 次触发强制校准（drift ≥ 0.25）→ 升级为严重漂移告警：
- 记录到 `drift_history` 表，`alert_level = "severe"`
- 在对话中输出告警信息（可选，取决于配置）

## 五、审视与调整逻辑

### 5.1 审视

结合感知层情绪和漂移维度信息，判断是否需要调整当前回复：

- 如果用户情绪为 `negative_high` 且漂移 ≥ 0.15 → 建议调整回复
- 如果漂移维度集中在某个风格维度上 → 仅在该维度上校准
- 如果感知层检测到 `pressing` 氛围 → 降低校准强度，优先保证响应速度

### 5.2 调整

轻量文本修正（不调用 LLM），规则示例：

- 漂移在 `formality` 维度偏高 → 追加"简单来说"等软化词
- 漂移在 `warmth` 维度偏低 → 追加语气词或表情符号
- 漂移在 `directness` 维度偏高 → 追加"你觉得呢？"等征求意见短语

调整后的 response 放在 `ProtectionResult.adjusted_response` 字段，若为 None 则表示不调整。

## 六、与信念场的关系

### 6.1 风格锚点存储

风格锚点和决策锚点存储在 L6 信念中：

```python
anchor_belief = Belief(
    content=json.dumps({"style_anchor": style_anchor_vector, "decision_anchor": decision_anchor_vector}),
    source="system",
    memory_type="persona_anchor",
    layer=6,
    confidence=0.99,
    base_confidence=0.99,
    metadata={"persona_id": persona_id, "anchor_version": version}
)
```

- `layer=6` 对应 L6 人格记忆层（不衰减）
- `memory_type='persona_anchor'` 标识锚点信念
- `confidence=0.99` 高置信度，不被衰减

### 6.2 漂移历史记录

漂移历史记录到 `drift_history` 表：

```sql
CREATE TABLE drift_history (
    id INTEGER PRIMARY KEY,
    persona_id VARCHAR(100) NOT NULL,
    drift_score FLOAT NOT NULL,
    alert_level VARCHAR(20) NOT NULL,
    dimensions TEXT,
    calibration_applied BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL
);
```

## 七、配置示例

```yaml
persona:
  feature_flags:
    enable_persona_system: true
    enable_style_protection: true
    enable_identity_injection: true
    enable_perception: true
    enable_self_review: true
    enable_adjustment: true
    enable_autonomous_evolution: false
    enable_inner_reaction: false
    enable_hard_fact_guard: true
  style:
    style_dimensions: 7
    anchor_dimensions: 128
    decision_anchor_dimensions: 256
    drift_threshold: 0.25
    review_drift_threshold: 0.15
    enable_proactive: false
    bound_components: true
  hard_fact:
    confidence: 0.99
    memory_type: identity
    layer: 1
    categories:
      - identity
      - knowledge_boundary
      - relation
      - bottom_line
  compiler:
    min_input_chars: 100
    max_input_chars: 1000000
    language_samples_min: 500
    language_samples_max: 1000
    embedding_model: dashscope/text-embedding-v2
    embedding_dimensions: 1536
  autonomous:
    consistency_reject_threshold: 0.3
    consistency_auto_threshold: 0.7
    trigger_days: 7
    max_proposals: 5
```

## 八、风格保护参数锁定表

以下参数为锁定参数，禁止修改（已在 `src/config.py` 中通过 `@field_validator` 保护）：

| 参数 | 值 | 说明 |
|------|-----|------|
| `drift_threshold`（保护层） | 0.25 | 超过此值强制生成校准指令 |
| `review_drift_threshold`（审视层） | 0.15 | 超过此值记录轻微漂移日志 |
| `enable_proactive` | False | 不主动干预，仅漂移时校准 |
| 风格锚点维度 | 128 维 | 风格编码基础配置 |
| 决策锚点维度 | 256 维 | 决策锚点基础配置 |
| `bound_components` | True | 风格编码器与决策锚点绑定使用 |

## 九、数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                    人格编译流程                               │
│                                                             │
│  输入文本 (100字~100万字)                                    │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────┐    ┌──────────────┐                           │
│  │ 风格编码器 │    │ 决策锚点提取器 │                          │
│  │ (7维度)   │    │ (DashScope   │                           │
│  │           │    │  → PCA降维) │                           │
│  └─────┬─────┘    └──────┬───────┘                           │
│        │                 │                                   │
│        ▼                 ▼                                   │
│  ┌──────────────────────────────────────┐                    │
│  │     生成人格档案 (PersonaProfile)     │                    │
│  │  - 风格维度 (StyleDimensions)        │                    │
│  │  - 风格锚点 (128维向量)              │                    │
│  │  - 决策锚点 (256维向量)              │                    │
│  │  - 硬事实信念ID列表                  │                    │
│  │  - 语言样本 (500-1000条)             │                    │
│  │  - 边界规则                         │                    │
│  └──────────────┬───────────────────────┘                    │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                    │
│  │    存储到 beliefs 表 + 内存缓存      │                    │
│  └──────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    风格保护流水线                             │
│                                                             │
│  每轮对话                                                   │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────┐                                       │
│  │ 感知层 (零LLM)    │                                       │
│  │ - 重复检测         │                                       │
│  │ - 氛围检测         │                                       │
│  │ - 情绪检测 (6类)   │                                       │
│  │ - 耐心衰减         │                                       │
│  └──────┬───────────┘                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐                                       │
│  │ 身份 Prompt 注入  │                                       │
│  │ + 校准指令注入     │                                       │
│  └──────┬───────────┘                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐                                       │
│  │ LLM 生成回复      │                                       │
│  └──────┬───────────┘                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐                                       │
│  │ 风格保护检测       │                                       │
│  │ 提取回复风格向量    │                                       │
│  │ 计算余弦距离       │                                       │
│  │                    │                                       │
│  │  distance < 0.15 ────► 通过                              │
│  │  0.15 ≤ d < 0.25 ──► 记录日志                            │
│  │  d ≥ 0.25 ──────────► 生成校准指令                       │
│  └──────┬───────────┘                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐                                       │
│  │ 返回回复          │                                       │
│  │ 同步：无阻塞       │                                       │
│  └──────────────────┘                                       │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐  (异步 asyncio.create_task)           │
│  │ 后台异步管线       │                                       │
│  │ - 记录漂移历史     │                                       │
│  │ - 演化提议检测     │                                       │
│  │ - 校准指令积累     │                                       │
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

## 十、已知问题与教训

1. **风格编码器与决策锚点必须绑定使用**（ECS 实战验证）：单独使用效果不好，两者互为补充。
2. **Feature Flags 默认值必须与策略对齐**：`enable_proactive=False` 是锁定参数，不能默认开启。
3. **漂移检测不调用 LLM**：纯规则提取回复风格向量，保证性能。
4. **连续漂移三次需升级告警**：防止长期累积漂移不被发现。
5. **锚点存储在 L6 不衰减**：L6 置信度衰减速率配置为 0.0，确保锚点永久有效。