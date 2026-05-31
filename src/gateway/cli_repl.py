from __future__ import annotations

import asyncio
import logging
import os
import uuid

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from src.core.agent import Agent
from src.security.approval import get_approval_manager

logger = logging.getLogger(__name__)

COMMANDS = ["/mode", "/approve", "/deny", "/exit", "/quit", "/clear"]
MODES = ["quick", "balanced", "deep"]

REPL_STYLE = Style.from_dict(
    {
        "prompt": "#00aa00 bold",
        "assistant": "#00aaff",
        "system": "#888888 italic",
        "error": "#ff0000",
        "approval": "#ffaa00 bold",
        "tool": "#aa8800",
    }
)

_agent: Agent | None = None
_current_mode: str = "balanced"


class _CommandCompleter(Completer):
    def get_completions(self, document: Document, complete_event):  # type: ignore[no-untyped-def]
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return

        word_before = document.get_word_before_cursor(WORD=True)

        if text.startswith("/mode"):
            parts = text.split()
            if len(parts) == 2 and len(parts[1]) <= len(word_before):
                for mode in MODES:
                    if mode.startswith(word_before):
                        yield Completion(mode, start_position=-len(word_before))
            if len(parts) <= 1:
                for mode in MODES:
                    yield Completion(mode, start_position=0, display=f"/mode {mode}")
            return

        if text.startswith("/approve") or text.startswith("/deny"):
            return

        for cmd in COMMANDS:
            if cmd.startswith(word_before):
                yield Completion(cmd, start_position=-len(word_before))


def set_agent(agent: Agent) -> None:
    global _agent
    _agent = agent


def _build_agent() -> Agent | None:
    from src.config import get_settings
    from src.core.belief_store import BeliefStore
    from src.core.noop_implementations import (
        MockToolRegistry,
        NoOpMemoryStore,
        NoOpPersonaGuard,
        NoOpSkillEngine,
    )
    from src.core.reader import Reader

    try:
        settings = get_settings()
        providers_cfg = settings.models.providers

        for provider_name, cfg in providers_cfg.items():
            if not cfg.api_key and provider_name not in ("ollama",):
                continue
            if not cfg.model and not cfg.api_key:
                continue

            if provider_name == "dashscope":
                from src.models.dashscope import DashScopeProvider
                from src.models.interfaces import IModelProvider

                provider: IModelProvider = DashScopeProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                    embedding_model=cfg.embedding_model,
                )
            elif provider_name == "deepseek":
                from src.models.deepseek import DeepSeekProvider
                from src.models.interfaces import IModelProvider

                provider = DeepSeekProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                )
            elif provider_name == "ollama":
                from src.models.interfaces import IModelProvider
                from src.models.openai_compat import OllamaProvider

                provider = OllamaProvider(
                    base_url=cfg.base_url,
                    model=cfg.model,
                )
            else:
                from src.models.interfaces import IModelProvider
                from src.models.openai_compat import OpenAICompatProvider

                provider = OpenAICompatProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                )

            belief_store = BeliefStore()
            reader = Reader(belief_store)

            return Agent(
                model_provider=provider,
                belief_store=belief_store,
                reader=reader,
                tool_registry=MockToolRegistry(),
                memory_store=NoOpMemoryStore(),
                persona_guard=NoOpPersonaGuard(),
                skill_engine=NoOpSkillEngine(),
            )

        return None
    except Exception:
        logger.exception("Failed to build agent")
        return None


def _print_colored(text: str, style: str = "") -> None:
    from prompt_toolkit import print_formatted_text as pft
    from prompt_toolkit.formatted_text import FormattedText

    if style:
        pft(FormattedText([("class:" + style, text)]))
    else:
        pft(text)


def _print_approval_banner(approval_id: str, tool_name: str, command: str) -> None:
    _print_colored("=" * 60, "approval")
    _print_colored(
        " 需要审批 / Approval Required",
        "approval",
    )
    _print_colored(f" Approval ID: {approval_id}", "approval")
    _print_colored(f" 工具 / Tool : {tool_name}", "tool")
    _print_colored(f" 命令 / Command: {command}", "tool")
    _print_colored(
        f" 请输入 /approve {approval_id} 批准, 或 /deny {approval_id} 拒绝",
        "system",
    )
    _print_colored(
        f" Enter /approve {approval_id} to approve, or /deny {approval_id} to deny",
        "system",
    )
    _print_colored("=" * 60, "approval")


async def _wait_for_approval(approval_id: str) -> bool:
    mgr = await get_approval_manager()
    try:
        approved = await asyncio.wait_for(
            mgr.wait(approval_id, timeout=300),
            timeout=300,
        )
        return approved
    except asyncio.TimeoutError:
        _print_colored(
            " 审批超时（5分钟），自动拒绝 / Approval timeout (5min), auto-denied",
            "error",
        )
        try:
            await mgr.resolve(approval_id, approved=False, reason="审批超时自动拒绝")
        except Exception:
            pass
        return False


async def _handle_command(cmd_line: str, session: PromptSession) -> bool:
    parts = cmd_line.strip().split(maxsplit=2)
    cmd = parts[0].lower()

    if cmd in ("/exit", "/quit"):
        _print_colored("再见 / Goodbye", "system")
        return True

    if cmd == "/clear":
        os.system("clear" if os.name != "nt" else "cls")
        return False

    if cmd == "/mode":
        global _current_mode
        if len(parts) >= 2 and parts[1] in MODES:
            _current_mode = parts[1]
            _print_colored(f"模式已切换 / Mode set: {_current_mode}", "system")
        else:
            _print_colored("用法 / Usage: /mode quick|balanced|deep", "error")
        return False

    mgr = await get_approval_manager()

    if cmd == "/approve":
        if len(parts) < 2:
            _print_colored("用法 / Usage: /approve <approval_id>", "error")
            return False
        aid = parts[1]
        req = await mgr.aget_request(aid)
        if req is None:
            _print_colored(f"审批未找到 / Approval not found: {aid}", "error")
            return False
        reason = parts[2] if len(parts) > 2 else ""
        await mgr.resolve(aid, approved=True, reason=reason)
        _print_colored(f"已批准 / Approved: {aid}", "system")
        return False

    if cmd == "/deny":
        if len(parts) < 2:
            _print_colored("用法 / Usage: /deny <approval_id>", "error")
            return False
        aid = parts[1]
        req = await mgr.aget_request(aid)
        if req is None:
            _print_colored(f"审批未找到 / Approval not found: {aid}", "error")
            return False
        reason = parts[2] if len(parts) > 2 else ""
        await mgr.resolve(aid, approved=False, reason=reason)
        _print_colored(f"已拒绝 / Denied: {aid}", "system")
        return False

    _print_colored(f"未知命令 / Unknown command: {cmd}", "error")
    return False


async def _handle_user_message(message: str, conversation_id: str) -> None:
    agent = _agent
    if agent is None:
        agent = _build_agent()
        if agent is None:
            _print_colored(
                "Agent 不可用: 未配置模型提供者 / Agent unavailable: no model provider configured",
                "error",
            )
            return
        set_agent(agent)

    _print_colored("", "")
    try:
        async for token in agent.chat_stream(message, conversation_id):
            if isinstance(token, dict):
                if token.get("type") == "approval":
                    _print_colored(
                        f"[审批] {token.get('message', '')} id={token.get('approval_id', '')}",
                        "warn",
                    )
                    approved = await _wait_for_approval(token["approval_id"])
                    if not approved:
                        _print_colored("审批被拒绝", "error")
                continue
            if isinstance(token, str):
                print(token, end="", flush=True)
        _print_colored("", "")
    except Exception as e:
        _print_colored(f"错误 / Error: {e}", "error")


async def run_repl(agent: Agent | None = None) -> None:
    global _agent
    if agent is not None:
        _agent = agent

    history_file = os.path.expanduser("~/.shuyuancore_history")

    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _multiline_newline(event):  # type: ignore[no-untyped-def]
        event.current_buffer.insert_text("\n")

    try:
        session: PromptSession = PromptSession(
            history=FileHistory(history_file),
            completer=_CommandCompleter(),
            key_bindings=bindings,
            style=REPL_STYLE,
            multiline=True,
            prompt_continuation=HTML("... "),
        )
    except Exception:
        session = PromptSession(
            history=FileHistory(history_file),
            completer=_CommandCompleter(),
            key_bindings=bindings,
            style=REPL_STYLE,
            prompt_continuation=HTML("... "),
        )

    conversation_id = str(uuid.uuid4())

    _print_colored("ShuyuanCore REPL", "assistant")
    _print_colored("输入消息开始对话 / Type a message to chat", "system")
    _print_colored("命令 / Commands: /mode, /approve, /deny, /clear, /exit", "system")
    _print_colored("Alt+Enter 换行 / Alt+Enter for newline", "system")
    _print_colored("")

    while True:
        try:
            prompt_html = HTML(f"<prompt>{_current_mode}</prompt> {conversation_id[:8]}> ")
            user_input = await session.prompt_async(prompt_html)
            user_input = user_input.strip()
        except (EOFError, KeyboardInterrupt):
            _print_colored("再见 / Goodbye", "system")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            should_exit = await _handle_command(user_input, session)
            if should_exit:
                break
        else:
            await _handle_user_message(user_input, conversation_id)


if __name__ == "__main__":
    asyncio.run(run_repl())
