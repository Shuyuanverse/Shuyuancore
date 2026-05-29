# ShuyuanCore 自演化系统设计方案

## 1. 概述

自演化系统赋予 ShuyuanCore 根据实际使用情况自动优化自身行为的能力。系统通过"生、融、灭"（Birth / Fusion / Death）三大机制管理模块生命周期，使 Agent 在持续使用中不断进化。

### 1.1 设计目标

- **自我优化**：从成功执行轨迹中自动提炼可复用模块
- **动态精简**：融合相似模块、淘汰冗余模块，保持模块池精炼
- **质量门控**：每次演化操作都经过 LLM 质量审查，防止劣化
- **配置驱动**：所有演化阈值和策略通过配置控制

### 1.2 核心理念

```
生 (Birth)   执行业务 → 记录轨迹 → 提炼模块 → 质量审查 → 注册入库
融 (Fusion)  检测协作 → 合并模块 → 质量审查 → 新模块入库 → 旧模块归档
灭 (Death)   检测闲置 → 标记归档
```

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent 执行引擎                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 证据更新器 │  │ 风险更新器 │  │ 创新更新器 │  │  ...     │   │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘   │
└────────┼──────────────┼──────────────┼─────────────┼────────┘
         │              │              │             │
         ▼              ▼              ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                  ModuleManager (模块管理器)                    │
│                                                              │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │
│   │  create_module│  │ fuse_modules │  │archive_inactive  │   │
│   │   (生)       │   │   (融)       │   │   (灭)          │   │
│   └──────┬──────┘   └──────┬──────┘   └───────┬─────────┘   │
└──────────┼──────────────────┼──────────────────┼─────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  功能模块存储 (SQLite)                        │
│  ┌─────────────────┐  ┌─────────────────────────┐           │
│  │ evolution_modules│  │ evolution_collaborations│           │
│  └─────────────────┘  └─────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 模块生命周期

### 3.1 生（Birth）— 模块创建

从**成功执行轨迹**中自动提炼可复用的模块 prompt。

**触发条件：**
- 同类任务在 `birth_window_days`（默认 7 天）内被触发了 `birth_threshold`（默认 40）次
- 由 Agent 主循环中的 `_background_update` 任务检测

**执行流程：**

```
1. 收集执行轨迹（多轮对话、工具调用、执行结果）
2. 调用 LLM 生成模块 prompt
   └── System: "根据以下任务执行轨迹，生成一个可复用的提示词"
   └── User: 执行轨迹文本
3. 质量门控：ReviewAgent 审查 prompt 质量
   ├── quality ≥ 0.7 → 通过，进入步骤 4
   └── quality < 0.7 → 重试一次
       ├── 重试后 quality ≥ 0.7 → 通过
       └── 重试后 quality < 0.7 → 抛出 ValueError，创建失败
4. 分配 memory_partition（格式：module_{uuid8}）
5. 插入 evolution_modules 表，status = 'active'
```

**LLM Prompt 模板：**

```
System: 你是一个模块生成器。根据以下任务执行轨迹，生成一个可复用的提示词，
用于指导未来的类似任务。

User: 执行轨迹：
{execution_trajectory}
```

### 3.2 融（Fusion）— 模块融合

将两个高频协作的模块合并为一个复合模块，消除冗余。

**触发条件：**
- 两个模块在 `fusion_window_days`（默认 3 天）内协作次数 ≥ `fusion_threshold`（默认 3）
- 协作次数通过 `get_collaboration_count()` 查询 `evolution_collaborations` 表

**执行流程：**

```
1. 检查模块 A 和 B 均存在
2. 读取两个模块的 prompt 内容
3. 调用 LLM 融合 prompt
   └── System: "将下面两个模块的提示词合并成一个更强大的提示词"
   └── User: "模块 A: ... \n\n 模块 B: ..."
4. 质量门控：quality ≥ 0.7？
   ├── 否 → 抛出 ValueError
   └── 是 → 继续
5. 创建新模块（名称格式：{name_a}_{name_b}_fused）
6. 归档旧模块（status = 'archived'）
7. 记录融合事件
```

**LLM Prompt 模板：**

```
System: 你是一个模块融合器。请将下面两个模块的提示词合并成一个更强大的提示词，
保留两者优点，消除冗余，形成有机的整体。

User: 模块 A（{name_a}）：
{prompt_a}

模块 B（{name_b}）：
{prompt_b}
```

### 3.3 灭（Death）— 模块归档

长期未使用的模块自动归档，保持模块池的精炼和高效。

**触发条件：**
- 模块状态为 `active`
- `last_trigger_at` 为空 或 `last_trigger_at` 距今超过 `death_inactive_days`（默认 14 天）
- 由 `archive_inactive_modules()` 定期检测

**执行流程：**

```
1. 查询所有 active 状态的模块
2. 筛选出 last_trigger_at 为空 或 超过 inactive_days 的模块
3. 将状态更新为 'archived'
4. 设置 archived_at 时间戳
```

---

## 4. 数据结构

### evolution_modules 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 模块唯一标识（UUID hex） |
| name | TEXT | 模块名称 |
| prompt_text | TEXT | 生成的提示词 |
| memory_partition | TEXT | 记忆分区标识 |
| task_type | TEXT | 任务类型 |
| trigger_count | INTEGER | 触发次数（默认 0） |
| status | TEXT | 状态（active / archived） |
| created_at | INTEGER | 创建时间戳（毫秒） |
| last_trigger_at | INTEGER | 最后触发时间戳 |
| archived_at | INTEGER | 归档时间戳 |

### evolution_collaborations 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 协作记录 ID |
| from_module | TEXT | 源模块 ID |
| to_module | TEXT | 目标模块 ID |
| timestamp | INTEGER | 协作时间戳（毫秒） |

---

## 5. 配置项

```yaml
evolution:
  birth_threshold: 40           # 生：同类任务触发 N 次后创建模块
  birth_window_days: 7          # 生：统计窗口（天）
  fusion_threshold: 3           # 融：模块协作 N 次后触发融合
  fusion_window_days: 3         # 融：协作统计窗口（天）
  death_inactive_days: 14       # 灭：N 天未使用则归档
  enable_auto_evolution: true   # 自动演化总开关
```

---

## 6. 与系统的集成

### 与核心 Agent 的集成

在 Agent 主循环的 `_background_update` 后台任务中：

```python
async def _background_update(self, ...):
    # 1. 更新器执行
    updater_results = await self._run_updaters(...)

    # 2. 提取触发信息
    if self._should_check_evolution():
        # 2a. 记录模块协作
        for module_a, module_b in detected_collaborations:
            await self.module_manager.record_collaboration(module_a, module_b)

        # 2b. 检查融合条件
        for pair in high_collaboration_pairs:
            if pair.collaboration_count >= self.config.fusion_threshold:
                await self.module_manager.fuse_modules(pair.a_id, pair.b_id)

        # 2c. 归档闲置模块
        await self.module_manager.archive_inactive_modules()

    # 3. 信念写入
    ...
```

### 与信念存储的集成

- 模块提示词通过 `memory_partition` 分区存储
- 模块的使用频率通过 `trigger_count` 追踪
- 模块的协作关系通过 `evolution_collaborations` 表追踪

---

## 7. 质量门控

所有演化操作（生和融）都经过 `ReviewAgent` 的质量审查。

### 评分标准

| 维度 | 说明 |
|------|------|
| 完整性 | prompt 是否包含完整的执行逻辑 |
| 准确性 | prompt 是否正确反映了任务需求 |
| 一致性 | prompt 是否与系统风格一致 |
| 安全性 | prompt 是否涉及风险操作 |

### 阈值策略

| 操作 | 首次阈值 | 重试阈值 | 重试次数 |
|------|---------|---------|---------|
| 模块创建 | 0.7 | 0.7 | 1 |
| 模块融合 | 0.7 | - | 0 |

---

## 8. 安全与边界

- 所有演化操作都有审计日志
- 模块创建和融合均可通过配置关闭
- 归档操作不会物理删除数据，仅更新状态
- 模块名称生成使用 UUID hex 防止冲突