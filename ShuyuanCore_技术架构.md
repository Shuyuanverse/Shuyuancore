# ShuyuanCore 技术架构方案
版本：v1.0 | 日期：2026-05-26
## 一、项目结构
ShuyuanCore/
├── src/
│ ├── core/                    # 核心Agent循环
│ │ ├── agent.py              # Agent主类：对话循环
│ │ ├── conversation.py       # 会话管理：上下文窗口、动态压缩
│ │ └── router.py             # 模型路由：按任务类型选模型
│ │
│ ├── memory/                  # 六层记忆系统
│ │ ├── base.py               # 记忆基类和接口
│ │ ├── core\_memory.py        # L1 核心记忆（MEMORY.md + USER.md）
│ │ ├── working\_memory.py     # L2 工作记忆（中期自动过期）
│ │ ├── long\_term.py          # L3 长期历史（SQLite FTS5 + ChromaDB向量检索）
│ │ ├── skill\_memory.py       # L4 因果技能图
│ │ ├── relational.py         # L5 关系记忆（含动态用户心理模型）
│ │ ├── persona\_memory.py     # L6 人格记忆
│ │ ├── store.py              # 统一存储管理（SQLite初始化 + ChromaDB初始化）
│ │ └── embedding.py          # Embedding服务（DashScope API优先，本地降级）
│ │
│ ├── skills/                  # 因果技能系统
│ │ ├── engine.py             # 技能引擎（提炼、因果抽取、渐进披露）
│ │ ├── graph.py              # 因果技能图（JSON图结构）
│ │ ├── curator.py            # Curator（7天固定触发，最多3次迭代）
│ │ └── manager.py            # 技能管理器（CRUD、导入导出、市场）
│ │
│ ├── tools/                   # 工具系统（29个内置工具）
│ │ ├── registry.py           # 工具注册表
│ │ ├── mcp\_client.py         # MCP客户端
│ │ ├── mcp\_server.py         # MCP服务端
│ │ └── builtin/              # 内置工具
│ │ ├── terminal.py           # 终端命令执行
│ │ ├── file\_ops.py           # 文件操作
│ │ ├── web.py                # 网页搜索提取
│ │ ├── browser.py            # 浏览器自动化
│ │ ├── memory.py             # 记忆管理工具
│ │ ├── skills.py             # 技能管理工具
│ │ ├── code\_exec.py          # 代码沙盒执行
│ │ ├── media.py              # 图像/TTS/视觉
│ │ ├── cron.py               # 定时任务
│ │ ├── delegation.py         # 子代理委派
│ │ ├── database.py           # 数据库操作（MySQL/PostgreSQL/SQLite）
│ │ ├── git.py                # Git操作（clone/commit/push/PR/diff）
│ │ ├── api\_debug.py          # API调试（HTTP请求、接口测试）
│ │ ├── doc\_gen.py            # 文档生成（Markdown/PDF/DOCX/PPT）
│ │ ├── xiaohongshu.py        # 小红书（搜索笔记、提取评论、趋势分析）
│ │ ├── douyin.py             # 抖音（搜索视频、提取文案、数据分析）
│ │ ├── weibo.py              # 微博（搜索热搜、提取评论、话题监控）
│ │ ├── wechat\_mp.py          # 公众号（搜索文章、提取全文、阅读量分析）
│ │ ├── email.py              # 邮件操作（收发邮件、搜索邮件）
│ │ ├── calendar.py           # 日历操作（读写日历、日程管理）
│ │ ├── spreadsheet.py        # 表格处理（读写Excel/CSV、数据分析）
│ │ ├── translate.py          # 翻译（多语言翻译）
│ │ ├── project\_mgmt.py       # 项目管理（GitHub Issues/Jira/飞书任务）
│ │ ├── knowledge\_base.py     # 知识库（Notion/语雀/Obsidian）
│ │ ├── file\_convert.py       # 文件转换（PDF转Word、图片OCR、格式互转）
│ │ ├── monitoring.py         # 监控告警（服务器状态、网站可用性、异常通知）
│ │ ├── chart.py              # 画图/图表（流程图、架构图、数据可视化）
│ │ └── crypto.py             # 加密/签名（文件加密、数字签名、证书管理）
│ │
│ ├── agents/                  # 多智能体协作
│ │ ├── coordinator.py        # 多Agent协调器
│ │ ├── decision.py           # 决策Agent
│ │ ├── review.py             # 审查Agent（漂移阈值0.15）
│ │ ├── arbitrate.py          # 仲裁Agent（务实合成）
│ │ ├── sub\_agent.py          # 隔离子代理（最多5个）
│ │ └── multi\_view.py         # 多视角并行推理（2-5个视角）
│ │
│ ├── persona/                 # 人格编译引擎
│ │ ├── compiler.py           # 人格编译器（主流程）
│ │ ├── style\_encoder.py      # 风格编码器（双实现：PyTorch 256维 + NumPy 256维）
│ │ ├── decision\_anchor.py    # 决策锚点提取器（双实现：PyTorch 256维 + NumPy 256维）
│ │ ├── protection.py         # 风格保护（松刹车策略，drift\_threshold=0.25）
│ │ ├── core.py               # CORE.md身份管理（原SOUL.md）
│ │ ├── mode.py               # 通用↔人格模式切换
│ │ ├── identity.py           # 双维度身份矩阵（通用×多身份 / 人格×多身份）
│ │ └── style\_protection.py   # 风格保护流水线（检测偏离度+注入校准指令）
│ │
│ ├── gateway/                 # 消息平台Gateway（8个平台，同一批全做）
│ │ ├── gateway.py            # 统一Gateway管理
│ │ ├── base\_adapter.py       # 平台适配器基类
│ │ ├── telegram.py           # Telegram适配
│ │ ├── wechat.py             # 微信适配
│ │ ├── wechat\_work.py        # 企业微信适配
│ │ ├── feishu.py             # 飞书适配
│ │ ├── dingtalk.py           # 钉钉适配
│ │ ├── qq.py                 # QQ适配
│ │ ├── cli.py                # CLI终端适配
│ │ ├── api.py                # REST API适配（含完整对话历史API）
│ │ └── openai\_proxy.py       # OpenAI兼容代理
│ │
│ ├── cron/                    # 定时任务
│ │ ├── scheduler.py          # 调度器（自然语言+cron+条件触发+任务链）
│ │ └── job.py                # 任务定义和执行
│ │
│ ├── models/                  # 模型接口（三LLM分工）
│ │ ├── provider.py           # 模型提供商管理
│ │ └── openai\_compat.py      # OpenAI兼容接口
│ │
│ ├── evolution/               # 自演化架构
│ │ ├── module\_manager.py     # 模块生命周期（生/融/灭）
│ │ └── trigger.py            # 触发器（7天40次同类任务→生模块）
│ │
│ ├── prediction/              # 预测式用户建模
│ │ ├── predictor.py          # 需求预测+主动发起
│ │ └── feedback.py           # 预测准确度反馈
│ │
│ └── security/                # 安全体系（14层）
│ ├── auth.py                 # 用户认证和权限分级
│ ├── approval.py             # 危险命令审批
│ ├── audit.py                # 行为审计日志
│ ├── sandbox.py              # 执行沙箱管理（8种后端）
│ ├── encryption.py           # 数据加密（记忆、API Key、对话历史）
│ ├── network\_isolation.py    # 网络隔离（访问白名单）
│ ├── privacy.py              # 隐私脱敏（手机号、身份证、银行卡）
│ ├── session\_isolation.py    # 会话隔离（多用户数据隔离）
│ ├── rollback.py             # 操作回滚（文件级快照+恢复）
│ ├── rate\_limit.py           # 速率限制（单次/单日调用量上限）
│ ├── confirm.py              # 敏感操作二次确认
│ └── output\_filter.py        # 模型输出过滤
│
├── config/
│ └── default.yaml             # 默认配置
│
├── data/                      # 运行时数据（gitignore）
│ ├── memories/               # 记忆文件
│ │ ├── MEMORY.md
│ │ ├── USER.md
│ │ └── user\_model.json       # 动态用户心理模型
│ ├── identities/             # 多身份数据
│ │ ├── work/                 # 工作助手身份
│ │ ├── study/                # 学习助手身份
│ │ └── persona\_zhang/        # 人格模式身份（如张律师）
│ ├── skills/                 # 技能文件
│ ├── graph/                  # 因果技能图
│ ├── chroma/                 # ChromaDB持久化数据
│ ├── state.db                # SQLite数据库（唯一）
│ └── logs/                   # 日志目录
│ ├── audit.log               # 审计日志
│ └── app.log                 # 应用日志
│
├── deploy/                    # 部署配置
│ ├── systemd/
│ │ └── agentx.service        # ShuyuanCore systemd服务
│ ├── nginx/
│ │ └── agentx.conf           # Nginx反向代理配置
│ ├── docker-compose.yaml     # Docker Compose一键部署
│ ├── Dockerfile              # Docker镜像构建
│ ├── install.sh              # 一键安装脚本（curl | bash）
│ └── homebrew/               # Homebrew公式（macOS）
│
├── tests/                     # 测试
├── cli.py                     # CLI入口
├── main.py                    # 应用入口
├── pyproject.toml             # 项目配置
└── README.md
**v3变更说明（对齐产品方案v2.0全部决策）**：
• 新增 memory/working\_memory.py（L2工作记忆，替代原L2用户心理模型位置）
• 新增 persona/core.py（SOUL.md→CORE.md）、persona/identity.py（双维度身份矩阵）
• 新增 evolution/（自演化架构：7天40次触发，活跃模块≤5）
• 新增 prediction/（预测式建模+主动发起+准确度反馈）
• 新增 gateway/wechat\_work.py、dingtalk.py、qq.py（8个平台同一批全做，移除Discord）
• 新增14个工具文件：database/git/api*debug/doc*gen/xiaohongshu/douyin/weibo/wechat*mp/email/calendar/spreadsheet/translate/project*mgmt/knowledge*base/file*convert/monitoring/chart/crypto
• 安全体系从5层扩展到14层，新增encryption/network*isolation/privacy/session*isolation/rollback/rate*limit/confirm/output*filter
• 决策锚点NumPy版统一256维
• 三LLM分工：主/复盘/工具
## 二、核心模块设计
### 2.1 Agent主循环（core/agent.py）
Agent的核心是一个循环：接收消息→准备上下文→执行→生成回复→更新状态。
用户消息进来
│
▼
[1] 加载身份（CORE.md / 人格编码 + 当前身份）
│
▼
[2] 准备上下文
├── 注入核心记忆（MEMORY.md + USER.md）
├── 查询工作记忆（当前活跃项目、近期待办）
├── 检索相关历史（FTS5 + ChromaDB向量检索）
├── 匹配相关技能（因果图推理）
├── 检索相关决策上下文（关系记忆）
└── 预测用户下一步需求
│
▼
[3] 判断执行模式
├── 简单任务 → 单链执行（决策Agent）
├── 复杂决策 → 多视角并行推理（2-5个视角+仲裁）
└── 用户可选择模式：快速/平衡/深度
│
▼
[4] 执行（三LLM分工）
├── 主LLM：实时交互、任务执行（最强模型）
├── 生成回复
├── 调用工具（29个内置工具）
└── 委派子代理（最多5个并行）
│
▼
[5] 安全检查（14层防线）
├── 风格保护检测（松刹车，drift\_threshold=0.25）
├── 危险命令拦截（需审批）
├── 审查Agent质量检查（漂移阈值0.15）
├── 敏感操作二次确认
├── 模型输出过滤
└── 隐私脱敏
│
▼
[6] 返回回复
│
▼
[7] 后台更新（异步，复盘LLM）
├── 更新核心记忆
├── 更新工作记忆（当前项目状态）
├── 更新用户心理模型
├── 保存长期记忆到ChromaDB（去重阈值>0.95）
├── 提炼技能 + 抽取因果（任务难度驱动判断）
├── 记录决策上下文
├── 更新人格记忆
├── 预测准确度反馈修正
└── 自演化触发检查（7天40次同类任务→生模块）
**关键类设计**：
**// python**class Agent:
"""ShuyuanCore主Agent类"""
async def chat(self, message: str, user\_id: str, platform: str) -> str:
"""主对话入口"""
async def \_prepare\_context(self, message, user\_id) -> list[dict]:
"""准备上下文：记忆+技能+用户模型+预测"""
async def \_execute(self, context, message) -> AgentResponse:
"""执行：单链或多视角（2-5个视角+仲裁）"""
async def \_background\_update(self, message, response, user\_id):
"""后台异步更新：记忆/技能/用户模型/预测/自演化"""
**三LLM分工**：
|  |  |  |  |
| --- | --- | --- | --- |
| **LLM角色** | **职责** | **模型选择** | **频率** |
| 主LLM | 实时交互、任务执行、生成回复 | 最强模型（qwen-max） | 每轮对话 |
| 复盘LLM | 总结经验、提取因果、生成技能、优化记忆、更新用户模型 | 便宜模型（deepseek-chat） | 对话后异步 |
| 工具LLM | 处理工具调用的参数构造和结果解析 | 轻量模型（qwen-turbo） | 工具调用时 |
### 2.2 六层记忆系统
**总览**：
|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **层级** | **名称** | **存储** | **生命周期** | **用途** |
| L1 | 核心记忆 | MEMORY.md + USER.md | 永久 | 会话开始注入system prompt |
| L2 | 工作记忆 | data/memories/working/ | 中期（项目完成或30天未激活自动清理） | 当前活跃工作上下文 |
| L3 | 长期历史 | SQLite + FTS5 + ChromaDB | 永久 | 全量历史，按需检索 |
| L4 | 因果技能图 | JSON图结构 | 永久（Curator维护） | 推理式技能调用 |
| L5 | 关系记忆 | SQLite | 永久 | 决策上下文+动态用户模型 |
| L6 | 人格记忆 | JSON | 永久 | 风格锚点+漂移历史 |
**记忆分层共享规则（多身份场景）**：
• L3长期历史 + L4因果技能图 → 全局共享（所有身份可见）
• L1核心记忆 + L6人格记忆 → 身份独立（每个身份各自一份）
#### L1 核心记忆（core\_memory.py）
文件：MEMORY.md（~2200字符）+ USER.md（~1375字符）
机制：
• 会话开始时作为冻结快照注入system prompt
• Agent主动写入，立即持久化到磁盘
• 当前会话不更新（下次会话生效）
• 达到80%容量时自动合并压缩
• 防注入安全扫描
**动态压缩**：不是截断，而是把多条相关信息压缩成更高密度的表述。比如5条关于代码风格的条目合并成1条综合偏好。
#### L2 工作记忆（working\_memory.py）
**// python**class WorkingMemory:
"""工作记忆——当前活跃的工作上下文"""
active\_projects: list # 活跃项目
recent\_todos: list # 近期待办
temp\_context: dict # 临时项目上下文
priority\_overrides: dict # 优先级覆盖（工作记忆优先于L3检索）
async def activate(self, project\_name):
"""激活项目，加载相关上下文"""
async def expire\_check(self):
"""过期检查：项目完成或30天未激活自动清理"""
async def cleanup(self):
"""清理：已完成的任务移出，保留决策记录到L3/L5"""
存储：data/memories/working/（每个活跃项目一个JSON文件）
关键特性：
• 自动过期：项目完成或30天未激活→自动清理
• 优先级高于L3：检索时先查工作记忆，再查长期历史
• 解决"临时信息放进长期历史变成噪音"的问题
#### L3 长期历史（long\_term.py）
SQLite表结构：
• messages: id, session*id, user*id, role, content, timestamp
• messages\_fts: FTS5虚拟表，全文索引
ChromaDB向量索引（基于ECS实战经验）：
• 集合名：long*term*memory
• Embedding方案：DashScope text-embedding-v2（1536维）
• 存储方式：ChromaDB PersistentClient（持久化到data/chroma/）
• 对话记录集合：conversations（独立集合，存储对话历史embedding）
双引擎检索：
• FTS5：精确关键词匹配，快速
• ChromaDB向量：语义相似度匹配，理解意图（1536维DashScope embedding）
• 合并去重，按相关性排序
⚠️ ECS实战教训（必须避免）：
• ShuyuanVerse原方案用自研VectorStore（JSON文件存储），性能差且不持久→ShuyuanCore直接用ChromaDB PersistentClient
• ShuyuanVerse的conversations集合与long*term*memory集合分离，search*long*term只检索long*term*memory集合，对话记录检索入口缺失→ShuyuanCore的检索接口必须同时搜索两个集合，或统一为一个集合
• ShuyuanVerse中ChromaDB存在重复记录（如"你不想知道我在做什么方向吗"重复13次）→ShuyuanCore写入前必须做去重检查
**Embedding服务设计（memory/embedding.py）**：
**// python**class EmbeddingService:
"""Embedding服务，支持多提供商，默认DashScope"""
# 方案一（默认）：DashScope API
# - 模型：text-embedding-v2
# - 维度：1536
# - 优点：代码已有、不占服务器内存、效果更好
# - 缺点：需要网络、有API调用成本
# 方案二（降级）：sentence-transformers本地模型
# - 模型：all-MiniLM-L6-v2
# - 维度：384
# - 优点：离线可用、无API成本
# - 缺点：占~400MB内存、维度低效果差
# 方案三（轻量）：NumPy随机投影（仅开发测试）
async def embed(self, text: str) -> list[float]:
"""生成文本embedding"""
async def embed\_batch(self, texts: list[str]) -> list[list[float]]:
"""批量生成embedding"""
**对话流程接入长期记忆**：
ECS实战验证的完整流程：
1. 在dialogue*router.py的流式和非流式对话结束后调用save*long*term*memory
2. save*long\_term\_memory将关键信息提取后，通过DashScope API生成embedding
3. 写入ChromaDB的long*term*memory集合
4. 写入前做去重检查：计算新embedding与已有记录的相似度，超过0.95阈值视为重复，跳过写入
历史数据回填（参考ECS实战）：
• 用nohup后台运行回填脚本
• 通过DashScope API逐条生成embedding写入ChromaDB
• 回填脚本支持断点续传（记录已处理到的ID）
• 回填完成后验证集合记录数与源数据一致
#### L4 因果技能图（skill\_memory.py + skills/graph.py）
图结构（JSON文件 data/graph/skill\_graph.json）：
**// json**{
"nodes": {
"api-test-suite": {
"type": "skill",
"preconditions": ["识别路由结构", "理解数据模型"],
"causality": {
"level0": "测试验证行为契约→发现偏离→定位缺陷",
"level1": "完整的因果链描述...",
"level2": "详细推理过程..."
},
"boundaries": ["不适用于GraphQL", "不适用于纯前端"],
"failure\_modes": ["mock过度导致假通过"],
"dependencies": ["Python 3.11+", "Docker环境"],
"version\_history": [{"version": "1.0", "date": "2026-05-26", "change": "初始创建"}],
"verification": "运行测试套件，所有用例通过",
"source": "agent\_created",
"abstractions": ["行为契约验证"]
},
"行为契约验证": {
"type": "concept",
"children": ["api-test-suite", "django-test-suite"]
}
},
"edges": [
{"from": "api-test-suite", "to": "查询加速", "type": "causally-linked"},
{"from": "行为契约验证", "to": "api-test-suite", "type": "abstracts"}
]
}
**因果技能图9个字段**：
|  |  |  |
| --- | --- | --- |
| **字段** | **说明** | **存储** |
| 前置条件 | 什么情况下适用 | 节点属性 |
| 因果链 | 为什么这么做有效（Level 0一句话/Level 1完整链/Level 2详细推理） | 节点属性，分层存储 |
| 适用边界 | 什么情况下会失效 | 节点属性 |
| 失败模式 | 怎么做会出错 | 节点属性 |
| 关联关系 | 和其他技能的因果/适用/抽象关系 | 边 |
| 依赖关系 | 需要哪些外部条件（如Docker、Python版本） | 节点属性 |
| 版本记录 | 每次修改都记录，方便回溯和Curator审查 | 节点属性 |
| 验证方法 | 怎么确认技能执行成功 | 节点属性 |
| 来源标记 | Agent自创/用户手动/社区安装，不同来源信任等级不同 | 节点属性 |
推理调用：
1. 新任务进来 → 提取任务特征
2. 在图中遍历找到相关节点
3. 判断前置条件是否满足
4. 按因果链推理出适用技能
5. 必要时跨领域迁移（通过抽象节点）
#### L5 关系记忆（relational.py）
SQLite表结构：
• decisions: id, user*id, context, options, chosen, reason, state*at\_time, verified, timestamp
• decision*patterns: id, pattern, confidence, sample*count, last\_seen
每次重要决策记录：
• 上下文：在做什么
• 选项：有哪些选择
• 选择：最终选了什么
• 原因：为什么选这个
• 状态：当时的状态
• 验证：事后是否证明选对了
检索：匹配"相似决策情境"，不是匹配关键词
**动态用户心理模型（内嵌L5）**：
**// python**class UserModel:
"""动态用户心理模型"""
state: str # 当前状态描述
short\_term\_goals: list # 短期目标
long\_term\_goals: list # 长期目标
decision\_patterns: list # 决策模式（含置信度）
knowledge\_gaps: list # 知识盲区
emotional\_trajectory: dict # 情绪轨迹
predicted\_next: str # 预测下一步
async def update(self, message, response):
"""每次交互后更新模型"""
async def predict(self) -> str:
"""预测用户下一步需求"""
存储为 data/memories/user\_model.json，每次交互后后台异步更新。
**注意**：当前先做单用户决策记录，暂不涉及多用户间关系。
#### L6 人格记忆（persona\_memory.py）
文件：data/memories/persona.json
内容：
• style\_anchors: 人格锚点（核心风格特征，不可漂移）
• style\_trajectory: 风格变化轨迹（时间序列）
• drift\_history: 漂移检测历史
每次交互后记录风格向量，与锚点比较。
超过阈值（0.25）触发校准。
ECS实战补充：
• 审查Agent（review\_agent.py）的漂移阈值为0.15，比保护层（0.25）更严格
• 这意味着：风格保护允许0.25的漂移，但审查Agent在0.15时就会提出质疑
• 两层阈值形成梯度：0.15开始提醒→0.25强制校准
### 2.3 因果技能系统
#### 技能提炼流程（skills/engine.py）
任务完成
│
▼
[1] 判断是否值得提炼（任务难度驱动，不是工具调用数量）
├── 尝试了多种方法才成功 → 是
├── 用户纠正了方法 → 是
├── 涉及跨领域知识 → 是
├── 遇到错误找到可行路径 → 是
└── 一遍过的简单任务 → 否
│
▼
[2] 提炼技能文档（Markdown+YAML）
├── name, description, version
├── 流程步骤
├── 陷阱和注意事项
└── 验证方法
│
▼
[3] 因果抽取（额外一次LLM调用）
├── 前置条件
├── 因果链（Level 0一句话/Level 1完整链/Level 2详细推理）
├── 适用边界
├── 失败模式
├── 依赖关系
├── 验证方法
└── 与已有技能的关联
│
▼
[4] 更新因果技能图
├── 添加技能节点（含9个字段）
├── 添加因果边
└── 检查是否有新的抽象关系
│
▼
[5] 质量门控
├── 技能是否可验证？
├── 因果链是否自洽？
└── 与已有技能是否冲突？
#### 渐进式披露
Level 0（~3k tokens）：技能名+描述+分类 → 始终在上下文
Level 1（按需加载）：完整技能内容+元数据 → 使用时加载
Level 2（深度参考）：技能内特定参考文件 → 需要时才读
#### Curator回收（skills/curator.py）
触发条件：7天固定触发（不再等空闲）
Phase 1（确定性，无LLM）：
• 30天未用 → 标记过时
• 90天未用 → 归档
Phase 2（LLM审查，最多3次迭代）：
• 逐技能判断：保留/修补/合并/归档
• 3次后仍不确定的标记"需人工审查"
约束：
• 不动捆绑技能和Hub安装的技能
• 只归档不删除
• 运行前自动tar.gz快照
• 可pin保护关键技能
#### 技能市场（agentskills.io兼容）
• 社区共享技能，安装前安全扫描
• 技能质量评分：使用人数、成功率、最近更新时间
• 因果技能可带关系导入，形成网络效应
• 兼容agentskills.io开放标准（安装后Agent使用时自动补充因果信息）
### 2.4 多智能体协作
#### 协调流程（agents/coordinator.py）
消息进来
│
▼
[1] 判断复杂度
├── 简单任务（单步/有现成技能）→ 单链执行
└── 复杂决策（多方案/有权衡/不确定）→ 多视角推理
│
▼
[2a] 单链执行
决策Agent → 审查Agent（风格+质量，漂移阈值0.15）→ 返回
│
▼
[2b] 多视角并行推理（2-5个视角，Agent根据问题复杂度自定）
┌─ 视角1 → 论据A
├─ 视角2 → 论据B
├─ 视角3 → 论据C
└─ ...（最多5个视角）
│
▼
仲裁Agent → 综合各方 + 用户模型适配 → 最终建议
│
▼
用户可选择模式：
├── 快速模式：仅决策Agent
├── 平衡模式：决策+审查
└── 深度模式：多视角+仲裁
#### 多视角推理（agents/multi\_view.py）
• 视角数量：最少2个，最多5个，Agent根据问题复杂度决定
• 每条推理链可调用不同模型、引用不同记忆、使用不同技能
• 每条链输出结构化论据
• 仲裁Agent始终存在，综合各方论据+用户心理模型判断
#### 子代理（agents/sub\_agent.py）
• 隔离的Agent实例（独立沙箱+独立会话）
• 最多同时运行5个
• 通过消息队列与主Agent通信
• 结果回传到主Agent
### 2.5 人格编译引擎
#### 编译流程（persona/compiler.py）
输入：对话记录 / 专业文章 / 语音转写（100字~100万字）
│
▼
[1] 风格编码器（双实现，⚠️与决策锚点绑定使用，不可单独使用）
分析：用词习惯、句式结构、语气节奏、口头禅、情绪表达
├── PyTorch版：256维风格向量（需torch依赖，精度更高）
└── NumPy版：256维风格向量（无torch依赖，轻量部署）
输出：风格7维度画像
- formality（正式度）
- warmth（温暖度）
- directness（直接度）
- playfulness（趣味度）
- detail\_orientation（细节取向度）
- emotional\_expression（情感表达度）
- pace（节奏度）
│
▼
[2] 决策锚点提取器（双实现，⚠️与风格编码器绑定使用，不可单独使用）
分析：价值排序、风险偏好、权衡逻辑、知识体系
├── PyTorch版：256维决策锚点（需torch依赖）
└── NumPy版：256维决策锚点（无torch依赖，轻量部署）
输出：决策锚点向量
│
▼
[3] 生成人格档案（7项）
│
▼
[4] 存储为 persona\_profile.json
可注入任意ShuyuanCore实例
**输入量级**：
• 最低：100字（质量可能不够好）
• 推荐：5万字以上（风格特征才够明显）
• 最高：100万字（超过需分批处理）
**人格档案（7项）**：
|  |  |
| --- | --- |
| **项目** | **说明** |
| 价值观 | 这个人最看重什么 |
| 知识体系 | 擅长什么领域、知识结构 |
| 经历摘要 | 关键人生/职业经历 |
| 沟通偏好 | 怎么和人说话（正式？随性？爱用比喻？） |
| 决策案例 | 典型历史决策记录，展示选择逻辑 |
| 语言样本 | 500-1000条原文片段，按场景分类（正式场合/日常聊天/决策讨论/技术解释等） |
| 禁忌边界 | 绝对不会说什么、做什么（硬边界，非偏好） |
ECS实战验证（/opt/shuyuanverse/backend/app/services/persona/）：
• 完整编译流程已验证：输入资料→风格编码器分析→决策锚点提取→生成人格档案→存储为JSON
• 风格7维度已在上千条对话中验证有效
• PyTorch版和NumPy版输出可对齐，轻量版适合服务器资源受限场景
• **⚠️ 风格编码器+决策锚点为绑定组件，不可单独使用**（上一个产品验证：单独使用效果不好）
#### 风格保护（persona/protection.py + persona/style\_protection.py）
松刹车策略（ECS实战验证的参数，直接沿用，不做修改）：
• 每次输出前计算风格向量偏离度
• drift*threshold = 0.25（保护层阈值，style*protection.py:58 ProtectionConfig）
• enable\_proactive = False（不主动干预，只检测到漂移时校准）
• 超过阈值 → 在下次prompt中注入校准指令
• 长期运行偏离率 ≤ 20%
两层阈值梯度（ECS实战发现）：
• 审查Agent（review\_agent.py）漂移阈值 = 0.15（更严格）
• 0.15偏离：审查Agent提出质疑，但不强制干预
• 0.25偏离：风格保护层强制注入校准指令
• 这形成"提醒→强制"的梯度，避免一刀切
风格保护流水线（style\_protection.py，从ShuyuanVerse移植）：
1. 检测输出风格向量与锚点偏离度
2. 偏离度 < 0.15：正常通过
3. 0.15 ≤ 偏离度 < 0.25：标记为"轻微漂移"，日志记录
4. 偏离度 ≥ 0.25：注入校准指令到下一轮prompt
5. 连续3次触发校准 → 升级为"严重漂移"告警
ECS实战参数汇总：
|  |  |  |
| --- | --- | --- |
| **参数** | **值** | **来源** |
| drift\_threshold（保护层） | 0.25 | style\_protection.py:58 |
| drift\_threshold（审查Agent） | 0.15 | review\_agent.py:47 |
| enable\_proactive | False | style\_protection.py:62 |
| DRIFT*THRESHOLD*LOW | 0.15 | config.py:43 |
| DRIFT*THRESHOLD*HIGH | 0.20 | config.py:44 |
| QUALITY\_FACTOR | 0.85 | config.py:45 |
#### 身份系统（persona/core.py + persona/identity.py）
**CORE.md**：核心身份文件（原SOUL.md），定义Agent的身份、性格、行为准则
• 更中性的名称，更工具感
• 所有记忆和技能都通过这个身份透镜完成
• 缺失时回退到内置默认身份
**双维度身份矩阵**：
|  |  |  |  |
| --- | --- | --- | --- |
|  | **身份1** | **身份2** | **身份3** |
| 通用模式 | 工作助手 | 学习助手 | 研究助手 |
| 人格模式 | 张律师 | 李医生 | 王顾问 |
**多身份切换**：
• 通用模式内：工作/学习/研究等不同侧重点
• 人格模式内：不同人的数字分身
• 模式间：通用↔人格
• 最多5个身份
**切换方式**：
• 自然语言："切到工作模式"、"用张律师的身份聊"
• Slash命令：/profile work
**记忆分层共享**：
• L3长期历史+L4技能图：全局共享
• L1核心记忆+L6人格记忆：身份独立
**切换时未完成任务提醒确认**
### 2.6 工具系统
#### 工具注册（tools/registry.py）
**// python**class ToolRegistry:
"""工具注册表"""
def register(self, name, func, description, toolset, dangerous=False):
"""注册工具"""
def get\_tools\_for\_context(self, context) -> list[Tool]:
"""根据上下文返回可用工具（有记忆的工具调用）"""
async def execute(self, tool\_name, params, approval\_callback=None):
"""执行工具（危险命令需审批）"""
#### 有记忆的工具调用
工具调用前：
1. 检索记忆：上次是否做过类似操作？
2. 评估复用：上次的结论/结果还适用吗？
3. 如果复用：返回缓存结果或增量执行
4. 如果不适用：正常执行
5. 执行后：更新记忆，记录决策上下文
#### MCP协议
客户端模式：
• 连接本地stdio/远程HTTP的MCP服务器
• 自动发现工具，注册到工具表
• 调用时自动路由
服务端模式：
• 暴露ShuyuanCore的工具给外部Agent/IDE
• Claude Code/Cursor/VS Code可通过MCP调用
• 按server配置include/exclude过滤
#### ACP协议
• VS Code/Zed/JetBrains IDE集成，作为编辑器AI后端
### 2.7 消息平台Gateway（8个平台，同一批全做）
#### 统一Gateway（gateway/gateway.py）
架构：
• 单进程管理所有平台连接
• 统一消息格式：{user\_id, platform, content, attachments, metadata}
• 统一Slash命令体系
• 跨平台共享记忆和技能
平台适配器接口：
• connect(): 建立连接
• send\_message(): 发送消息
• receive\_message(): 接收消息（回调）
• get*user*info(): 获取用户信息
• platform\_features(): 返回平台特性（支持线程？支持文件？）
#### 平台深度适配
|  |  |
| --- | --- |
| **平台** | **深度适配能力** |
| Telegram | Inline keyboard交互确认、后台任务通知 |
| 微信 | 语音消息处理、小程序卡片 |
| 企业微信 | 企业通讯录对接、审批流 |
| 飞书 | 多维表格对接、审批流集成 |
| 钉钉 | 审批流集成、群机器人 |
| QQ | 消息推送、文件传输 |
| CLI | 富文本输出、进度条、交互式确认 |
| API | RESTful接口 + WebSocket推送 + 完整对话历史API（分页） |
#### REST API设计（gateway/api.py）
ShuyuanCore的API必须包含完整的对话历史端点：
GET /api/v1/conversations # 获取对话列表
GET /api/v1/conversations/{id}/messages # 获取对话消息（分页）
?page=1&per\_page=50&before={msg\_id} # 支持上拉加载更多
POST /api/v1/conversations # 创建新对话
DELETE /api/v1/conversations/{id} # 删除对话
GET /api/v1/conversations/{id}/messages/search # 搜索对话内容
关键设计要求：
1. 后端必须存储完整对话历史（SQLite），不依赖前端localStorage
2. 消息API必须支持分页（page + per\_page 或 cursor-based）
3. 必须支持before参数实现"上拉加载更多"
4. 前端可以缓存最近消息到localStorage，但权威数据源是后端
5. localStorage仅作为离线展示的降级方案，不能作为主存储
### 2.8 定时任务（cron/scheduler.py）
定义方式：自然语言 或 cron语法
存储：SQLite表（jobs: id, schedule, skill, prompt, deliver*to, last*run, next\_run）
执行：
• 轮询检查到期任务
• 可选预加载技能
• 可选no\_agent模式（确定性操作，不消耗LLM）
• 结果回传到指定平台（deliver=all全平台广播）
自然语言解析：LLM将"每天早上8点发新闻"解析为cron表达式
**条件触发**：
• 基于事件触发（如服务器CPU超80%告警、GitHub新Issue通知、竞品发布新版本提醒）
• 可配置触发条件和执行动作
**任务链**：
• 一个任务完成后自动触发下一个
• 前一步输出是后一步输入
• 支持多步串行流水线
### 2.9 安全体系（14层防线）
|  |  |  |
| --- | --- | --- |
| **层级** | **防线** | **说明** |
| 1 | 用户认证 | 管理员/普通用户权限分区 |
| 2 | 危险命令审批 | dangerous=True的工具需 /approve 确认 |
| 3 | 沙箱隔离 | 默认Docker执行，限制文件系统和网络 |
| 4 | 行为审计 | 所有工具调用记录到audit.log |
| 5 | 供应链安全 | 技能安装前扫描恶意内容 |
| 6 | 数据加密 | 记忆、API Key、对话历史存储加密 |
| 7 | 网络隔离 | Agent执行任务时网络访问白名单可控 |
| 8 | 隐私脱敏 | 对话记录写入记忆前自动脱敏手机号、身份证、银行卡等 |
| 9 | 会话隔离 | 多用户场景下不同用户数据完全隔离 |
| 10 | 操作回滚 | 文件级快照+恢复 |
| 11 | 速率限制 | 单次/单日调用量上限，超限即停 |
| 12 | 敏感操作二次确认 | 发邮件、发消息、转账等对外发送操作必须确认 |
| 13 | 模型输出过滤 | LLM生成内容返回前过滤敏感信息 |
| 14 | 权限分级 | 细粒度权限配置（工具、目录、命令审批等按用户不同） |
ECS实战补充：
• fail2ban封SSH的教训：云电脑出口IP被封锁，需VNC解封
• ShuyuanCore部署时应将fail2ban与ShuyuanCore的IP白名单联动
• .env文件明文存储API Key的风险：ShuyuanCore应支持环境变量注入，.env不提交git
### 2.10 执行沙箱（8种后端）
|  |  |
| --- | --- |
| **后端** | **说明** |
| 本地（裸机） | 直接执行，无隔离 |
| Docker | 容器隔离，默认选项 |
| SSH | 远程机器执行 |
| Singularity | HPC集群 |
| Modal | 无服务器，空闲零成本 |
| Daytona | 云端开发环境 |
| Vercel Sandbox | 轻量沙箱 |
| Kubernetes | 企业级集群部署 |
命令审批机制：危险命令需用户 /approve 确认
### 2.11 部署与安装（6种方式）
|  |  |
| --- | --- |
| **方式** | **命令/操作** |
| 一键安装 | `curl \
| Homebrew | brew install agentx（macOS用户） |
| Docker一键 | docker run agentx/agentx |
| 源码部署 | git clone && pip install && agentx |
| 云端一键 | 一键部署到阿里云/腾讯云/AWS |
| 零配置起步 | agentx setup 向导引导 |
$5 VPS即可运行
### 2.12 预测式用户建模（prediction/）
**动态心理模型**（见L5记忆层）：每次交互后自动推理更新
**用户可感知**：
• 不用每次从头解释背景
• Agent在还没开口时主动准备相关信息
• 沟通方式自动适配状态（焦虑时简洁，轻松时可以多聊）
• 在认知盲区主动提醒
• **主动发起**：不等你开口，Agent觉得该提醒你时会主动找你（如"你三天没碰那个项目了，要不要继续？"）
• **预测准确度反馈**：Agent预判→你实际行为→对比→修正模型，预判越来越准
### 2.13 自演化架构（evolution/）
Agent的架构本身能演化——不只是技能库变大，而是能力结构在生长。
第1天：通用Agent
└── 主推理模块
第7天：检测到40次代码相关任务
└── 主推理模块
└── 代码推理模块（自动生成，含独立prompt和记忆分区）
第14天：代码推理+架构分析频繁协作
└── 主推理模块
└── 代码推理模块
└── 架构设计模块（自动融合生成）
第28天：某模块14天未激活
└── 主推理模块
└── 架构设计模块
└── [用户建模模块 → 已归档，可随时唤醒]
**演化规则**：
• **生**：7天内40次同类任务 → 自动创建专属模块（独立prompt+记忆分区+技能子图）
• **融**：两个模块3天内协作3次以上 → 自动融合产生新能力
• **灭**：模块14天未激活 → 自动归档（不删除，可唤醒）
• 同时活跃模块不超过5个
• 模块创建流程：LLM根据积累的同类技能和经验自动生成模块prompt → 审查Agent检查质量 → 通过后激活
## 三、数据存储方案
|  |  |  |  |
| --- | --- | --- | --- |
| **数据类型** | **存储方式** | **路径** | **备注** |
| 核心记忆 | Markdown | data/memories/MEMORY.md, USER.md | L1 |
| 工作记忆 | JSON | data/memories/working/ | L2，中期自动过期 |
| 用户模型 | JSON | data/memories/user\_model.json | L5内嵌 |
| 人格档案 | JSON | data/memories/persona\_profile.json | - |
| 对话历史 | SQLite + FTS5 | data/state.db | L3 |
| 向量索引 | ChromaDB PersistentClient | data/chroma/ | DashScope text-embedding-v2 |
| Embedding缓存 | ChromaDB内 | data/chroma/ | 去重阈值>0.95 |
| 决策记录 | SQLite | data/state.db | L5 |
| 技能文件 | Markdown+YAML | data/skills/ | - |
| 因果技能图 | JSON | data/graph/skill\_graph.json | L4，9个字段 |
| 多身份数据 | 目录 | data/identities/ | L1+L6身份独立 |
| 配置 | YAML | config/default.yaml | - |
| 审计日志 | 文本 | data/logs/audit.log | - |
| 应用日志 | 文本（轮转） | data/logs/app.log | RotatingFileHandler |
**ChromaDB集合设计（基于ECS实战）**：
集合1：long*term*memory
• 用途：存储Agent提炼的长期记忆
• 预期数据量：数百条
• Embedding：DashScope text-embedding-v2（1536维）
• 元数据：{source, timestamp, topic, importance}
集合2：conversations
• 用途：存储对话记录的embedding
• 预期数据量：数千至数万条
• Embedding：DashScope text-embedding-v2（1536维）
• 元数据：{session*id, user*id, role, timestamp}
⚠️ ECS实战关键教训：
ShuyuanVerse的conversations集合与long*term*memory集合分离，search*long*term只检索long*term*memory集合，对话记录检索入口缺失。ShuyuanCore的解决方案：
• 提供统一的search\_memory()接口，默认同时搜索两个集合
• 或将所有数据存入一个集合，用metadata区分类型
• 推荐方案：统一集合 + metadata区分，避免检索入口缺失问题
## 四、关键数据流
### 4.1 对话主流程
用户消息 → Gateway → Agent.chat()
→ 加载身份（CORE.md/人格编码 + 当前身份）
→ 注入核心记忆到system prompt
→ 查询工作记忆（活跃项目、近期待办）
→ 检索相关历史（FTS5 + ChromaDB向量）
→ 匹配相关技能（因果图推理）
→ 预测用户下一步需求
→ 判断执行模式（简单/复杂，用户可选快速/平衡/深度）
→ 执行（三LLM分工：主LLM交互+工具LLM解析+复盘LLM异步）
→ 风格保护检测（drift\_threshold=0.25）
→ 审查Agent质量检查（drift\_threshold=0.15）
→ 返回回复
→ 后台：更新记忆、保存长期记忆到ChromaDB、提炼技能、更新用户模型、预测反馈、自演化检查
### 4.2 技能提炼流程
任务完成 → 判断是否值得提炼（任务难度驱动）→ 提炼SKILL.md → 因果抽取（9字段）→
更新因果图 → 质量门控 → 存入技能库
### 4.3 人格编译流程
输入资料（100字~100万字）→ 风格编码器(256维, 7维度) + 决策锚点(256维, 绑定) →
人格档案（7项，含500-1000条语言样本）→ 存储为profile → 可注入任意Agent实例
### 4.4 长期记忆写入流程
对话结束
│
▼
[1] 提取关键信息（复盘LLM调用）
- 提取用户偏好、决策、事实性信息
│
▼
[2] 生成Embedding
- DashScope text-embedding-v2（1536维）
│
▼
[3] 去重检查
- 计算新embedding与ChromaDB已有记录的余弦相似度
- 相似度 > 0.95 → 视为重复，跳过
│
▼
[4] 写入ChromaDB
- 写入conversations集合（对话记录）
- 如果是结构化知识 → 同时写入long\_term\_memory集合
│
▼
[5] 同时写入SQLite
- 消息原文存入messages表
- FTS5索引用于关键词检索
## 五、依赖清单
### 核心依赖
• fastapi + uvicorn（Web框架）
• httpx（异步HTTP客户端，调用LLM + DashScope Embedding API）
• sqlite3（内置，对话历史+FTS5）
• aiosqlite（异步SQLite）
• pyyaml（配置文件）
• click 或 typer（CLI）
• chromadb（向量检索，必须依赖）
### Embedding依赖（二选一）
• dashscope（DashScope API，默认方案，text-embedding-v2 1536维）
• sentence-transformers（本地降级方案，all-MiniLM-L6-v2 384维，占~400MB内存）
### 人格编译依赖（可选）
• torch（PyTorch版风格编码器+决策锚点，256维，占~2GB）
• numpy（NumPy版风格编码器+决策锚点，256维，轻量替代，无额外内存开销）
### 可选依赖
• docker（执行沙箱，可选，没有则本地执行）
• python-telegram-bot（Telegram适配）
• playwright（浏览器自动化）
### 开发依赖
• pytest + pytest-asyncio
• ruff（格式化和lint）
## 六、配置结构（config/default.yaml）
**// yaml**agent:
name: ShuyuanCore
mode: general # general | persona
models:
default: dashscope/qwen-max
embedding: dashscope/text-embedding-v2
embedding\_dimensions: 1536
routing:
code: deepseek/deepseek-chat
chat: dashscope/qwen-max
math: dashscope/qwen-max
embedding: dashscope/text-embedding-v2
tool: dashscope/qwen-turbo # 工具LLM，轻量模型
review: deepseek/deepseek-chat # 复盘LLM，便宜模型
providers:
dashscope:
api\_key: ${DASHSCOPE\_API\_KEY}
base\_url: https://dashscope.aliyuncs.com/compatible-mode/v1
model: qwen-max
embedding\_model: text-embedding-v2
deepseek:
api\_key: ${DEEPSEEK\_API\_KEY}
base\_url: https://api.deepseek.com/v1
model: deepseek-chat
openai:
api\_key: ${OPENAI\_API\_KEY}
base\_url: https://api.openai.com/v1
ollama:
base\_url: http://localhost:11434
memory:
core\_memory\_limit: 2200
user\_model\_limit: 1375
consolidation\_threshold: 0.8
fts5\_search\_limit: 10
vector\_search\_limit: 5
working:
expire\_days: 30 # 工作记忆过期天数
auto\_cleanup: true # 自动清理已完成项目
chroma:
persist\_directory: data/chroma
client\_type: persistent
collections:
long\_term\_memory:
metadata: {source, timestamp, topic, importance}
conversations:
metadata: {session\_id, user\_id, role, timestamp}
embedding:
provider: dashscope
dedup\_threshold: 0.95
batch\_size: 20
skills:
auto\_extract: true
progressive\_disclosure: true
curator\_interval\_days: 7 # 7天固定触发
curator\_max\_iterations: 3 # 最多3次迭代
stale\_days: 30
archive\_days: 90
difficulty\_driven: true # 任务难度驱动提炼判断
persona:
drift\_threshold: 0.25
review\_drift\_threshold: 0.15
enable\_proactive: false
style\_dimensions: 256
anchor\_dimensions\_pytorch: 256
anchor\_dimensions\_numpy: 256 # NumPy版也统一256维
bound\_components: true # 风格编码器+决策锚点绑定
min\_input\_chars: 100 # 人格编译最低100字
max\_input\_chars: 1000000 # 最高100万字
language\_samples\_min: 500 # 语言样本最少500条
language\_samples\_max: 1000 # 最多1000条
style\_7\_dimensions:
- formality
- warmth
- directness
- playfulness
- detail\_orientation
- emotional\_expression
- pace
protection\_levels:
normal: 0.15
mild\_drift: 0.25
severe\_drift: 3
identity\_file: CORE.md # 原SOUL.md
identity:
max\_identities: 5 # 最多5个身份
switch\_methods: # 切换方式
- natural\_language # 自然语言
- slash\_command # /profile <name>
shared\_layers: # 全局共享的记忆层
- L3
- L4
independent\_layers: # 身份独立的记忆层
- L1
- L6
evolution:
trigger\_days: 7 # 7天窗口
trigger\_count: 40 # 40次同类任务触发
max\_active\_modules: 5 # 同时活跃不超5个
fuse\_threshold: 3 # 3天内协作3次以上→融合
archive\_inactive\_days: 14 # 14天未激活→归档
prediction:
enable\_proactive: true # 主动发起
feedback\_loop: true # 预测准确度反馈
security:
require\_approval: true
sandbox: docker
audit\_log: true
ip\_whitelist: []
env\_expose: false
data\_encryption: true # 记忆/API Key/对话加密
network\_isolation: true # 网络访问白名单
privacy\_desensitize: true # 隐私脱敏
session\_isolation: true # 多用户会话隔离
operation\_rollback: true # 操作回滚
rate\_limit: true # 速率限制
sensitive\_confirm: true # 敏感操作二次确认
output\_filter: true # 模型输出过滤
permission\_grading: true # 权限分级
gateway:
platforms:
cli: { enabled: true }
api: { enabled: true, port: 8000 }
telegram: { enabled: false, token: ${TELEGRAM\_BOT\_TOKEN} }
wechat: { enabled: false }
wechat\_work: { enabled: false }
feishu: { enabled: false }
dingtalk: { enabled: false }
qq: { enabled: false }
history:
per\_page: 50
max\_per\_page: 200
cache\_recent: 20
cron:
enabled: true
check\_interval: 60
condition\_trigger: true # 条件触发
task\_chain: true # 任务链
deploy:
host: 0.0.0.0
port: 8005
workers: 1
log\_level: info
log\_rotation:
max\_size: 50MB
backup\_count: 5
health\_check:
enabled: true
endpoint: /health
interval: 30
methods: # 部署方式
- curl\_bash
- pip
- homebrew
- docker
- source
- cloud\_one\_click
## 七、CLI命令设计
**// bash**agentx run # 启动交互式CLI对话
agentx serve # 启动API服务器
agentx gateway # 启动消息平台Gateway
agentx setup # 首次设置向导
agentx model # 配置/切换模型
agentx tools # 配置工具集
agentx skills list # 列出技能
agentx skills search # 搜索技能（含社区市场）
agentx skills create # 手动创建技能
agentx skills install # 安装社区技能
agentx persona compile # 编译数字人格（100字~100万字输入）
agentx persona export # 导出人格档案
agentx profile # 切换身份（自然语言或名称）
agentx migrate # 从Hermes/OpenClaw/ShuyuanVerse迁移
agentx doctor # 诊断问题（含ChromaDB健康检查）
agentx update # 更新版本
agentx deploy # 部署管理
agentx memory stats # 记忆系统统计
agentx memory reindex # 重建ChromaDB索引
agentx memory backfill # 从SQLite历史数据回填ChromaDB
## 八、开发路线
**起飞阶段**：完整实现所有能力，不分Phase，不设时间表。
所有模块一次性完整实现，不做MVP，不分阶段交付。
## 九、与ShuyuanVerse的关系及代码资产
### 9.1 关系定位
• **ShuyuanVerse**：数字分身产品，专注人格编译和风格保持，已部署运行在ECS上
• **ShuyuanCore**：通用Agent框架，支持六层记忆、因果技能图、多智能体协作等
• **定位区别**：ShuyuanVerse是垂直产品，ShuyuanCore是通用框架；ShuyuanCore从零新建，不复用ShuyuanVerse代码，但可移植逻辑
### 9.2 ShuyuanVerse代码资产概况
ECS侦查实测数据（2026-05-24）：
|  |  |
| --- | --- |
| **指标** | **值** |
| 代码总量 | **50,231行** Python |
| 后端路径 | /opt/shuyuanverse/backend/app/ |
| 前端路径 | /opt/shuyuanverse/frontend/（React + Vite） |
| 运行方式 | uvicorn:8005 + nginx:80 |
| 数据库 | 6个SQLite文件，3处副本散落 |
### 9.3 可移植代码资产评估
|  |  |  |  |
| --- | --- | --- | --- |
| **模块** | **代码量** | **可移植性** | **说明** |
| 风格编码器 (style\_encoder) | 2,342行 | ⭐⭐⭐⭐ | 核心算法可直接移植，7维度风格画像 |
| 决策锚点 (decision\_anchor) | 5,033行 | ⭐⭐⭐⭐ | PyTorch+NumPy双实现，需适配架构 |
| 风格防护 (style\_protection) | 502行 | ⭐⭐⭐⭐⭐ | 松刹车流水线，最干净可直接移植 |
| 对话引擎 (dialogue) | 9,839行 | ⭐⭐ | 多Agent协作+状态机，架构差异大需大改 |
| 漂移检测 (drift) | 3,609行 | ⭐⭐ | 可移植部分约一半 |
| 记忆系统 (memory) | 1,995行 | ⭐⭐ | 需从4层扩展到6层 |
| 人格系统 (persona) | 8,072行 | ⭐⭐ | 需重新设计 |
| Skill系统 (skill) | 3,291行 | ⭐ | 因果技能图全新架构需从头开发 |
| RAG检索 (rag) | 2,618行 | ⭐⭐ | 检索器可参考，存储层需全部换 |
| 多平台采集 (collectors) | 2,760行 | ⭐ | 需要重新开发 |
| LLM服务 (llm) | 614行 | ⭐⭐⭐⭐⭐ | 主备切换逻辑通用 |
### 9.4 移植原则
• **逻辑移植，代码重写**：理解ShuyuanVerse的算法思路，用ShuyuanCore的架构风格重新实现
• **不做依赖拷贝**：不直接复制ShuyuanVerse的import链，避免带入不需要的依赖
• **保留参数验证**：ShuyuanVerse中经过实战验证的参数（如drift*threshold=0.25, review*drift\_threshold=0.15）直接采用
• **修复已知问题**：移植时同步修复ECS实战中发现的问题（如ChromaDB集合分离导致检索缺失、重复记忆未去重等）
• **架构优先**：以新架构为准，旧代码的架构设计不带入；如果旧代码的某个功能和架构冲突，改代码不是改架构
## 十、部署架构
基于ECS实战经验，ShuyuanVerse部署存在严重缺陷：无进程守护、无HTTPS、无自动重启、无健康检查。ShuyuanCore必须从设计之初就建立完善的部署架构。
### 10.1 部署架构总览
┌─────────────────┐
│ 用户/客户端 │
└────────┬────────┘
         │ HTTPS (443)
┌────────▼────────┐
│ Nginx │
│ (反向代理+SSL) │
└────────┬────────┘
         │ HTTP (8005)
┌────────▼────────┐
│ ShuyuanCore │
│ (uvicorn) │
│ systemd管理 │
└────────┬────────┘
         │
┌────────┴────────┐
│ │
┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
│ SQLite+FTS5 │ │ ChromaDB │ │ 文件系统 │
│ (state.db) │ │(持久化) │ │(记忆/技能) │
└───────────────┘ └──────────┘ └─────────────┘
### 10.2 systemd服务管理
ShuyuanCore的systemd服务（deploy/systemd/agentx.service）：
**// ini**[Unit]
Description=ShuyuanCore Server
After=network.target
[Service]
Type=simple
User=agentx
Group=agentx
WorkingDirectory=/opt/agentx
ExecStart=/opt/agentx/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 --workers 1
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/opt/agentx/.env
# 安全限制
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/agentx/data /opt/agentx/logs
[Install]
WantedBy=multi-user.target
### 10.3 Nginx反向代理 + HTTPS
ShuyuanCore的Nginx配置（deploy/nginx/agentx.conf）：
**// nginx**# HTTP → HTTPS 重定向
server {
listen 80;
server\_name agentx.example.com;
return 301 https://$server\_name$request\_uri;
}
# HTTPS 主配置
server {
listen 443 ssl http2;
server\_name agentx.example.com;
# Let's Encrypt SSL
ssl\_certificate /etc/letsencrypt/live/agentx.example.com/fullchain.pem;
ssl\_certificate\_key /etc/letsencrypt/live/agentx.example.com/privkey.pem;
ssl\_protocols TLSv1.2 TLSv1.3;
# 前端静态文件
location / {
root /opt/agentx/frontend/dist;
try\_files $uri $uri/ /index.html;
}
# API反向代理
location /api/ {
proxy\_pass http://127.0.0.1:8005/api/;
proxy\_set\_header Host $host;
proxy\_set\_header X-Real-IP $remote\_addr;
proxy\_set\_header X-Forwarded-For $proxy\_add\_x\_forwarded\_for;
proxy\_set\_header X-Forwarded-Proto $scheme;
# SSE支持
proxy\_buffering off;
proxy\_cache off;
proxy\_read\_timeout 300s;
}
# 健康检查端点
location /health {
proxy\_pass http://127.0.0.1:8005/health;
}
}
### 10.4 Docker Compose一键部署
**// yaml**version: '3.8'
services:
agentx:
build:
context: ..
dockerfile: deploy/Dockerfile
ports:
- "8005:8005"
volumes:
- ../data:/app/data
- ../config:/app/config
env\_file:
- ../.env
restart: always
healthcheck:
test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
interval: 30s
timeout: 10s
retries: 3
start\_period: 30s
nginx:
image: nginx:alpine
ports:
- "80:80"
- "443:443"
volumes:
- ./nginx/agentx.conf:/etc/nginx/conf.d/default.conf
- /etc/letsencrypt:/etc/letsencrypt
- ../frontend/dist:/usr/share/nginx/html
depends\_on:
agentx:
condition: service\_healthy
restart: always
### 10.5 健康检查端点
ShuyuanCore健康检查（main.py）：
**// python**@app.get("/health")
async def health\_check():
"""健康检查端点，供systemd/nginx/监控使用"""
checks = {
"status": "healthy",
"app\_name": "ShuyuanCore",
"version": "3.0.0",
"database": "connected" if await check\_sqlite() else "error",
"chromadb": "connected" if await check\_chromadb() else "error",
"llm": "configured" if await check\_llm() else "error",
"disk\_usage": get\_disk\_usage(),
"memory\_usage": get\_memory\_usage(),
"uptime": get\_uptime(),
}
# 磁盘超过85%或内存超过90%降级为degraded
if checks["disk\_usage"] > 85 or checks["memory\_usage"] > 90:
checks["status"] = "degraded"
# 数据库或ChromaDB不可用降级为unhealthy
if checks["database"] == "error" or checks["chromadb"] == "error":
checks["status"] = "unhealthy"
status\_code = 200 if checks["status"] != "unhealthy" else 503
return JSONResponse(content=checks, status\_code=status\_code)
### 10.6 日志轮转
ShuyuanCore日志配置（/etc/logrotate.d/agentx）：
/opt/agentx/data/logs/\*.log {
daily
rotate 7
compress
delaycompress
missingok
notifempty
maxsize 50M
copytruncate
}
Python应用日志配置：
**// python**import logging
from logging.handlers import RotatingFileHandler
handler = RotatingFileHandler(
'data/logs/app.log',
maxBytes=50\*1024\*1024, # 50MB
backupCount=5
)
### 10.7 ECS实战对照表
|  |  |  |
| --- | --- | --- |
| **部署项** | **ShuyuanVerse（ECS现状）** | **ShuyuanCore（目标）** |
| 进程管理 | 无（手动uvicorn启动） | systemd（自动重启） |
| 反向代理 | Nginx:80（仅HTTP） | Nginx:80+443（HTTP+HTTPS） |
| SSL证书 | 无 | Let's Encrypt自动续期 |
| 健康检查 | 有/health但无监控 | /health + systemd + 外部监控 |
| 日志管理 | 无轮转，可能撑爆磁盘 | logrotate + RotatingFileHandler |
| 磁盘管理 | 71%已用，三处数据库副本 | 单一数据目录，定期清理 |
| 安全 | fail2ban误封 | IP白名单联动 |
| Docker | 未安装 | Docker Compose可选 |
## 十一、模型路由
ECS实战确认：ShuyuanVerse使用DashScope(qwen-max)作为主模型、DeepSeek(deepseek-chat)作为备选、DashScope text-embedding-v2作为Embedding。ShuyuanCore默认配置对齐，但支持更多模型。
### 11.1 模型路由策略
任务类型 → 模型映射（三LLM分工）：
|  |  |  |
| --- | --- | --- |
| **LLM角色** | **任务** | **模型** |
| 主LLM | 日常对话 | dashscope/qwen-max |
| 主LLM | 代码生成 | deepseek/deepseek-chat |
| 主LLM | 数学推理 | dashscope/qwen-max |
| 主LLM | 人格编译 | dashscope/qwen-max |
| 复盘LLM | 技能提炼、记忆优化、用户模型更新 | deepseek/deepseek-chat |
| 工具LLM | 工具参数构造、结果解析 | dashscope/qwen-turbo |
主备切换（从ShuyuanVerse llm\_service.py移植逻辑）：
• 默认：dashscope → deepseek（主模型失败自动切备选）
• 切换条件：API超时(30s) / 5xx错误 / 连续3次429(限流)
• 自动恢复：5分钟后切回主模型
### 11.2 Embedding方案选择
|  |  |  |
| --- | --- | --- |
| **对比项** | **DashScope text-embedding-v2** | **sentence-transformers** |
| 维度 | 1536 | 384 |
| 内存占用 | 0（API调用） | ~400MB |
| 中文效果 | 优秀（阿里优化） | 一般 |
| 离线能力 | 无（需网络） | 有 |
| 成本 | API调用费（极低） | 免费 |
| 部署复杂度 | 低 | 高 |
| ECS实战验证 | ✅ 已验证可用 | ❌ 未使用 |
**结论**：默认使用DashScope API，降级时用sentence-transformers，开发测试时用NumPy随机投影。
## 十二、前端架构要点
### 12.1 ShuyuanVerse前端问题清单
|  |  |  |
| --- | --- | --- |
| **问题** | **严重程度** | **详情** |
| 聊天记录只存localStorage | 🔴 严重 | 无服务器端历史加载，换设备/清缓存丢失 |
| 后端缺history API | 🔴 严重 | 前端定义了getHistory但后端没实现 |
| loadMoreHistory未实现 | 🟡 中等 | 往上翻没有加载更多 |
| localStorage 5MB限制 | 🟡 中等 | 消息多了旧的被截断 |
### 12.2 ShuyuanCore前端架构原则
1. **后端为权威数据源**
◦ 所有对话历史存储在服务器SQLite + ChromaDB
◦ 前端localStorage仅作为展示缓存，非主存储
2. **完整的对话历史API**
◦ GET /api/v1/conversations/{id}/messages?page=1&per\_page=50
◦ 支持 before 参数：加载更早消息（上拉加载更多）
◦ 支持搜索
3. **分页加载策略**
◦ 首次进入对话：加载最近50条消息
◦ 上拉触发：加载更早的50条
◦ 搜索触发：直接搜索服务器
4. **离线降级**
◦ 网络不可用时展示localStorage缓存
◦ 网络恢复后自动同步
## 十三、已知问题与经验教训
### 13.1 ChromaDB实战经验
**问题1：自研VectorStore不可靠**
• 现象：ShuyuanVerse原方案用自研VectorStore（JSON文件存储），性能差且不持久
• 修复：替换为ChromaDB PersistentClient
• 教训：向量存储不要自己造轮子
**问题2：集合分离导致检索入口缺失**
• 现象：conversations集合（3260条）与long*term*memory集合（64条）分离，search*long*term只检索long*term*memory
• 影响：用户说过的重要信息在对话记录中，但Agent搜索时找不到
• 教训：必须提供统一检索接口
**问题3：重复记忆未去重**
• 现象：ChromaDB中存在重复记录，如"你不想知道我在做什么方向吗"重复13次
• 修复：写入前计算embedding与已有记录余弦相似度，超过0.95视为重复
• 教训：向量数据库写入必须做去重
**问题4：历史数据回填耗时**
• 现象：3260条对话记录需逐条通过DashScope API生成embedding
• 解决方案：nohup后台运行、断点续传、批量请求
• 教训：回填脚本必须支持断点续传
### 13.2 部署实战经验
**问题5-9**：无进程守护、无HTTPS、fail2ban误封、磁盘空间紧张、.env泄露
• 对策：systemd、Let's Encrypt、IP白名单、单数据目录、.gitignore
### 13.3 代码架构经验
**问题10：Feature Flags全部默认开启**
• 现象：7个Feature Flags全部默认True，但用户已决定回退松刹车策略
• 教训：Feature Flags默认值必须与策略对齐
**问题11：多数据库副本混乱**
• 现象：6个SQLite文件，3处不同目录的副本
• 教训：只用一个state.db
**问题12：前端定义了API但后端没实现**
• 现象：前端定义了getHistory、loadMoreHistory等方法，但后端没有对应API
• 教训：API设计必须前后端对齐，后端先行（API-First）
### 经验教训汇总表
|  |  |  |
| --- | --- | --- |
| **编号** | **教训** | **ShuyuanCore对策** |
| 1 | 向量存储不要自研 | ChromaDB PersistentClient |
| 2 | 集合分离导致检索缺失 | 统一检索接口 |
| 3 | 写入不去重导致数据膨胀 | 相似度>0.95跳过 |
| 4 | 回填脚本无断点续传 | 记录已处理ID |
| 5 | 无进程守护 | systemd + Restart=always |
| 6 | 无HTTPS | Let's Encrypt |
| 7 | fail2ban误封 | IP白名单联动 |
| 8 | 磁盘空间紧张+多副本 | 单数据目录 + 磁盘监控 |
| 9 | .env泄露 | .gitignore + 环境变量优先 |
| 10 | Feature Flags默认值错误 | 默认值与策略对齐 |
| 11 | 多数据库副本混乱 | 单一state.db |
| 12 | 前端API后端缺失 | API-First开发 |
## 十四、风险与注意事项
1. **松刹车参数不要改**：drift*threshold=0.25, enable*proactive=False（ECS实战验证）
2. **审查Agent阈值更严格**：review*drift*threshold=0.15，形成0.15→0.25的梯度保护
3. **风格编码器+决策锚点必须绑定使用**：不可单独使用（ECS实战验证）
4. **决策锚点维度统一256维**：NumPy版也从128维改为256维
5. **技能提炼判断用任务难度驱动**：不是工具调用数量，是"尝试多种方法/用户纠正/跨领域知识"
6. **Curator最多3次迭代**：3次后仍不确定的标记"需人工审查"
7. **Curator 7天固定触发**：不再等空闲
8. **子代理最多5个**：防止资源过度消耗
9. **多视角2-5个**：Agent根据问题复杂度自定，不固定3个
10. **因果图用JSON**：不引入Neo4j，轻量起步
11. **异步优先**：所有I/O操作用async，后台更新不阻塞对话
12. **ChromaDB写入必须去重**：相似度>0.95视为重复
13. **Embedding方案默认DashScope API**：不占本地内存，效果更好
14. **对话历史API必须完整**：后端先行，分页+搜索
15. **部署从第一天就完善**：systemd、HTTPS、健康检查、日志轮转
16. **单一数据目录**：避免数据库副本散落
17. **所有文件人可读**：记忆用Markdown、技能用Markdown+YAML、配置用YAML
18. **模块可独立禁用**：没有人格编译也能跑，没有ChromaDB也能降级到纯FTS5
19. **自演化活跃模块不超过5个**：防止模块过多混乱
20. **先做单用户**：关系记忆先做单用户决策记录
21. **人格编译输入100字~100万字**：最低100字，推荐5万字以上
22. **语言样本500-1000条**：按场景分类
*文档结束 | ShuyuanCore 技术架构方案 v1.0 | 2026-05-26*
本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
