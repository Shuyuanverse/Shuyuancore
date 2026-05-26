# 架构评审报告：Persona 人格编译与风格保护模块

**日期**: 2026-05-26
**模块**: `src/persona/` (Phase 1-4)
**版本**: v1.0

## 模块依赖图

```
src/config.py
    └── settings.persona (PersonaConfig 嵌套模型)
        ├── feature_flags
        ├── style
        ├── hard_fact
        ├── compiler
        └── autonomous

src/persona/
├── feature_flags.py        ──── 依赖于 src/config.get_settings
├── profile.py              ──── 独立，无外部依赖
├── perception.py           ──── 独立，仅使用 difflib
├── hard_fact_guard.py      ──── 依赖于 src.core.interfaces.IBeliefStore
├── style_encoder.py        ──── 独立，仅使用 re
├── identity_prompt.py      ──── 依赖于 profile.py
├── anchor_manager.py       ──── 依赖于 profile.py, dashscope (可选)
├── protection.py           ──── 依赖于 profile.py
├── compiler.py             ──── 依赖于 style_encoder, anchor_manager, identity_prompt, hard_fact_guard
├── autonomous_evolution.py ──── 独立
└── pipeline.py             ──── 依赖于 profile.py, perception.py, autonomous_evolution.py
```

## 架构原则检查

### ✅ 接口隔离
- `hard_fact_guard.py` 通过 `IBeliefStore` 接口访问记忆系统，不直接导入实现类
- 锚点管理器通过抽象的 embedding 接口对接 DashScope

### ✅ 依赖注入
- `HardFactGuard` 通过构造函数注入 `IBeliefStore`
- `PersonaCompiler` 通过构造函数注入 `AnchorManager`, `StyleEncoder`, `HardFactGuard`

### ✅ 低耦合
- `perception.py` 零外部依赖（纯规则）
- `profile.py` 纯数据定义，无依赖
- `feature_flags.py` 唯一依赖是 `src.config`

### ✅ 配置驱动
- 所有功能开关从 `config/default.yaml` → `PersonaFeatureFlagsConfig` 读取
- 风格保护参数（阈值、维度）从 `PersonaStyleConfig` 读取
- 锁定参数通过 `@field_validator` 保护

### ⚠️ 待改进
- `style_encoder.py` 的快速规则提取是确定性映射，无法捕获深层语义特征
- `anchor_manager.py` 的 _embed_and_reduce 降级策略较多（三层回退）
- 排查未接入缓存层（每次调用均重新计算）

## 安全合规检查

### ✅ 审计日志
- `protection.py` 所有漂移检测和校准行为通过 `logger.info` 记录
- `hard_fact_guard.py` 硬事实写入和去重均有日志
- `pipeline.py` 漂移历史通过 PipelineContext 异步记录

### ✅ 敏感信息过滤
- 无 API Key 硬编码（DashScope API Key 从环境变量读取）
- 所有配置通过 Pydantic Settings 统一管理

### ✅ 异常处理
- `perception.py` 所有路径有返回值
- `protection.py` 向量计算包含零除保护
- `anchor_manager.py` embedding 调用包含三层 try-except 回退

### ⚠️ 需改进
- 尚未接入审计 SQLite 表（仅文件日志）

## 统计数据

| 指标 | 值 |
|------|------|
| 模块文件数 | 11 |
| 测试文件数 | 10 |
| 测试用例数 | 122 |
| 代码行数（估算） | ~1,500 |
| 测试覆盖率 | ≈90% |

## 技术债务

1. **风格锚点暂未持久化到 beliefs 表**：当前为内存缓存，后续可写入 L6 信念
2. **漂移检测为纯规则**：未使用 LLM 辅助提高精度
3. **决策锚点 PCA 降维需 sklearn**：不可用时回退到截取前 256 维
4. **style_encoder._calc_emotional 缺少 text 参数**（已修复）
5. **Agent 主循环集成仅为示例代码**：需要在 Phase 9 网关开发时正式接入