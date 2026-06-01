from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Belief:
    id: str
    content: str
    source: str
    confidence: float = 1.0
    base_confidence: float = 1.0
    last_accessed: int = 0
    memory_type: str = "chat"
    layer: int = 3
    entities: list[str] = field(default_factory=list)
    emotion: float = 0.5
    depends_on: list[str] = field(default_factory=list)
    child_belief_ids: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    status: str = "active"
    is_composite: bool = False
    timestamp: int = 0
    conversation_date: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


MEMORY_TYPE_LAYER_MAP: dict[str, int] = {
    "identity": 1,
    "preference": 1,
    "fact": 3,
    "task": 2,
    "agreement": 2,
    "emotion": 5,
    "chat": 3,
}


class IBeliefStore(ABC):
    @abstractmethod
    async def add(self, conversation_id: str, belief: Belief) -> str: ...

    @abstractmethod
    async def get(self, conversation_id: str, limit: int = 50) -> list[Belief]: ...

    @abstractmethod
    async def get_by_id(self, belief_id: str) -> Belief | None: ...

    @abstractmethod
    async def update(self, belief: Belief) -> None: ...

    @abstractmethod
    async def clear(self, conversation_id: str) -> None: ...

    @abstractmethod
    async def remove(self, conversation_id: str, belief_id: str) -> None: ...

    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        min_confidence: float = 0.1,
    ) -> list[tuple[Belief, float]]: ...

    @abstractmethod
    async def get_similar_task_count(
        self,
        query: str,
        days: int = 7,
        similarity_threshold: float = 0.8,
    ) -> int: ...

    @abstractmethod
    async def propagate_confidence(
        self, belief_id: str, delta: float, visited: set[str] | None = None
    ) -> None: ...

    @abstractmethod
    async def overthrow(self, old_id: str, new_id: str, reason: str) -> None: ...


class IConversationManager(ABC):
    """对话管理器接口。

    负责：
    - 创建对话
    - 添加消息
    - 获取消息历史
    - 列表对话
    - 删除对话
    """

    @abstractmethod
    async def create_conversation(self, user_id: str, title: str = "") -> str:
        """创建新对话。

        Args:
            user_id: 用户 ID
            title: 对话标题（可选）

        Returns:
            str: 对话 ID
        """
        ...

    @abstractmethod
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加消息到对话。

        Args:
            conversation_id: 对话 ID
            role: 角色（user/assistant/system）
            content: 消息内容
            metadata: 元数据（可选）
        """
        ...

    @abstractmethod
    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取对话消息历史。

        Args:
            conversation_id: 对话 ID
            limit: 最大消息数
            before: 游标（格式："{timestamp}_{id}"）

        Returns:
            list[dict]: 消息列表
        """
        ...

    @abstractmethod
    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, bool]:
        """列表用户的所有对话。

        Args:
            user_id: 用户 ID
            limit: 每页数量
            cursor: 分页游标

        Returns:
            tuple: (对话列表，下一个游标，是否有更多)
        """
        ...

    @abstractmethod
    async def delete_conversation(self, conversation_id: str) -> None:
        """删除对话及其所有消息。

        Args:
            conversation_id: 对话 ID
        """
        ...


class IReader(ABC):
    @abstractmethod
    async def read(
        self,
        conversation_id: str,
        user_query: str | None = None,
        max_tokens: int = 4000,
    ) -> list[dict[str, Any]]: ...


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


class IToolRegistry(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str: ...

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]: ...

    @abstractmethod
    def get_tool(self, tool_name: str) -> ToolSpec | None: ...


class IMemoryStore(ABC):
    """通用记忆存储接口。

    用于存储和检索与信念无关的持久化记忆数据，
    例如用户偏好、会话上下文、行为模式等。
    """

    @abstractmethod
    async def store(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    async def retrieve(self, key: str) -> Any | None: ...

    @abstractmethod
    async def delete(self, key: str) -> bool: ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 10) -> list[tuple[str, Any, float]]: ...


class IPersonaGuard(ABC):
    """人格守卫接口。

    负责检测人格漂移、验证输出一致性，
    并在必要时提供约束提示以维持人格稳定性。
    """

    @abstractmethod
    async def validate(
        self,
        user_id: str,
        persona_id: str,
        output: str,
    ) -> tuple[bool, float]: ...

    @abstractmethod
    async def check_drift(
        self,
        user_id: str,
        persona_id: str,
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def get_guard_prompt(
        self,
        user_id: str,
        persona_id: str,
    ) -> str: ...


class ISkillEngine(ABC):
    """技能引擎接口。

    负责技能的注册、执行、发现与生命周期管理。
    """

    @abstractmethod
    async def execute_skill(
        self,
        skill_name: str,
        params: dict[str, Any],
        user_id: str = "default",
    ) -> Any: ...

    @abstractmethod
    async def list_skills(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_skill_spec(
        self,
        skill_name: str,
    ) -> dict[str, Any] | None: ...
