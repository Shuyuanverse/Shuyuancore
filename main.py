from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import NoReturn

from src.config import get_settings
from src.models.dashscope import DashScopeProvider
from src.models.deepseek import DeepSeekProvider
from src.models.openai_compat import OpenAICompatProvider, OllamaProvider
from src.models.router import Router

logger = logging.getLogger(__name__)


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


def cmd_serve(_args: argparse.Namespace) -> None:
    import uvicorn

    from src.gateway.api_server import create_app

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


def cmd_repl(_args: argparse.Namespace) -> None:
    from src.gateway.cli_repl import run_repl

    asyncio.run(run_repl())


def cmd_model_switch(args: argparse.Namespace) -> None:
    router = _build_router()
    try:
        result = router.switch_model(args.role, args.model)
        print(f"\u6a21\u578b\u5df2\u5207\u6362\u81f3: {result['model']} (\u89d2\u8272: {result['role']})")
        print(f"Model switched to: {result['model']} (role: {result['role']})")
    except Exception as exc:
        print(f"\u5207\u6362\u5931\u8d25 / Switch failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_model_list(_args: argparse.Namespace) -> None:
    router = _build_router()
    models = router.get_current_models()
    print("\u5f53\u524d\u6a21\u578b\u914d\u7f6e / Current model configuration:")
    print("\u2500" * 40)
    for task_type, model_spec in models.items():
        print(f"  {task_type:<12} \u2192 {model_spec}")


def cmd_model_routing(_args: argparse.Namespace) -> None:
    router = _build_router()
    rules = router.get_routing_rules()
    print("\u8def\u7531\u89c4\u5219 / Routing rules:")
    print("\u2500" * 40)
    for rule in rules:
        print(f"  {rule['task_type']:<12} \u2192 {rule['model']}")


def cmd_health(_args: argparse.Namespace) -> None:
    router = _build_router()
    results = asyncio.run(router.check_health())
    print("\u6a21\u578b\u5065\u5eb7\u68c0\u67e5 / Provider health check:")
    print("\u2500" * 40)
    all_ok = True
    for name, status in results.items():
        icon = "\u2705" if status.ok else "\u274c"
        latency = f"{status.latency_ms}ms" if status.latency_ms else "N/A"
        error = f" - {status.error}" if status.error else ""
        print(f"  {icon} {name:<12} {latency}{error}")
        if not status.ok:
            all_ok = False
    if all_ok:
        print("\u2500" * 40)
        print("\u6240\u6709\u63d0\u4f9b\u8005\u72b6\u6001\u6b63\u5e38 / All providers healthy")
    else:
        print("\u2500" * 40)
        print("\u90e8\u5206\u63d0\u4f9b\u8005\u4e0d\u53ef\u7528 / Some providers unavailable")


def cmd_mode(args: argparse.Namespace) -> None:
    valid_modes = ("quick", "balanced", "deep")
    if args.mode not in valid_modes:
        print(f"\u65e0\u6548\u7684\u6a21\u5f0f / Invalid mode: {args.mode}", file=sys.stderr)
        print(f"\u53ef\u7528\u503c / Valid values: {', '.join(valid_modes)}", file=sys.stderr)
        sys.exit(1)
    print(f"\u591a\u667a\u80fd\u4f53\u6a21\u5f0f\u5df2\u5207\u6362\u81f3: {args.mode}\uff08\u4f1a\u8bdd\u7ea7\uff0c\u4e0d\u6301\u4e45\u5316\uff09")
    print(f"Multi-agent mode set to: {args.mode} (session-level, not persisted)")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="shuyuancore",
        description=(
            "ShuyuanCore - \u667a\u80fd\u8fdb\u5316\u3001\u98ce\u683c\u4e00\u81f4\u3001"
            "\u6df1\u5ea6\u8bb0\u5fc6\u3001\u81ea\u4e3b\u884c\u52a8\u7684\u5f00\u6e90AI Agent"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    model_parser = subparsers.add_parser("model", help="\u6a21\u578b\u7ba1\u7406 / Model management")
    model_subparsers = model_parser.add_subparsers(dest="model_command")

    switch_parser = model_subparsers.add_parser("switch", help="\u5207\u6362\u6a21\u578b / Switch model")
    switch_parser.add_argument("role", help="\u89d2\u8272 (chat/code/math/tool/review/main)")
    switch_parser.add_argument("model", help="\u6a21\u578b\u89c4\u683c (\u5982 dashscope/qwen-max)")
    switch_parser.set_defaults(func=cmd_model_switch)

    list_parser = model_subparsers.add_parser(
        "list", help="\u5217\u51fa\u5f53\u524d\u6a21\u578b / List current models"
    )
    list_parser.set_defaults(func=cmd_model_list)

    routing_parser = model_subparsers.add_parser(
        "routing", help="\u67e5\u770b\u8def\u7531\u89c4\u5219 / View routing rules"
    )
    routing_parser.set_defaults(func=cmd_model_routing)

    health_parser = subparsers.add_parser("health", help="\u5065\u5eb7\u68c0\u67e5 / Health check")
    health_parser.set_defaults(func=cmd_health)

    mode_parser = subparsers.add_parser(
        "mode", help="\u591a\u667a\u80fd\u4f53\u534f\u4f5c\u6a21\u5f0f / Multi-agent collaboration mode"
    )
    mode_parser.add_argument(
        "mode",
        choices=["quick", "balanced", "deep"],
        help="quick=\u5feb\u901f / balanced=\u5e73\u8861 / deep=\u6df1\u5ea6",
    )
    mode_parser.set_defaults(func=cmd_mode)

    serve_parser = subparsers.add_parser("serve", help="\u542f\u52a8 API \u670d\u52a1")
    serve_parser.set_defaults(func=cmd_serve)

    repl_parser = subparsers.add_parser("repl", help="\u542f\u52a8\u4ea4\u4e92\u5f0f REPL")
    repl_parser.set_defaults(func=cmd_repl)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()