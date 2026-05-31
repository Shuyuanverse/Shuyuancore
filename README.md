# ShuyuanCore

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

**智能进化、风格一致、深度记忆、自主行动的开源 AI Agent。**

*ShuyuanCore — An open-source AI agent with intelligent evolution, consistent style, deep memory, and autonomous action.*

---

## 为什么需要 ShuyuanCore？

今天的 AI Agent 已经能帮你干活了——跑命令、搜文件、写代码。但它们不理解为什么这么做，不预判你下一步需要什么，不在成长中保持风格一致，不会自己长出新能力。它们越用越熟练，但不会越活越通透。

**ShuyuanCore 要做一个不仅能干活、而且越干越强的 AI。** 它不光替你做事，还理解你为什么这么做、预判你下一步需要什么、在成长中保持风格一致、自己发现需要什么能力并主动生长。

> **技能进化让 Agent 越做越快，智能进化让 Agent 越做越强。**

---

## 核心特性

### 核心能力

- **多平台接入**：已实现 3 个（CLI、API Server、REPL），其余 6 个（OpenAI 兼容代理、微信、企业微信、飞书、钉钉、QQ、Telegram）标记为"待实现"
- **多提供商模型路由**：DashScope、DeepSeek、OpenAI 兼容 API、Ollama 等，按任务类型自动路由与故障转移
- **29 内置工具**：终端、文件、浏览器、Git、数据库、邮件、日历、图表、加密、监控等
- **3LLM 分工**：主 LLM（实时交互）+ 复盘 LLM（后台优化）+ 工具 LLM（参数解析）

### 进化能力

- **六层记忆系统**：核心记忆 → 工作记忆 → 长期历史（SQLite + ChromaDB）→ 因果技能图 → 关系记忆 → 人格记忆
- **因果技能图**：技能不是扁平关键词匹配，而是带前置条件、因果链、适用边界、失败模式的图结构推理
- **技能 Curator**：7 天周期自动审查、修补、合并、归档，防止技能库膨胀

### 独有能力

- **人格编译引擎**：从真实对话（100 字~100 万字）中编译出数字人格，256 维风格编码 + 256 维决策锚点
- **风格保护机制**：松刹车策略，长期运行偏离率 ≤ 20%（ECS 实战验证参数）
- **预测式用户建模（待实现：骨架文件已就位）**
- **自演化架构（部分实现：module_manager 可用，包入口待完善）**

---

## 快速开始

### 方式一：源码部署（推荐）

```bash
git clone https://github.com/Shuyuanverse/Shuyuancore.git
cd Shuyuancore
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env
# 编辑 .env 填入 API Key
shuyuancore serve
```

### 方式二：Docker 一键部署

```bash
git clone https://github.com/Shuyuanverse/Shuyuancore.git
cd Shuyuancore
cp .env.example .env
# 编辑 .env 填入 API Key
docker-compose up -d
```

### 方式三：CLI 交互

```bash
shuyuancore repl
```

### 配置

最小配置仅需一个 API Key：

```bash
# .env
DASHSCOPE_API_KEY=your-api-key-here
```

> $5 VPS 即可运行，零配置起步。

---

## 使用方式

### CLI 交互模式

```bash
shuyuancore repl
```

进入 REPL 后直接对话，支持 `/new`、`/model`、`/skills`、`/memory`、`/approve` 等 Slash 命令。

### API Server

```bash
shuyuancore serve
```

服务启动在 `http://localhost:8005`，API 文档在 `http://localhost:8005/docs`。

```bash
# 发送对话请求
curl -X POST http://localhost:8005/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，介绍一下你自己"}'
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `shuyuancore serve` | 启动 API 服务器 |
| `shuyuancore repl` | 启动交互式 CLI 对话 |
| `shuyuancore health` | 模型健康检查 |
| `shuyuancore model list` | 列出当前模型配置 |
| `shuyuancore model switch <role> <model>` | 切换模型 |
| `shuyuancore mode <quick\|balanced\|deep>` | 设置多智能体协作模式 |

---

## 架构总览

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────┐
│                  Gateway 层                       │
│  CLI  │  API  │  Telegram(待实现)  │  微信(待实现)  │  飞书(待实现)  │  ...(待实现) │
└────────────────────────┬────────────────────────┘
                         │
┌────────────────────────▼────────────────────────┐
│                Core Agent                         │
│  身份加载 → 上下文准备 → 执行模式判断 → 安全检查    │
└────┬──────────────────┬──────────────────┬───────┘
     │                  │                  │
┌────▼────┐     ┌───────▼───────┐  ┌──────▼──────┐
│ Memory  │     │  Skills       │  │  Agents     │
│ 6层记忆  │     │ 因果技能图     │  │ 多智能体协作  │
│         │     │ Curator回收   │  │ 子代理并行   │
└─────────┘     └───────────────┘  └─────────────┘
     │                  │                  │
┌────▼────┐     ┌───────▼───────┐  ┌──────▼──────┐
│ Persona │     │  Evolution    │  │ Prediction  │
│ 人格编译 │     │ 自演化架构     │  │ 预测式建模   │
│ 风格保护 │     │ 生/融/灭      │  │ 主动发起     │
└─────────┘     └───────────────┘  └─────────────┘
```

---

## 项目结构

```
ShuyuanCore/
├── src/
│   ├── core/          # 核心 Agent 循环
│   ├── memory/        # 六层记忆系统
│   ├── skills/        # 因果技能系统
│   ├── tools/         # 29 个内置工具
│   ├── agents/        # 多智能体协作
│   ├── persona/       # 人格编译引擎
│   ├── models/        # 模型路由与提供商
│   ├── gateway/       # 2 个平台消息接入（CLI + API），其余待实现
│   ├── security/      # 安全体系（已实现：审批/审计/沙箱，其余待实现）
│   ├── cron/          # 定时任务
│   ├── evolution/     # 自演化架构
│   └── prediction/    # 预测式用户建模
├── config/
│   └── default.yaml   # 默认配置
├── tests/             # 840+ 个测试用例
├── docs/              # 14 份技术文档
├── deploy/            # Docker/systemd/Nginx 部署配置
├── migrations/        # Alembic 数据库迁移
├── pyproject.toml
└── README.md
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [产品方案](docs/ShuyuanCore_产品方案.md) | 愿景、能力体系、商业模式 |
| [技术架构](docs/ShuyuanCore_技术架构.md) | 模块设计、数据流、依赖清单 |
| [API 接口文档](docs/ShuyuanCore_API接口文档.md) | RESTful 端点定义 |
| [数据库 Schema](docs/ShuyuanCore_数据库Schema.md) | 表结构定义 |
| [部署文档](docs/DEPLOYMENT.md) | 安装、配置、故障排查 |
| [开发路线图](ROADMAP.md) | 开发任务与状态 |

更多设计方案文档见 `docs/` 目录。

---

## 贡献

欢迎贡献代码、报告问题、提出建议！请阅读以下指南：

- [贡献指南](CONTRIBUTING.md) — 如何提交代码
- [行为准则](CODE_OF_CONDUCT.md) — 社区规范
- [安全政策](SECURITY.md) — 如何报告安全漏洞

### 快速开始贡献

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

---

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源许可证。

*ShuyuanCore — 让 AI 从"工具"进化为"智能伙伴"。*
