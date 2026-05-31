# Contributing to ShuyuanCore

感谢你对 ShuyuanCore 的贡献！我们欢迎各种形式的参与：提交代码、报告问题、改进文档、提出建议。

---

## 快速导航

- [行为准则](CODE_OF_CONDUCT.md)
- [安全政策](SECURITY.md)
- [开发路线图](ROADMAP.md)
- [文档索引](docs/)

---

## 开始之前

### 环境要求

- **Python**: 3.10 或更高
- **包管理**: pip（推荐）或 uv
- **测试框架**: pytest + pytest-asyncio
- **代码检查**: ruff + mypy

### 本地开发设置

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/Shuyuanverse/Shuyuancore.git
cd Shuyuancore

# 2. 创建虚拟环境
python3 -m venv venv && source venv/bin/activate

# 3. 安装开发依赖
pip install -e ".[dev,all]"

# 4. 复制环境变量模板
cp .env.example .env

# 5. 运行测试验证环境
pytest
```

---

## 提交问题（Issue）

### Bug 报告

请在 [Issues](https://github.com/Shuyuanverse/Shuyuancore/issues) 中使用 Bug Report 模板，包含：

- **复现步骤**：清晰描述如何触发问题
- **预期行为**：你认为应该发生什么
- **实际行为**：实际发生了什么
- **环境信息**：Python 版本、操作系统、ShuyuanCore 版本
- **日志输出**：相关日志或错误堆栈

### 功能请求

- 描述你想要的功能和使用场景
- 说明这个功能解决什么问题
- 如果有实现思路，欢迎一并提出

---

## 提交代码（Pull Request）

### 工作流

1. **Fork** 仓库到你的 GitHub 账号
2. 创建功能分支：`git checkout -b feature/your-feature-name`
3. 进行开发（遵循下方代码规范）
4. 运行测试和代码检查（必须通过）
5. 提交并推送到你的 Fork
6. 提交 Pull Request 到 `main` 分支

### 提交信息格式

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>
```

| type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(memory): add working memory layer` |
| `fix` | 修复 Bug | `fix(agent): resolve context overflow` |
| `docs` | 文档更新 | `docs: update API documentation` |
| `style` | 代码格式 | `style: fix ruff formatting issues` |
| `refactor` | 重构 | `refactor(gateway): extract approval middleware` |
| `test` | 测试相关 | `test(skills): add curator unit tests` |
| `chore` | 构建/工具 | `chore: update pyproject.toml dependencies` |

**要求**：
- `subject` 不超过 50 字符
- 使用现在时（如 `add` 而非 `added`）
- 首字母不大写，末尾不加句号

### PR 要求

- 每个 PR 应聚焦一个功能或修复，避免混合改动
- 描述清楚改动的目的和影响范围
- 关联相关的 Issue（使用 `Closes #123` 语法）
- 确保 CI 检查通过（测试、lint、类型检查）

---

## 代码规范

### Python 规范

本项目遵循以下工具链：

| 工具 | 用途 | 命令 |
|------|------|------|
| [ruff](https://docs.astral.sh/ruff/) | 代码检查 + 格式化 | `ruff check src/ && ruff format src/` |
| [mypy](https://mypy.readthedocs.io/) | 类型检查 | `mypy src/` |
| [pytest](https://docs.pytest.org/) | 单元测试 | `pytest` |

### 命名规范

- **模块/包**：小写，无下划线（`core`, `memory`）
- **类名**：CapWords（`Agent`, `MemoryStore`）
- **函数/方法**：小写下划线（`get_conversation`）
- **常量**：全大写下划线（`DRIFT_THRESHOLD`）
- **私有属性/方法**：单下划线前缀（`_prepare_context`）

### 格式规范

- 缩进：4 个空格，禁止使用 Tab
- 行长：最大 100 字符
- 空行：模块级函数和类之间空两行，类内方法之间空一行
- 导入顺序：标准库 → 第三方库 → 本地模块，各组空一行

### 类型注解

所有函数参数和返回值**必须**标注类型：

```python
from __future__ import annotations
from typing import Optional

async def get_conversation(session_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a conversation by session ID.

    Args:
        session_id: Unique identifier for the conversation session.

    Returns:
        Conversation dict if found, None otherwise.
    """
    ...
```

### Docstring

所有公共类、公共方法、模块级函数**必须**包含 Google 风格的 docstring，包含 `Args`、`Returns`、`Raises` 等部分。

### 关键规则

- **禁止硬编码敏感信息**：API Key、密码等必须从环境变量读取
- **禁止裸 `except:`**：所有异常处理必须明确捕获具体类型
- **禁止跨模块直接导入具体实现**：必须通过 `interfaces.py` 通信
- **禁止修改已锁定的关键参数**（如 `drift_threshold=0.25`）
- **每个提交必须确保代码可运行**（通过 smoke test）

---

## 测试要求

### 运行测试

```bash
# 运行全部测试
pytest

# 运行特定模块测试
pytest tests/test_memory/ -v

# 运行并生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 编写测试

- 测试文件放在 `tests/` 下，路径与 `src/` 一一对应
- 测试文件命名：`test_<module>.py`
- 测试函数命名：`test_<function>_<scenario>`
- 异步测试使用 `@pytest.mark.asyncio`
- 测试必须使用独立数据库（`:memory:` 或临时文件），禁止读写生产 `state.db`
- 核心模块（config, models, core/agent, memory）行覆盖率目标 ≥ 85%

### 测试数据库隔离示例

```python
import pytest
from src.memory.store import MemoryStore

@pytest.fixture
async def store():
    """Create an in-memory store for testing."""
    s = MemoryStore(db_path=":memory:")
    await s.init()
    yield s
    await s.close()

@pytest.mark.asyncio
async def test_store_write_and_read(store):
    await store.write("test_key", {"data": "value"})
    result = await store.read("test_key")
    assert result["data"] == "value"
```

---

## 数据库迁移

使用 Alembic 管理数据库迁移：

```bash
# 创建新迁移
alembic revision -m "add_user_preferences"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

**迁移脚本要求**：
- 必须包含 `upgrade()` 和 `downgrade()`
- 每个迁移只做一件事
- 提交前测试回滚（`downgrade` 然后 `upgrade`）

---

## 开发流程

### 较大功能变更的设计流程

对于复杂功能，建议先在 Issue 中讨论设计方案，包含：

1. **功能拆解**：要实现什么，输入/输出是什么
2. **架构设计**：类/接口定义、模块通信、数据流
3. **技术选型**：用什么库/方法，为什么
4. **实现步骤**：按什么顺序开发
5. **风险点**：可能的问题和边界条件

获得反馈后再开始编码。

### 接口先行

新增模块时，先定义 `interfaces.py` 再写实现：

```
src/memory/
├── __init__.py
├── interfaces.py   # 先写这个
├── core_memory.py  # 再写实现
└── long_term.py
```

---

## 安全注意事项

- 不要在代码或 PR 中泄露 API Key、密码等敏感信息
- 涉及危险操作（执行命令、删除文件、数据库修改）的代码需包含审批机制
- 报告安全漏洞请通过 [安全政策](SECURITY.md) 中的方式联系维护者

---

## 许可证

参与贡献即表示你同意你的贡献将在 [Apache License 2.0](LICENSE) 下分发。

---

*感谢你的贡献！*
