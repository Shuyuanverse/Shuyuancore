# ShuyuanCore API 接口文档
版本：v1.0-rev2 | 日期：2026-05-26
## 一、通用规范
### 1.1 基础信息
- **Base URL**：`https://agentx.example.com/api/v1`
- **认证方式**：`Authorization: Bearer <token>`（JWT Token）
- **Content-Type**：`application/json`
- **统一响应格式**：
|  |  |  |
| --- | --- | --- |
| **字段** | **类型** | **说明** |
| code | integer | 0=成功，非0=错误（见错误码表） |
| message | string | 状态描述 |
| data | object/array/null | 业务数据 |
| request\_id | string | 请求追踪ID（UUID） |
**// json**{
"code": 0,
"message": "success",
"data": { ... },
"request_id": "uuid"
}
### 1.2 错误码
|  |  |  |  |
| --- | --- | --- | --- |
| **错误码** | **含义** | **HTTP状态码** | **示例场景** |
| 0 | 成功 | 200 | - |
| 1001 | 参数缺失 | 400 | 缺少必填参数 |
| 1002 | 参数格式错误 | 400 | JSON格式错误、参数类型不对 |
| 1003 | 资源不存在 | 404 | 会话ID不存在 |
| 1004 | 权限不足 | 403 | 普通用户访问admin接口 |
| 1005 | 幂等键重复 | 409 | 重复审批请求（同approval_id） |
| 2001 | 模型调用失败 | 502 | LLM API超时或5xx错误 |
| 2002 | 模型切换失败 | 400 | 目标模型不存在或未配置 |
| 3001 | 记忆操作失败 | 500 | SQLite/ChromaDB写入失败 |
| 4001 | 技能不存在 | 404 | 技能ID找不到 |
| 4002 | 技能市场连接失败 | 502 | agentskills.io无法访问 |
| 5001 | 人格编译失败 | 500 | 输入材料不足或格式错误 |
| 6001 | 工具执行失败 | 500 | 终端命令返回非零退出码 |
| 6002 | 工具审批超时 | 408 | 15分钟内未审批 |
| 6003 | 工具危险操作被拒绝 | 403 | /deny了审批请求 |
| 7001 | MCP连接失败 | 502 | MCP服务器无法连接 |
| 7002 | MCP工具不存在 | 404 | 请求的MCP工具未注册 |
| 8001 | 定时任务创建失败 | 400 | cron表达式无效 |
| 9001 | 审批不存在 | 404 | approval_id无效 |
| 9002 | 危险操作需审批 | 202 | 返回approval_id等待确认 |
| 9003 | MCP连接失败 | 502 | MCP服务器stdio命令不存在 |
| 10001 | 会话不存在 | 404 | 会话ID无效 |
| 10002 | 消息不存在 | 404 | 消息ID无效 |
| 10003 | 会话已归档 | 409 | 无法向已归档会话发送消息 |
| 10004 | 会话已删除 | 409 | 无法操作已删除会话 |
| 11000 | 配置缺失 | 500 | 配置文件不存在或解析失败 |
| 11001 | 配置更新失败 | 400 | 运行时配置验证失败 |
| 11002 | 配置持久化失败 | 500 | 写入default.yaml失败 |
### 1.3 认证说明
**// http**Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Token获取：通过CLI `agentx auth login` 或 首次setup生成
用户数据隔离原则（v1.0-rev2补充）：每个用户的对话历史、记忆（L1-L6）、技能、人格档案、身份完全隔离。user_id 是隔离的标识符，API所有查询必须带 user_id 过滤（从JWT Token解析）。不存在跨用户数据共享，admin角色只用于系统管理操作，不访问用户数据。
### 1.4 分页规范
**游标分页**（v1.0-rev2补充cursor编码格式）：
|  |  |  |
| --- | --- | --- |
| **参数** | **类型** | **说明** |
| limit | integer | 每页数量，默认20，最大100 |
| cursor | string | 游标（base64编码的`created_at_id`格式），首次不传 |
**// json**{
"data": {
"items": [...],
"next_cursor": "MTcxNjY3NjAwMF8xMjM0NTY3OA==",  // base64(created_at + "_" + id)
"has_more": true
}
}
### 1.5 幂等性
POST请求支持幂等（v1.0-rev2补充，approve/deny专用）：
**// http**Idempotency-Key: <unique-key>
同一 approval_id 只能审批一次，重复请求返回首次结果。推荐客户端生成唯一key（如UUID）携带在 Idempotency-Key HTTP 头中。
### 1.6 WebSocket 实时推送
**// ws**wss://agentx.example.com/ws/v1
连接时需在query参数中携带token：
`wss://agentx.example.com/ws/v1?token=<jwt_token>`
消息格式：
**// json**{
"type": "message",      // message/typing/tool_call/error
"data": { ... },
"timestamp": 1716700800000
}
## 二、认证接口
### 2.1 登录
**POST /auth/login**
**// json**{
"username": "admin",
"password": "your-password"
}
**// json**{
"code": 0,
"data": {
"token": "eyJhbGciOiJIUzI1NiIs...",
"expires_at": 1719283200000,
"role": "admin"
}
}
## 三、业务接口
### 3.1 对话管理
#### GET /conversations
获取会话列表
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| status | string | 否 | active/archived/deleted，默认active |
| limit | integer | 否 | 默认20 |
| cursor | string | 否 | 游标 |
| identity_id | string | 否 | 按身份过滤 |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "conv_001",
"title": "Python数据分析",
"message_count": 24,
"current_model": "dashscope/qwen-max",
"identity_id": "default",
"status": "active",
"created_at": 1716604800000,
"updated_at": 1716691200000
}
],
"next_cursor": "MTcxNjY3NjAwMF8xMjM0NTY3OA==",
"has_more": true
}
}
#### POST /conversations
创建会话
**// json**{
"title": "可选，不传则自动生成",
"identity_id": "default",
"model": "dashscope/qwen-max"
}
**// json**{
"code": 0,
"data": {
"id": "conv_002",
"title": "新会话",
"created_at": 1716700800000
}
}
#### GET /conversations/{id}/messages
获取对话消息（分页，支持上拉加载更多）
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| page | integer | 否 | 页码，默认1 |
| per_page | integer | 否 | 每页数量，默认50，最大200 |
| before | string | 否 | 消息ID，加载此ID之前的更早消息（上拉加载更多） |
| after | string | 否 | 消息ID，加载此ID之后的消息（WebSocket断线重连） |
| search | string | 否 | 关键词搜索（FTS5全文检索） |
| role | string | 否 | 过滤角色：user/assistant/system |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "msg_001",
"role": "user",
"content": "帮我分析这个数据",
"tokens_used": 15,
"tool_calls": null,
"metadata": {"model": "qwen-max"},
"created_at": 1716691200000
},
{
"id": "msg_002",
"role": "assistant",
"content": "我来帮您分析...",
"tokens_used": 342,
"tool_calls": [
{"name": "code_exec", "params": "import pandas..."}
],
"metadata": {"model": "qwen-max", "tools_used": ["code_exec"]},
"created_at": 1716691260000
}
],
"total": 24,
"has_more": true
}
}
**// json**{
"code": 10003,
"message": "会话不存在",
"data": {"conversation_id": "conv_xxx"},
"request_id": "uuid"
}
#### GET /conversations/{id}/messages/search
搜索对话内容
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| q | string | 是 | 搜索关键词，FTS5全文检索 |
| cursor | string | 否 | 游标，用于分页（v1.0-rev2补充：cursor格式为base64编码的rank_id组合） |
| limit | integer | 否 | 每页数量，默认20 |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "msg_003",
"role": "assistant",
"content": "这是搜索结果...",
"relevance": 0.92,  // 相关性分数，范围0~1
"created_at": 1716604800000
}
],
"next_cursor": "base64_cursor_string",
"has_more": false
}
}
#### POST /conversations/{id}/messages
发送消息（流式/非流式）
**// json**{
"content": "帮我分析这个CSV文件",
"model": "dashscope/qwen-max", // 可选，覆盖会话默认模型
"stream": true,                 // true=SSE流式，false=同步响应
"temperature": 0.7,             // 可选
"identity_id": "default"        // 可选，覆盖当前身份
}
**流式响应（SSE）**：
**// sse**data: {"type": "thinking", "content": "正在分析文件..."}
data: {"type": "tool_call", "tool": "code_exec", "params": "import pandas..."}
data: {"type": "tool_result", "tool": "code_exec", "result": "..."}
data: {"type": "content", "content": "根据分析结果..."}
data: {"type": "done", "tokens_used": 456}
**非流式响应**：
**// json**{
"code": 0,
"data": {
"id": "msg_003",
"role": "assistant",
"content": "根据分析结果...",
"tokens_used": 456,
"tool_calls": [
{"name": "code_exec", "params": "import pandas...", "result": "..."}
],
"created_at": 1716700800000
}
}
#### DELETE /conversations/{id}
删除会话（软删除）
**// json**{
"code": 0,
"message": "success",
"data": {"deleted": "conv_001", "messages_count": 24}
}
**// json**{
"code": 10003,
"message": "会话不存在",
"data": {"conversation_id": "conv_xxx"},
"request_id": "uuid"
}
**// json**{
"code": 10004,
"message": "会话已删除",
"data": {"conversation_id": "conv_001"},
"request_id": "uuid"
}
v1.0-rev2补充：软删除后将session状态标记为deleted，同时触发ChromaDB中该会话对话记录的异步清理任务（后台运行，不影响接口响应）。
### 3.2 记忆系统
#### GET /memory/core
获取核心记忆（MEMORY.md + USER.md）
**// json**{
"code": 0,
"data": {
"memory": "用户偏好Python...\n项目进展...",
"user": "用户心理状态...\n短期目标...",
"memory_chars": 2100,
"user_chars": 1200,
"consolidation_ratio": 0.72
}
}
#### PATCH /memory/core
更新核心记忆
**// json**{
"memory": "新增偏好：喜欢用FastAPI...",  // 增量追加
"user": "更新了短期目标..."              // 增量追加
}
v1.0-rev2补充：此接口为增量更新，只修改请求体中提供的字段，不会置空未提供的字段。例如只传{"memory": "..."}时，user字段保持原值不变。
**// json**{
"code": 0,
"data": {"updated": true, "memory_chars": 2150, "user_chars": 1200}
}
#### GET /memory/working
获取工作记忆（L2）
**// json**{
"code": 0,
"data": {
"active_projects": ["API文档编写", "数据库设计"],
"recent_todos": [
{"task": "完成用户表设计", "project": "数据库设计", "deadline": "2024-06-01"}
],
"temp_context": {"current_focus": "优化查询性能"},
"priority_overrides": {}
}
}
#### GET /memory/search
语义搜索记忆
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| q | string | 是 | 搜索内容 |
| type | string | 否 | all/long_term/conversation，默认all |
| limit | integer | 否 | 默认10 |
| cursor | string | 否 | 游标（v1.0-rev2补充：cursor格式为base64编码的relevance_id组合） |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "mem_001",
"content": "用户之前提到过...",
"type": "long_term",
"relevance": 0.89,  // v1.0-rev2补充：范围0~1
"source": "conversation_20240520",
"created_at": 1716172800000
}
],
"next_cursor": "base64_cursor_string",
"has_more": false
}
}
#### POST /memory/working/projects/{name}/activate
激活项目
**// json**{
"code": 0,
"data": {"activated": "数据库设计", "context_loaded": true}
}
#### DELETE /memory/working/projects/{name}
标记项目完成（自动清理）
**// json**{
"code": 0,
"data": {"completed": "数据库设计", "cleanup_scheduled": true}
}
### 3.3 技能系统
#### GET /skills
技能列表
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| status | string | 否 | active/stale/archived，默认active |
| type | string | 否 | agent/manual/hub |
| search | string | 否 | 关键词搜索 |
| limit | integer | 否 | 默认20 |
| cursor | string | 否 | 游标 |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "skill_001",
"name": "数据分析",
"description": "使用pandas进行数据分析的标准流程",
"version": "2.0",
"status": "active",
"type": "agent",
"usage_count": 15,
"last_used_at": 1716604800000,
"causal_edges": 3,
"created_at": 1716000000000
}
],
"next_cursor": "...",
"has_more": false,
"total_active": 42,
"total_stale": 5,
"total_archived": 12
}
}
#### GET /skills/{id}
技能详情（含因果图）
**// json**{
"code": 0,
"data": {
"id": "skill_001",
"name": "数据分析",
"description": "使用pandas进行数据分析的标准流程",
"version": "2.0",
"status": "active",
"type": "agent",
"usage_count": 15,
"content": "# 数据分析流程\n1. 读取数据...",
"preconditions": ["有CSV/Excel文件"],
"causality": {
"level0": "读取→清洗→分析→可视化",
"level1": "完整因果链...",
"level2": "详细推理..."
},
"boundaries": ["不适用于实时流数据"],
"failure_modes": ["内存不足导致OOM"],
"dependencies": ["pandas", "numpy"],
"verification": "输出包含统计摘要和图表",
"causal_graph": {
"parents": ["数据读取"],
"children": ["数据可视化", "报告生成"],
"abstracts": ["数据处理"]
},
"created_at": 1716000000000,
"updated_at": 1716604800000
}
}
#### POST /skills/curate
触发Curator审查（dry_run模式）
**// json**{
"dry_run": true  // true=预览，false=实际执行
}
v1.0-rev2补充：dry_run=true时返回preview预览数据，不实际修改技能。
**// json**{
"code": 0,
"data": {
"dry_run": true,
"preview": {
"skills_examined": 45,
"actions": [
{"skill_id": "skill_003", "action": "archive", "reason": "90天未使用"},
{"skill_id": "skill_007", "action": "merge", "target": "skill_001", "reason": "功能重叠"}
],
"retained": 40,
"archived": 3,
"merged": 2
}
}
}
#### GET /skills/market
社区技能市场
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| q | string | 否 | 搜索关键词 |
| category | string | 否 | 分类 |
| sort | string | 否 | popular/recent/rating |
**// json**{
"code": 0,
"data": {
"items": [
{
"name": "web-scraper",
"description": "通用网页数据提取",
"author": "community",
"installs": 1523,
"rating": 4.8,
"last_updated": "2024-05-20"
}
],
"total": 156
}
}
#### POST /skills/market/install
安装社区技能
**// json**{
"name": "web-scraper",
"version": "1.2.0"
}
### 3.4 人格系统
#### POST /personas/compile
编译人格
**// json**{
"name": "张律师",
"source": {
"type": "text",  // text/audio/conversations
"content": "这里放对话记录或文章...",  // 100字~100万字
"language_samples": [
{"text": "正式场合发言...", "scene": "formal"},
{"text": "日常聊天...", "scene": "casual"},
{"text": "决策讨论...", "scene": "decision"}
]
},
"options": {
"style_encoder": "pytorch",  // pytorch/numpy
"anchor_extractor": "pytorch"  // pytorch/numpy
}
}
**// json**{
"code": 0,
"data": {
"id": "per_001",
"name": "张律师",
"status": "compiling",  // compiling/done/error
"progress": 0.45,
"estimated_seconds": 120
}
}
**编译完成推送（WebSocket）**：
**// json**{
"type": "persona_compiled",
"data": {
"id": "per_001",
"name": "张律师",
"profile": {
"values": ["公平正义", "客户利益优先"],
"knowledge_system": ["合同法", "公司法", "知识产权"],
"experience_summary": "15年执业经验，擅长商业纠纷",
"communication_preference": "正式但易懂，善用案例",
"decision_cases": ["案例1: ...", "案例2: ..."],
"language_samples_count": 687,
"taboos": ["绝不泄露客户信息", "不做虚假承诺"]
},
"style_dimensions": {
"formality": 0.85,
"warmth": 0.60,
"directness": 0.75,
"playfulness": 0.20,
"detail_orientation": 0.90,
"emotional_expression": 0.40,
"pace": 0.65
}
}
}
#### GET /personas
人格列表
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "per_001",
"name": "张律师",
"description": "15年执业经验的商业律师",
"status": "active",
"created_at": 1716604800000
}
],
"total": 3
}
}
#### GET /personas/{id}/drift
风格漂移记录
**// json**{
"code": 0,
"data": {
"current_drift": 0.12,
"threshold": 0.25,
"review_threshold": 0.15,
"status": "normal",  // normal/warning/severe
"history": [
{"drift": 0.08, "action": "none", "created_at": 1716518400000},
{"drift": 0.15, "action": "warn", "created_at": 1716604800000}
]
}
}
### 3.5 身份系统
#### GET /identities
获取身份列表
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "idt_work",
"name": "工作助手",
"mode": "general",
"type": "work",
"persona_id": null,
"is_active": true,
"created_at": 1716604800000
},
{
"id": "idt_zhang",
"name": "张律师",
"mode": "persona",
"type": "custom",
"persona_id": "per_001",
"is_active": false,
"created_at": 1716604800000
}
],
"max_identities": 5,
"active_count": 2
}
}
v1.0-rev2补充：响应中每个identity增加profile_id字段，标识该身份关联的人格档案ID（通用模式为null）。
#### POST /identities
创建身份
**// json**{
"name": "李医生",
"mode": "persona",
"persona_id": "per_002"
}
#### POST /identities/{id}/switch
切换身份
**// json**{
"code": 0,
"data": {
"switched_to": "idt_zhang",
"mode": "persona",
"unfinished_tasks": [],  // 未完成任务列表（切换时提醒）
"memory_loaded": true
}
}
#### DELETE /identities/{id}
删除身份（仅允许删除通用模式身份；人格模式身份需先解绑人格）
**// json**{
"code": 1004,
"message": "人格模式身份需先解绑人格",
"data": {"identity_id": "idt_zhang", "persona_id": "per_001"}
}
### 3.6 定时任务
#### GET /jobs
任务列表
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| status | string | 否 | active/paused/all |
| type | string | 否 | cron/condition/chain |
| limit | integer | 否 | 默认20 |
**// json**{
"code": 0,
"data": {
"items": [
{
"id": "job_001",
"schedule": "0 8 * * *",
"prompt": "生成每日新闻摘要",
"deliver_to": ["telegram", "wechat"],
"is_active": true,
"last_run_at": 1716700800000,
"next_run_at": 1716787200000,
"has_chain": false
}
],
"next_cursor": null,
"has_more": false
},
"request_id": "uuid"
}
#### POST /jobs
创建任务
**请求体**：
**// json**{
"schedule": "每天早上8点",
"prompt": "生成每日新闻摘要并发送到Telegram",
"deliver_to": ["telegram", "wechat"],
"skill": "news-briefing",
"condition_trigger": null,
"chain_next_job_id": null
}
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| schedule | string | 是 | cron表达式或自然语言。自然语言示例："每天早上8点"→解析为 0 8 \* \* \*，"每周一上午9点"→解析为 0 9 \* \* 1。解析失败返回错误码 8001 |
| prompt | string | 是 | 执行提示 |
| deliver\_to | array | 否 | 投递平台列表 |
| skill | string | 否 | 预加载技能 |
| condition\_trigger | object | 否 | 条件触发配置，JSON schema：{"type": "cpu\_usage", "threshold": 80, "operator": ">"} |
| chain\_next\_job\_id | string | 否 | 任务链：下一步任务ID |
**错误响应**：
v1.0-rev2补充：错误码8001的完整错误响应包含reason字段。
**// json**{"code": 8001, "message": "cron表达式无效", "data": {"schedule": "每天早上8点", "reason": "无法解析"}, "request_id": "uuid"}
#### GET /jobs/{id}
获取任务详情
#### PUT /jobs/{id}
更新任务
**请求体**：
**// json**{
"schedule": "0 9 * * *",
"prompt": "更新后的提示"
}
#### DELETE /jobs/{id}
删除任务
#### POST /jobs/{id}/trigger
手动触发任务
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"triggered": "job_001", "result": "执行成功"}, "request_id": "uuid"}
### 3.7 工具系统
#### GET /tools
工具列表
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"items": [
{"name": "terminal", "description": "终端命令执行", "dangerous": true, "toolset": "system"},
{"name": "file_ops", "description": "文件操作", "dangerous": false, "toolset": "system"},
{"name": "web", "description": "网页搜索提取", "dangerous": false, "toolset": "web"}
],
"total": 29
},
"request_id": "uuid"
}
#### POST /tools/{name}/execute
执行工具
**请求体**：
**// json**{
"params": {"command": "ls -la"},
"auto_approve": false
}
**成功响应（需审批）**：
**// json**{"code": 9002, "message": "危险操作需审批", "data": {"approval_id": "apr_001", "tool": "terminal"}, "request_id": "uuid"}
**成功响应（已执行）**：
**// json**{"code": 0, "message": "success", "data": {"result": "文件列表...", "execution_time_ms": 120}, "request_id": "uuid"}
#### GET /tools/mcp/servers
MCP服务器列表
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"servers": [
{"name": "filesystem", "status": "connected", "tools_count": 5},
{"name": "github", "status": "disconnected", "tools_count": 0}
]
},
"request_id": "uuid"
}
#### POST /tools/mcp/connect
连接MCP服务器
**请求体**：
**// json**{
"name": "github",
"type": "stdio",
"command": "mcp-server-github",
"env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
}
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"connected": "github", "tools_discovered": 8}, "request_id": "uuid"}
**错误响应**：
**// json**{"code": 9003, "message": "MCP连接失败", "data": {"server": "github", "reason": "命令不存在"}, "request_id": "uuid"}
### 3.8 模型管理
#### GET /models
可用模型列表
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"providers": [
{"name": "dashscope", "models": ["qwen-max", "qwen-turbo", "text-embedding-v2"]},
{"name": "deepseek", "models": ["deepseek-chat"]},
{"name": "openai", "models": ["gpt-4o", "gpt-4o-mini"]}
],
"total_models": 200
},
"request_id": "uuid"
}
#### GET /models/current
当前使用模型
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"main": "dashscope/qwen-max",
"review": "deepseek/deepseek-chat",
"tool": "dashscope/qwen-turbo",
"embedding": "dashscope/text-embedding-v2"
},
"request_id": "uuid"
}
#### PUT /models/switch
切换模型
**请求体**：
**// json**{
"role": "main",
"model": "openai/gpt-4o"
}
#### GET /models/routing
获取路由规则
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"rules": [
{"task_type": "chat", "model": "dashscope/qwen-max"},
{"task_type": "code", "model": "deepseek/deepseek-chat"},
{"task_type": "math", "model": "dashscope/qwen-max"}
]
},
"request_id": "uuid"
}
### 3.9 自演化
#### GET /evolution/modules
获取模块列表
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| status | string | 否 | 状态过滤：active/archived，默认active |
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"items": [
{
"id": "mod_001",
"name": "code_reasoning",
"trigger_count": 42,
"trigger_window_start": 1716096000000,
"status": "active",
"last_activated_at": 1716700800000,
"created_at": 1716096000000
}
],
"active_count": 2,
"max_active": 5
},
"request_id": "uuid"
}
#### GET /evolution/history
演化历史（游标分页）
**查询参数**：
|  |  |  |  |
| --- | --- | --- | --- |
| **参数** | **类型** | **必填** | **说明** |
| limit | integer | 否 | 每页数量，默认20，最大100 |
| cursor | string | 否 | 游标 |
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"items": [
{"type": "born", "module": "code_reasoning", "trigger_count": 40, "timestamp": 1716096000000},
{"type": "fused", "modules": ["code_reasoning", "arch_analysis"], "result": "arch_design", "timestamp": 1716355200000}
],
"next_cursor": "1716096000000_1",
"has_more": true
},
"request_id": "uuid"
}
#### POST /evolution/modules/{id}/archive
手动归档模块
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"archived": "mod_003"}, "request_id": "uuid"}
#### POST /evolution/modules/{id}/activate
重新激活已归档模块
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"activated": "mod_003"}, "request_id": "uuid"}
### 3.10 预测式建模
#### GET /prediction/user-model
获取用户心理模型
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"state": "专注工作中",
"short_term_goals": ["完成API文档", "完成数据库Schema"],
"long_term_goals": ["ShuyuanCore上线"],
"decision_patterns": [{"pattern": "偏好轻量级方案", "confidence": 0.85}],
"knowledge_gaps": ["Kubernetes部署"],
"predicted_next": "开始写数据库Schema"
},
"request_id": "uuid"
}
#### GET /prediction/next
获取预测的下一步需求
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"prediction": "开始写数据库Schema",
"confidence": 0.78,
"suggested_actions": ["准备DDL语句", "定义索引策略"]
},
"request_id": "uuid"
}
#### GET /prediction/accuracy
预测准确度统计
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"total_predictions": 120,
"correct_predictions": 89,
"accuracy": 0.742,
"last_7d_accuracy": 0.81
},
"request_id": "uuid"
}
### 3.11 系统
#### GET /health
健康检查（无需认证）
**成功响应**：
**// json**{
"status": "healthy",
"app_name": "ShuyuanCore",
"version": "1.0.0",
"database": "connected",
"chromadb": "connected",
"llm": "configured",
"disk_usage": 45,
"memory_usage": 62,
"uptime": 86400
}
#### GET /api/v1/status
系统状态
**认证**：Bearer Token
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"version": "1.0.0",
"uptime": 86400,
"active_conversations": 3,
"total_messages": 15200,
"active_modules": 2,
"pending_approvals": 1,
"background_tasks": ["curate_001"]
},
"request_id": "uuid"
}
#### GET /api/v1/config
获取配置（脱敏后）
**认证**：Bearer Token (admin)
脱敏规则：api_key、secret、password、token 等敏感字段替换为 "***"。api_key_env 字段仅存储环境变量名（如 DASHSCOPE_API_KEY），不包含敏感信息，直接返回原值。
**成功响应**：
**// json**{
"code": 0,
"message": "success",
"data": {
"agent": {"name": "ShuyuanCore", "mode": "general"},
"models": {"default": "dashscope/qwen-max"},
"security": {"sandbox": "docker", "audit_log": true},
"database": {"path": "data/state.db", "api_key": "***"}
},
"request_id": "uuid"
}
#### PUT /api/v1/config
更新配置（需admin权限）
**行为说明**：修改仅影响内存中的运行时配置，立即生效但**重启后丢失**。如需持久化，必须同时修改 config/default.yaml 文件并重启服务。
**请求体**：
**// json**{
"agent": {"mode": "persona"},
"security": {"sandbox": "local"}
}
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"updated": ["agent.mode", "security.sandbox"], "persisted": false}, "request_id": "uuid"}
#### POST /api/v1/config/reload
从配置文件重新加载配置（需admin权限）
将 config/default.yaml 中的配置重新加载到内存，覆盖运行时的临时修改。用于持久化配置变更后生效。
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"reloaded": true, "source": "config/default.yaml"}, "request_id": "uuid"}
**错误响应**：
**// json**{"code": 11000, "message": "配置缺失", "data": {"file": "config/default.yaml", "error": "文件不存在"}, "request_id": "uuid"}
**// json**{"code": 1002, "message": "参数格式错误", "data": {"file": "config/default.yaml", "error": "YAML解析失败：第5行缩进错误"}, "request_id": "uuid"}
#### POST /api/v1/approve
审批危险操作（支持幂等键）
**认证**：Bearer Token (admin)
支持幂等键（Idempotency-Key HTTP头），防止重复审批。同一 approval_id 只能审批一次，重复请求返回首次结果。
**请求头**：建议携带 Idempotency-Key: <unique-key>
**请求体**：
**// json**{
"approval_id": "apr_001",
"reason": "确认执行"
}
**成功响应**：
**// json**{"code": 0, "message": "success", "data": {"approved": "apr_001", "executed": true}, "request_id": "uuid"}
**错误响应**（重复审批）：
**// json**{"code": 1005, "message": "幂等键重复", "data": {"approval_id": "apr_001", "previous_status": "approved"}, "request_id": "uuid"}
#### POST /api/v1/deny
拒绝危险操作（支持幂等键）
**认证**：Bearer Token (admin)
同 approve，支持幂等键防止重复操作。
**请求体**：
**// json**{
"approval_id": "apr_001",
"reason": "拒绝执行"
}
## 四、Changelog
|  |  |  |
| --- | --- | --- |
| **版本** | **日期** | **变更** |
| v1.0 | 2026-05-26 | 初始版本，覆盖全部11个模块60+接口 |
| v1.0-rev2 | 2026-05-26 | 修订：认证章节补充用户数据隔离说明；游标分页补充cursor编码格式；PATCH /memory/core明确不会置空未提供字段；搜索接口cursor格式说明；jobs错误码8001补充完整示例含reason；approve/deny补充Idempotency-Key请求头提示；config脱敏规则明确api*key*env返回原值；/config/reload补充错误响应（文件不存在/YAML解析失败）；DELETE /conversations补充ChromaDB异步清理要求；/identities响应增加profile*id字段；/skills/curate dry*run模式返回preview预览；/memory/search补充relevance范围0~1 |
*文档结束 | ShuyuanCore API 接口文档 v1.0 | 2026-05-26*
