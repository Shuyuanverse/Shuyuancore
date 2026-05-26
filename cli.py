from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from src.config import get_settings
from src.models.dashscope import DashScopeProvider
from src.models.deepseek import DeepSeekProvider
from src.models.openai_compat import OpenAICompatProvider, OllamaProvider
from src.models.router import Router


def _build_router() -> Router:
    from src.models.interfaces import ProviderRegistry

    settings = get_settings()
    registry = ProviderRegistry()

    providers_cfg = settings.models.providers
    for provider_name in providers_cfg:
        cfg = providers_cfg[provider_name]
        if provider_name == "dashscope":
            registry.register(
                "dashscope",
                DashScopeProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                    embedding_model=cfg.embedding_model,
                ),
            )
        elif provider_name == "deepseek":
            registry.register(
                "deepseek",
                DeepSeekProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                ),
            )
        elif provider_name == "openai":
            registry.register(
                "openai",
                OpenAICompatProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                ),
            )
        elif provider_name == "ollama":
            registry.register(
                "ollama",
                OllamaProvider(
                    base_url=cfg.base_url,
                    model=cfg.model,
                ),
            )
        else:
            registry.register(
                provider_name,
                OpenAICompatProvider(
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model=cfg.model,
                ),
            )

    router = Router(registry=registry)
    return router


def cmd_model_switch(args: argparse.Namespace) -> None:
    router = _build_router()
    try:
        result = router.switch_model(args.role, args.model)
        print(f"模型已切换至: {result['model']} (角色: {result['role']})")
        print(f"Model switched to: {result['model']} (role: {result['role']})")
    except Exception as exc:
        print(f"切换失败 / Switch failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_model_list(_args: argparse.Namespace) -> None:
    router = _build_router()
    models = router.get_current_models()
    print("当前模型配置 / Current model configuration:")
    print("─" * 40)
    for task_type, model_spec in models.items():
        print(f"  {task_type:<12} → {model_spec}")


def cmd_model_routing(_args: argparse.Namespace) -> None:
    router = _build_router()
    rules = router.get_routing_rules()
    print("路由规则 / Routing rules:")
    print("─" * 40)
    for rule in rules:
        print(f"  {rule['task_type']:<12} → {rule['model']}")


def cmd_health(_args: argparse.Namespace) -> None:
    import asyncio

    router = _build_router()
    results = asyncio.run(router.check_health())
    print("模型健康检查 / Provider health check:")
    print("─" * 40)
    all_ok = True
    for name, status in results.items():
        icon = "✅" if status.ok else "❌"
        latency = f"{status.latency_ms}ms" if status.latency_ms else "N/A"
        error = f" - {status.error}" if status.error else ""
        print(f"  {icon} {name:<12} {latency}{error}")
        if not status.ok:
            all_ok = False
    if all_ok:
        print("─" * 40)
        print("所有提供者状态正常 / All providers healthy")
    else:
        print("─" * 40)
        print("部分提供者不可用 / Some providers unavailable")


def cmd_mode(args: argparse.Namespace) -> None:
    valid_modes = ("quick", "balanced", "deep")
    if args.mode not in valid_modes:
        print(f"无效的模式 / Invalid mode: {args.mode}", file=sys.stderr)
        print(f"可用值 / Valid values: {', '.join(valid_modes)}", file=sys.stderr)
        sys.exit(1)
    print(f"多智能体模式已切换至: {args.mode}（会话级，不持久化）")
    print(f"Multi-agent mode set to: {args.mode} (session-level, not persisted)")


def cmd_serve(_args: argparse.Namespace) -> None:
    import uvicorn

    from src.gateway.api_server import create_app

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


def cmd_repl(_args: argparse.Namespace) -> None:
    import asyncio

    from src.gateway.cli_repl import run_repl

    asyncio.run(run_repl())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="shuyuancore",
        description="ShuyuanCore AI Agent",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令 / Subcommands")

    model_parser = subparsers.add_parser("model", help="模型管理 / Model management")
    model_subparsers = model_parser.add_subparsers(dest="model_command")

    switch_parser = model_subparsers.add_parser("switch", help="切换模型 / Switch model")
    switch_parser.add_argument("role", help="角色 (chat/code/math/tool/review/main)")
    switch_parser.add_argument("model", help="模型规格 (如 dashscope/qwen-max)")
    switch_parser.set_defaults(func=cmd_model_switch)

    list_parser = model_subparsers.add_parser("list", help="列出当前模型 / List current models")
    list_parser.set_defaults(func=cmd_model_list)

    routing_parser = model_subparsers.add_parser(
        "routing", help="查看路由规则 / View routing rules"
    )
    routing_parser.set_defaults(func=cmd_model_routing)

    health_parser = subparsers.add_parser("health", help="健康检查 / Health check")
    health_parser.set_defaults(func=cmd_health)

    mode_parser = subparsers.add_parser(
        "mode", help="多智能体协作模式 / Multi-agent collaboration mode"
    )
    mode_parser.add_argument(
        "mode", choices=["quick", "balanced", "deep"],
        help="quick=快速 / balanced=平衡 / deep=深度"
    )
    mode_parser.set_defaults(func=cmd_mode)

    serve_parser = subparsers.add_parser("serve", help="启动 API 服务")
    serve_parser.set_defaults(func=cmd_serve)

    repl_parser = subparsers.add_parser("repl", help="启动交互式 REPL")
    repl_parser.set_defaults(func=cmd_repl)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
