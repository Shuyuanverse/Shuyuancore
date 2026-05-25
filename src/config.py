from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        def _replacer(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1), "")

        return _ENV_VAR_PATTERN.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def _load_yaml(file_path: str) -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    return _resolve_env_vars(raw)


class AgentConfig(BaseModel):
    name: str = "ShuyuanCore"
    mode: str = "general"


class ModelRoutingConfig(BaseModel):
    code: str = "deepseek/deepseek-chat"
    chat: str = "dashscope/qwen-max"
    math: str = "dashscope/qwen-max"
    embedding: str = "dashscope/text-embedding-v2"
    tool: str = "dashscope/qwen-turbo"
    review: str = "deepseek/deepseek-chat"


class ModelProviderConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    embedding_model: str = ""


class ModelsConfig(BaseModel):
    default: str = "dashscope/qwen-max"
    embedding: str = "dashscope/text-embedding-v2"
    embedding_dimensions: int = 1536
    routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    providers: dict[str, ModelProviderConfig] = Field(default_factory=dict)


class WorkingMemoryConfig(BaseModel):
    expire_days: int = 30
    auto_cleanup: bool = True


class ChromaCollectionConfig(BaseModel):
    metadata: list[str] = Field(default_factory=list)


class ChromaCollectionsConfig(BaseModel):
    long_term_memory: ChromaCollectionConfig = Field(default_factory=ChromaCollectionConfig)
    conversations: ChromaCollectionConfig = Field(default_factory=ChromaCollectionConfig)


class ChromaConfig(BaseModel):
    persist_directory: str = "data/chroma"
    client_type: str = "persistent"
    collections: ChromaCollectionsConfig = Field(default_factory=ChromaCollectionsConfig)


class EmbeddingConfig(BaseModel):
    provider: str = "dashscope"
    dedup_threshold: float = 0.95
    batch_size: int = 20

    @field_validator("dedup_threshold")
    @classmethod
    def _lock_dedup_threshold(cls, v: float) -> float:
        if v != 0.95:
            raise ValueError(f"dedup_threshold 为锁定参数，值必须为 0.95，当前为 {v}")
        return v


class MemoryConfig(BaseModel):
    core_memory_limit: int = 2200
    user_model_limit: int = 1375
    consolidation_threshold: float = 0.8
    fts5_search_limit: int = 10
    vector_search_limit: int = 5
    working: WorkingMemoryConfig = Field(default_factory=WorkingMemoryConfig)
    chroma: ChromaConfig = Field(default_factory=ChromaConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class SkillsConfig(BaseModel):
    auto_extract: bool = True
    progressive_disclosure: bool = True
    curator_interval_days: int = 7
    curator_max_iterations: int = 3
    stale_days: int = 30
    archive_days: int = 90
    difficulty_driven: bool = True


class ProtectionLevelsConfig(BaseModel):
    normal: float = 0.15
    mild_drift: float = 0.25
    severe_drift: int = 3


class PersonaIdentityConfig(BaseModel):
    max_identities: int = 5
    switch_methods: list[str] = Field(default_factory=lambda: ["natural_language", "slash_command"])
    shared_layers: list[str] = Field(default_factory=lambda: ["L3", "L4"])
    independent_layers: list[str] = Field(default_factory=lambda: ["L1", "L6"])


class PersonaConfig(BaseModel):
    drift_threshold: float = 0.25
    review_drift_threshold: float = 0.15
    enable_proactive: bool = False
    style_dimensions: int = 256
    anchor_dimensions_pytorch: int = 256
    anchor_dimensions_numpy: int = 256
    bound_components: bool = True
    min_input_chars: int = 100
    max_input_chars: int = 1000000
    language_samples_min: int = 500
    language_samples_max: int = 1000
    style_7_dimensions: list[str] = Field(
        default_factory=lambda: [
            "formality",
            "warmth",
            "directness",
            "playfulness",
            "detail_orientation",
            "emotional_expression",
            "pace",
        ]
    )
    protection_levels: ProtectionLevelsConfig = Field(default_factory=ProtectionLevelsConfig)
    identity_file: str = "CORE.md"
    identity: PersonaIdentityConfig = Field(default_factory=PersonaIdentityConfig)

    @field_validator("drift_threshold")
    @classmethod
    def _lock_drift_threshold(cls, v: float) -> float:
        if v != 0.25:
            raise ValueError(f"drift_threshold 为锁定参数，值必须为 0.25，当前为 {v}")
        return v

    @field_validator("review_drift_threshold")
    @classmethod
    def _lock_review_drift_threshold(cls, v: float) -> float:
        if v != 0.15:
            raise ValueError(f"review_drift_threshold 为锁定参数，值必须为 0.15，当前为 {v}")
        return v

    @field_validator("enable_proactive")
    @classmethod
    def _lock_enable_proactive(cls, v: bool) -> bool:
        if v is not False:
            raise ValueError(f"persona.enable_proactive 为锁定参数，值必须为 False，当前为 {v}")
        return v

    @field_validator("style_dimensions")
    @classmethod
    def _lock_style_dimensions(cls, v: int) -> int:
        if v != 256:
            raise ValueError(f"style_dimensions 为锁定参数，值必须为 256，当前为 {v}")
        return v

    @field_validator("anchor_dimensions_numpy")
    @classmethod
    def _lock_anchor_dimensions_numpy(cls, v: int) -> int:
        if v != 256:
            raise ValueError(f"anchor_dimensions_numpy 为锁定参数，值必须为 256，当前为 {v}")
        return v

    @field_validator("min_input_chars")
    @classmethod
    def _lock_min_input_chars(cls, v: int) -> int:
        if v != 100:
            raise ValueError(f"min_input_chars 为锁定参数，值必须为 100，当前为 {v}")
        return v

    @field_validator("max_input_chars")
    @classmethod
    def _lock_max_input_chars(cls, v: int) -> int:
        if v != 1000000:
            raise ValueError(f"max_input_chars 为锁定参数，值必须为 1000000，当前为 {v}")
        return v

    @field_validator("language_samples_min")
    @classmethod
    def _lock_language_samples_min(cls, v: int) -> int:
        if v != 500:
            raise ValueError(f"language_samples_min 为锁定参数，值必须为 500，当前为 {v}")
        return v

    @field_validator("language_samples_max")
    @classmethod
    def _lock_language_samples_max(cls, v: int) -> int:
        if v != 1000:
            raise ValueError(f"language_samples_max 为锁定参数，值必须为 1000，当前为 {v}")
        return v


class EvolutionConfig(BaseModel):
    trigger_days: int = 7
    trigger_count: int = 40
    max_active_modules: int = 5
    fuse_threshold: int = 3
    archive_inactive_days: int = 14

    @field_validator("max_active_modules")
    @classmethod
    def _lock_max_active_modules(cls, v: int) -> int:
        if v != 5:
            raise ValueError(f"max_active_modules 为锁定参数，值必须为 5，当前为 {v}")
        return v


class PredictionConfig(BaseModel):
    enable_proactive: bool = True
    feedback_loop: bool = True


class SecurityConfig(BaseModel):
    require_approval: bool = True
    sandbox: str = "docker"
    audit_log: bool = True
    ip_whitelist: list[str] = Field(default_factory=list)
    env_expose: bool = False
    data_encryption: bool = True
    network_isolation: bool = True
    privacy_desensitize: bool = True
    session_isolation: bool = True
    operation_rollback: bool = True
    rate_limit: bool = True
    sensitive_confirm: bool = True
    output_filter: bool = True
    permission_grading: bool = True


class GatewayPlatformConfig(BaseModel):
    enabled: bool = False
    port: int = 0
    token: str = ""


class GatewayPlatformsConfig(BaseModel):
    cli: GatewayPlatformConfig = Field(default_factory=lambda: GatewayPlatformConfig(enabled=True))
    api: GatewayPlatformConfig = Field(
        default_factory=lambda: GatewayPlatformConfig(enabled=True, port=8000)
    )
    telegram: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)
    wechat: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)
    wechat_work: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)
    feishu: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)
    dingtalk: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)
    qq: GatewayPlatformConfig = Field(default_factory=GatewayPlatformConfig)


class HistoryConfig(BaseModel):
    per_page: int = 50
    max_per_page: int = 200
    cache_recent: int = 20


class GatewayConfig(BaseModel):
    platforms: GatewayPlatformsConfig = Field(default_factory=GatewayPlatformsConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)


class CronConfig(BaseModel):
    enabled: bool = True
    check_interval: int = 60
    condition_trigger: bool = True
    task_chain: bool = True


class LogRotationConfig(BaseModel):
    max_size: str = "50MB"
    backup_count: int = 5


class HealthCheckConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "/health"
    interval: int = 30


class DeployConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8005
    workers: int = 1
    log_level: str = "info"
    log_rotation: LogRotationConfig = Field(default_factory=LogRotationConfig)
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    methods: list[str] = Field(
        default_factory=lambda: [
            "curl_bash",
            "pip",
            "homebrew",
            "docker",
            "source",
            "cloud_one_click",
        ]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="forbid",
    )

    agent: AgentConfig = Field(default_factory=AgentConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    prediction: PredictionConfig = Field(default_factory=PredictionConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    deploy: DeployConfig = Field(default_factory=DeployConfig)


_settings: Settings | None = None
_CONFIG_YAML_PATHS: tuple[str, ...] = ("config/default.yaml",)


def get_settings(yaml_paths: tuple[str, ...] | None = None) -> Settings:
    global _settings
    if _settings is not None:
        return _settings

    paths = yaml_paths or _CONFIG_YAML_PATHS
    merged: dict[str, Any] = {}
    for file_path in paths:
        data = _load_yaml(file_path)
        _deep_merge(merged, data)

    _settings = Settings(**merged)
    return _settings


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def reload_settings(yaml_paths: tuple[str, ...] | None = None) -> Settings:
    global _settings
    _settings = None
    return get_settings(yaml_paths)
