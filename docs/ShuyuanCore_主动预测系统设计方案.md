# ShuyuanCore 主动预测系统设计方案

> **状态说明 / Status Note**
> 本文档为设计初稿。当前实现进度参见 README.md 及代码注释。
> - cron 模块：已实现（src/cron/）
> - evolution 模块：部分实现（module_manager 可用）
> - prediction 模块：已实现（src/prediction/）
> - 安全子系统：9/12 模块已实现（auth/confirm/encryption/network_isolation/output_filter/privacy/rate_limit/rollback/session_isolation）
> - 网关适配器：已实现 BaseAdapter/Gateway/API/CLI/OpenAIProxy/WechatWork，其余待社区贡献

## 1. 概述

主动预测系统赋予 ShuyuanCore 在对话空闲期主动发起交互的能力。系统通过分析对话上下文和用户行为模式，预测用户可能的下一步需求，并在适当时机主动提供帮助。

### 1.1 设计目标

- **主动服务**：在用户空闲时根据上下文主动提供有价值的建议
- **精准触发**：避免过度主动导致的骚扰，只在高置信度场景下触发
- **可配置性**：主动行为完全通过配置控制，可随时关闭
- **反馈闭环**：通过用户反馈持续优化主动触发策略

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 主循环                               │
│                                                              │
│  用户消息 → 处理回复 → 空闲检测 → (主动触发判断) → 等待下一轮 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
            ┌────────────┐  ┌──────────┐
            │  被动模式   │  │ 主动模式  │
            │ (回复用户)  │  │ (主动提议) │
            └────────────┘  └────┬─────┘
                                 │
                                 ▼
            ┌─────────────────────────────────────┐
            │          Predictor (预测器)            │
            │                                      │
            │  1. 空闲检测 → 超时判断               │
            │  2. 上下文分析 → 意图预测              │
            │  3. 置信度评估 → 阈值过滤              │
            │  4. 主动提议 → 输出                    │
            └─────────────────────────────────────┘
                                 │
                                 ▼
            ┌─────────────────────────────────────┐
            │          Feedback (反馈收集器)        │
            │                                      │
            │  用户接受/拒绝 → 统计 → 优化触发策略  │
            └─────────────────────────────────────┘
```

### 2.1 交互流程

```
用户: (...沉默 30 秒...)
                    ↓
Predictor: 检测到空闲超时
                    ↓
          分析最后一段对话上下文
                    ↓
          置信度评估 (≥ 0.7?)
              ├── 否 → 静默等待
              └── 是 → 生成主动提议
                         ↓
               Agent: "我注意到您正在分析数据，需要我帮您生成可视化图表吗？"
                         ↓
              用户: "好的" / "不用"
                         ↓
              Feedback: 记录反馈，更新统计
```

---

## 3. 子模块设计

### 3.1 预测器（Predictor）

预测器负责空闲检测和主动触发决策。

**核心逻辑：**

```
1. 每轮对话结束后启动空闲计时器
2. 超时后检查条件：
   a. 当前对话中主动提醒次数 < max_idle_checks_per_conversation
   b. 根据对话上下文计算预测置信度
   c. 置信度 ≥ confidence_threshold
3. 满足所有条件 → 生成主动提议
4. 不满足 → 继续等待或静默
```

**置信度评估维度（待实现）：**

| 维度 | 权重 | 说明 |
|------|------|------|
| 上下文明确度 | 0.4 | 用户是否明确表达了需求但未完成 |
| 情绪信号 | 0.3 | 用户是否表现出困惑或等待 |
| 行为模式 | 0.2 | 用户历史上的空闲期行为模式 |
| 任务阶段 | 0.1 | 当前任务是否处于关键节点 |

### 3.2 反馈收集器（Feedback）

收集用户对主动提议的反馈，用于优化触发策略。

**反馈类型：**

| 反馈 | 含义 | 处理方式 |
|------|------|---------|
| 接受 | 提议有用 | 增加该场景权重 |
| 拒绝 | 提议不相关 | 减少该场景权重 |
| 忽略 | 用户未回应 | 降低置信度阈值 |

**统计指标：**

- 主动提议次数（proactive_count）
- 接受率（acceptance_rate = 接受 / 总提议）
- 单对话最大重复拒绝次数
- 场景-意图命中率

---

## 4. 配置项

```yaml
prediction:
  enable_proactive: false               # 主动发起总开关
  idle_timeout_seconds: 30              # 空闲超时（秒）
  confidence_threshold: 0.7            # 预测置信度阈值
  max_idle_checks_per_conversation: 3  # 单次对话最大主动提醒次数
  feedback_loop: true                   # 反馈闭环开关
```

### 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_proactive | 是否允许 Agent 主动发起对话 | false |
| idle_timeout_seconds | 用户无操作 N 秒后触发主动判断 | 30 |
| confidence_threshold | 置信度 ≥ 阈值才主动提议 | 0.7 |
| max_idle_checks_per_conversation | 单次对话最多主动提醒次数 | 3 |
| feedback_loop | 是否收集用户反馈优化预测 | true |

---

## 5. 与系统的集成

### 与 Agent 主循环的集成

```python
async def _process_message(self, message):
    # 1. 处理用户消息
    response = await self._generate_response(message)

    # 2. 检查主动预测
    if self.config.prediction.enable_proactive:
        proactive_action = await self.predictor.check_idle(
            conversation_context=self.context,
            idle_timeout=self.config.prediction.idle_timeout_seconds,
            confidence_threshold=self.config.prediction.confidence_threshold,
        )
        if proactive_action:
            response += f"\n\n💡 {proactive_action.suggestion}"

    return response
```

### 与反馈系统的集成

```python
async def record_feedback(self, prediction_id, accepted, user_response):
    feedback = PredictionFeedback(
        prediction_id=prediction_id,
        accepted=accepted,
        user_response=user_response,
        context_snapshot=self.context.snapshot(),
    )
    await self.feedback_collector.record(feedback)

    # 更新置信度模型
    if not accepted:
        self.predictor.lower_confidence(self.context.task_type)
```

---

## 6. 主动提议生成策略

### 6.1 触发时机

| 场景 | 示例 | 触发优先级 |
|------|------|-----------|
| 未完成的任务 | 用户询问了数据分析但未要求生成图表 | 高 |
| 可优化的结果 | Agent 生成了文本但未格式化 | 中 |
| 关联建议 | 用户在处理代码，可建议运行测试 | 中 |
| 信息补充 | 用户查询了天气，可建议添加提醒 | 低 |

### 6.2 防骚扰策略

- 单次对话最大主动提醒次数：3 次（可配置）
- 连续被拒绝后，同一场景不再触发
- 主动提醒之间至少间隔 2 次正常对话
- 用户可随时通过对话关闭主动功能

---

## 7. 数据持久化

预测系统的反馈数据通过 SQLite 持久化：

```sql
CREATE TABLE IF NOT EXISTS prediction_feedback (
    id              TEXT PRIMARY KEY,
    prediction_id   TEXT NOT NULL,
    accepted        INTEGER NOT NULL,
    user_response   TEXT DEFAULT '',
    context_type    TEXT DEFAULT '',
    task_type       TEXT DEFAULT '',
    confidence      REAL NOT NULL,
    timestamp       REAL NOT NULL
);
```

---

## 8. 待实现功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Predictor 空闲检测 | 🔴 高 | 超时检测和空闲状态管理 |
| 上下文意图预测 | 🔴 高 | 根据对话历史预测用户意图 |
| 置信度评估模型 | 🔴 高 | 多维置信度计算引擎 |
| 主动提议生成 | 🟡 中 | 根据预测结果生成自然语言提议 |
| 反馈收集 | 🟡 中 | 用户接受/拒绝反馈的收集和记录 |
| 自适应优化 | 🟢 低 | 根据历史反馈优化触发策略 |

---

## 9. 安全与边界

- 主动提议仅限信息提供和建议，不允许执行任何写操作
- 用户可通过对话或配置随时完全关闭主动功能
- 置信度阈值设置下限（最低 0.5），防止低质量打扰
- 所有主动提议记录审计日志