"""PyTorch 兼容性检查工具 — 统一管理 PyTorch 可用性检测和降级逻辑。"""

import importlib
import logging

logger = logging.getLogger(__name__)

TORCH_AVAILABLE: bool
try:
    import torch  # noqa: F401
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning(
        "PyTorch 未安装，将使用降级模式。部分功能（风格编码/决策编码）受限。"
        "/ PyTorch not installed, falling back to light mode. Some features may be limited."
    )