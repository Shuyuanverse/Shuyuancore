# ShuyuanCore 定时任务系统设计方案

## 1. 概述

定时任务系统（Cron）为 ShuyuanCore 提供轻量级、基于条件触发的任务调度能力。系统不采用传统 crontab 表达式，而是采用**条件触发 + 链式任务**的模式，与 Agent 的自然语言理解能力深度结合。

### 1.1 设计目标

- **条件驱动**：任务触发基于语义条件而非固定时间点
- **链式编排**：支持任务完成后自动触发后续任务
- **轻量无侵入**：嵌入在 Agent 主循环中，无需外部调度器
- **自然语言接口**：用户可通过对话直接创建和管理定时任务

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 主循环 (core/agent.py)               │
│                                                              │
│  每次对话循环 → 检查定时任务 → 触发满足条件的任务 → 继续对话  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    CronScheduler (调度器)                     │
│                                                              │
│  ┌─────────────────────┐  ┌────────────────────────────┐    │
│  │  check_conditions()  │  │  execute_chain()           │    │
│  │  检查触发条件         │  │  执行任务链                 │    │
│  └──────────┬──────────┘  └─────────────┬──────────────┘    │
└─────────────┼────────────────────────────┼───────────────────┘
              │                            │
              ▼                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   任务存储（内存 + 持久化）                    │
│                                                              │
│  当前活跃任务 ←→ SQLite 持久化 ←→ Agent 对话创建/管理        │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 设计模式

```
非传统 Cron： "每周一早上 9 点通知我"  →  crontab 表达式
ShuyuanCore： "如果股市开盘了提醒我"    →  条件表达式
```

---

## 3. 任务模型

### CronJob 数据结构

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 任务唯一标识 |
| name | str | 任务名称（用户友好） |
| condition | str | 触发条件的自然语言描述 |
| action | str | 任务执行的动作描述 |
| interval_seconds | int | 检查间隔（秒） |
| max_executions | int | 最大执行次数（-1 为不限） |
| executed_count | int | 已执行次数 |
| enabled | bool | 是否启用 |
| chain_next | str | 完成后自动触发的下一个任务 ID |

### 任务状态

```
created → enabled → running → completed
                    ↓
                disabled (手动暂停)
```

---

## 4. 调度逻辑

### 4.1 条件检查

调度器在每次对话循环后执行：

```
1. 遍历所有 enabled 状态的任务
2. 检查 interval_seconds 是否到达
3. 评估 condition 是否满足（调用 LLM 判断）
   ├── 满足 → 执行 action
   └── 不满足 → 跳过，等待下次检查
4. 更新 executed_count
5. 如果 max_executions 已达 → 标记为 completed
```

### 4.2 链式任务

当任务 A 执行完成后，自动触发任务 B：

```
Job A (检查天气) → 执行完成
    → 自动触发 Job B (发送天气提醒给用户)
        → 执行完成
            → 自动触发 Job C (记录到日志)
```

### 4.3 条件触发模式

条件触发是 ShuyuanCore 定时任务系统的核心特性：

- 通过 LLM 评估自然语言条件是否满足
- 支持复杂语义条件："如果某只股票涨幅超过 5%"、"如果和用户的对话陷入僵局"
- 条件评估结果与 Agent 当前上下文状态关联

---

## 5. 配置项

```yaml
cron:
  enabled: true                    # 定时任务总开关
  check_interval: 60              # 条件检查间隔（秒）
  condition_trigger: true          # 启用条件触发模式
  task_chain: true                 # 启用链式任务
```

### 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enabled | 是否启用定时任务系统 | true |
| check_interval | Agent 每次对话循环后的检查间隔 | 60 秒 |
| condition_trigger | 是否启用基于 LLM 的条件评估 | true |
| task_chain | 是否支持链式任务编排 | true |

---

## 6. 与系统的集成

### 与 Agent 主循环的集成

```python
# Agent 每次对话循环的收尾阶段
async def _process_message(self, message):
    # 1. 处理用户消息
    response = await self._generate_response(message)

    # 2. 更新信念
    await self._update_beliefs(message, response)

    # 3. 检查定时任务
    if self.config.cron.enabled:
        await self.cron_scheduler.check_and_execute(self.context)

    return response
```

### 工具接口

定时任务作为内置工具暴露给 Agent，支持自然语言创建和管理：

- `create_cron_job` — 根据自然语言描述创建定时任务
- `list_cron_jobs` — 查看当前所有定时任务
- `pause_cron_job` — 暂停指定定时任务
- `resume_cron_job` — 恢复指定定时任务
- `delete_cron_job` — 删除定时任务

---

## 7. 数据持久化

任务数据通过 SQLite 持久化：

```sql
CREATE TABLE IF NOT EXISTS cron_jobs (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    condition       TEXT NOT NULL,
    action          TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    max_executions  INTEGER NOT NULL DEFAULT -1,
    executed_count  INTEGER NOT NULL DEFAULT 0,
    enabled         INTEGER NOT NULL DEFAULT 1,
    chain_next      TEXT DEFAULT '',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
```

---

## 8. 待实现功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| CronJob 数据模型 | 🔴 高 | 任务数据结构和字段定义 |
| Scheduler 调度循环 | 🔴 高 | 条件检查和任务执行核心逻辑 |
| LLM 条件评估 | 🔴 高 | 调用 LLM 判断自然语言条件是否满足 |
| 链式任务编排 | 🟡 中 | 任务完成后自动触发下一个任务 |
| 持久化存储 | 🟡 中 | SQLite 表的 CRUD 操作 |
| 对话式任务管理 | 🟢 低 | 通过自然语言创建/修改/删除任务 |

---

## 9. 安全注意事项

- 定时任务动作执行前需经过安全审批
- 条件评估中不允许执行任意代码
- 检查间隔设置下限，防止密集检查导致资源耗尽