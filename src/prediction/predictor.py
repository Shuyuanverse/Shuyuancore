# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

"""预测式建模核心 — 对话模式分析、用户行为预测、活跃时段挖掘。

功能：
- 分析对话模式（主题分布、情绪趋势、活跃时段）
- 基于规则 + LLM 增强的用户下一步需求预测
- 用户行为模型持久化（session_stats / topic_frequencies / active_hours）
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"

# 用于规则预测的关键词 -> 预测动作映射
_KEYWORD_ACTION_MAP: dict[str, str] = {
    "分析": "data_analysis",
    "图表": "chart_generation",
    "画图": "chart_generation",
    "可视化": "chart_generation",
    "总结": "summarization",
    "摘要": "summarization",
    "翻译": "translation",
    "代码": "code_review",
    "调试": "debugging",
    "bug": "debugging",
    "错误": "debugging",
    "测试": "testing",
    "部署": "deployment",
    "优化": "optimization",
    "性能": "optimization",
    "文档": "documentation",
    "报告": "report_generation",
    "邮件": "email_draft",
    "搜索": "web_search",
    "天气": "weather_query",
    "提醒": "reminder_set",
    "定时": "reminder_set",
    "规划": "planning",
    "计划": "planning",
    "推荐": "recommendation",
    "建议": "recommendation",
}

# 情绪相关关键词
_SENTIMENT_POSITIVE: set[str] = {"好", "棒", "不错", "满意", "感谢", "谢谢", "可以", "是的"}
_SENTIMENT_NEGATIVE: set[str] = {"不好", "差", "错误", "不对", "不行", "不满意", "糟糕", "失败"}

# 时间模式映射：空闲时段标签
_TIME_PERIOD_LABELS: dict[int, str] = {
    0: "凌晨", 1: "凌晨", 2: "凌晨", 3: "凌晨", 4: "凌晨", 5: "凌晨",
    6: "早晨", 7: "早晨", 8: "早晨",
    9: "上午", 10: "上午", 11: "上午",
    12: "中午", 13: "下午", 14: "下午", 15: "下午", 16: "下午", 17: "下午",
    18: "傍晚", 19: "晚上", 20: "晚上", 21: "晚上", 22: "晚上", 23: "深夜",
}


@dataclass
class PredictionResult:
    """预测结果。

    Attributes:
        predicted_action: 预测的用户下一步动作
        confidence: 置信度 (0.0 ~ 1.0)
        suggested_response: 建议的回复内容
        timestamp: 预测时间戳（毫秒）
        context: 预测时的上下文信息
        metadata: 额外元数据
    """

    predicted_action: str
    confidence: float
    suggested_response: str
    timestamp: int = field(default_factory=current_time_ms)
    context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class Predictor:
    """预测式建模核心。

    基于用户历史对话数据，使用规则匹配 + LLM 增强的方式预测用户下一步可能的需求。
    支持对话模式分析、活跃时段挖掘、主题频率统计等功能。
    """

    CREATE_TABLES_SQL: str = """
    CREATE TABLE IF NOT EXISTS session_stats (
        id              TEXT PRIMARY KEY,
        user_id         TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        message_count   INTEGER NOT NULL DEFAULT 0,
        avg_response_time_ms INTEGER DEFAULT 0,
        sentiment_trend TEXT DEFAULT 'neutral',
        topics          TEXT NOT NULL DEFAULT '[]',
        started_at      INTEGER NOT NULL,
        ended_at        INTEGER,
        metadata_json   TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS topic_frequencies (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL,
        topic       TEXT NOT NULL,
        count       INTEGER NOT NULL DEFAULT 0,
        last_used   INTEGER NOT NULL,
        created_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS active_hours (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL,
        hour        INTEGER NOT NULL,
        activity_count INTEGER NOT NULL DEFAULT 0,
        last_active INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_session_stats_user ON session_stats(user_id);
    CREATE INDEX IF NOT EXISTS idx_session_stats_conversation ON session_stats(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_topic_frequencies_user ON topic_frequencies(user_id);
    CREATE INDEX IF NOT EXISTS idx_topic_frequencies_topic ON topic_frequencies(user_id, topic);
    CREATE INDEX IF NOT EXISTS idx_active_hours_user ON active_hours(user_id);
    CREATE INDEX IF NOT EXISTS idx_active_hours_hour ON active_hours(user_id, hour);
    """

    def __init__(
        self,
        db_path: str = _DB_PATH,
        model_provider: Any | None = None,
        belief_store: Any | None = None,
    ) -> None:
        """初始化预测器。

        Args:
            db_path: SQLite 数据库路径
            model_provider: 可选的 LLM 提供者，用于增强预测
            belief_store: 可选的信念存储，用于读取用户记忆
        """
        self._db_path: str = db_path
        self._model_provider = model_provider
        self._belief_store = belief_store
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接（懒加载）。

        Returns:
            aiosqlite.Connection: 数据库连接
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._init_tables()
        return self._conn

    async def _init_tables(self) -> None:
        """初始化数据库表。"""
        conn = await self._get_conn()
        for statement in self.CREATE_TABLES_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(stmt)
        await conn.commit()

    async def analyze_conversation_pattern(self, conversation_id: str) -> dict[str, Any]:
        """分析对话模式。

        从已有 session_stats 记录和信念存储中提取指定对话的模式特征，
        包括主题分布、交互频率、情绪趋势。

        Args:
            conversation_id: 对话 ID

        Returns:
            dict: 包含以下键的分析结果
                - topics: 对话主题列表
                - message_count: 消息数量
                - sentiment_trend: 情绪趋势（positive / negative / neutral）
                - avg_response_time_ms: 平均响应时间（毫秒）
                - conversation_duration_ms: 对话持续时间（毫秒）
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM session_stats WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return {
                "topics": [],
                "message_count": 0,
                "sentiment_trend": "neutral",
                "avg_response_time_ms": 0,
                "conversation_duration_ms": 0,
            }

        return {
            "topics": json.loads(row["topics"]),
            "message_count": row["message_count"],
            "sentiment_trend": row["sentiment_trend"],
            "avg_response_time_ms": row["avg_response_time_ms"],
            "conversation_duration_ms": (
                (row["ended_at"] - row["started_at"])
                if row["ended_at"] and row["started_at"]
                else 0
            ),
        }

    async def predict_next(
        self,
        user_id: str,
        conversation_history: list[dict[str, str]],
    ) -> PredictionResult | None:
        """预测用户下一步可能的需求。

        使用基于规则的预测策略：
        1. 从对话历史中提取最后一条用户消息
        2. 关键词匹配识别可能的意图
        3. 结合用户历史活跃时段和主题频率调整置信度
        4. 如果有 LLM 提供者，尝试增强预测

        Args:
            user_id: 用户 ID
            conversation_history: 对话历史列表，每条包含 role 和 content

        Returns:
            PredictionResult 或 None（无法预测时返回 None）
        """
        if not conversation_history:
            return None

        # 提取用户消息文本
        user_messages = [
            msg["content"]
            for msg in conversation_history
            if msg.get("role") in ("user", "human")
        ]

        if not user_messages:
            return None

        last_message = user_messages[-1]
        all_text = " ".join(user_messages)

        # 关键词匹配预测
        predicted_action = self._match_keywords(last_message)
        if predicted_action is None:
            predicted_action = self._match_keywords(all_text)

        if predicted_action is None:
            return None

        # 计算置信度
        confidence = self._calculate_confidence(last_message, user_messages[:-1])

        # 获取用户活跃时段调整
        active_hours = await self.get_active_hours(user_id)
        current_hour = time.localtime().tm_hour
        if current_hour in active_hours:
            confidence = min(1.0, confidence + 0.05)

        # 如果可用，使用 LLM 增强预测
        suggested_response = f"看起来您正在{predicted_action.replace('_', ' ')}，需要帮助吗？"
        if self._model_provider is not None:
            try:
                enhanced = await self._llm_enhance_prediction(
                    predicted_action, last_message, confidence
                )
                if enhanced:
                    predicted_action, confidence, suggested_response = enhanced
            except Exception:
                logger.warning("LLM enhanced prediction failed, falling back to rule-based")

        result = PredictionResult(
            predicted_action=predicted_action,
            confidence=confidence,
            suggested_response=suggested_response,
            context={"last_message_length": len(last_message), "history_depth": len(user_messages)},
        )

        # 持久化预测到 user_predictions 表
        await self._save_prediction(user_id, result)

        return result

    async def _save_prediction(self, user_id: str, result: PredictionResult) -> None:
        """将预测结果持久化到数据库。

        Args:
            user_id: 用户 ID
            result: 预测结果
        """
        conn = await self._get_conn()
        prediction_id = uuid.uuid4().hex
        await conn.execute(
            """
            INSERT OR IGNORE INTO user_predictions
                (id, user_id, predicted_action, confidence, reasoning,
                 suggested_response, alternative_actions_json,
                 metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_id,
                user_id,
                result.predicted_action,
                result.confidence,
                f"Rule-based match with confidence {result.confidence:.2f}",
                result.suggested_response,
                "[]",
                json.dumps({**result.context, **result.metadata}),
                result.timestamp,
            ),
        )
        await conn.commit()

    async def _llm_enhance_prediction(
        self,
        base_action: str,
        last_message: str,
        base_confidence: float,
    ) -> tuple[str, float, str] | None:
        """使用 LLM 增强预测结果。

        Args:
            base_action: 规则匹配的基础动作
            last_message: 用户最后一条消息
            base_confidence: 基础置信度

        Returns:
            (action, confidence, suggestion) 或 None（增强失败）
        """
        if self._model_provider is None:
            return None

        system = (
            "你是一个用户意图预测助手。根据用户的最新消息，判断用户下一步最可能需要的动作。"
            f"基础预测为：{base_action}（置信度 {base_confidence:.2f}）。"
            "请输出 JSON 格式：{\"action\": \"...\", \"confidence\": 0.xx, \"suggestion\": \"...\"}"
        )

        response = await self._model_provider.chat(
            history=[
                {"role": "system", "content": system},
                {"role": "user", "content": last_message},
            ],
            temperature=0.3,
        )

        try:
            data = json.loads(response.content.strip())
            action = data.get("action", base_action)
            confidence = max(0.0, min(1.0, data.get("confidence", base_confidence)))
            suggestion = data.get("suggestion", f"看起来您正在{action.replace('_', ' ')}，需要帮助吗？")
            return action, confidence, suggestion
        except (json.JSONDecodeError, AttributeError):
            return None

    def _match_keywords(self, text: str) -> str | None:
        """通过关键词匹配识别用户意图。

        Args:
            text: 用户消息文本

        Returns:
            str 或 None: 匹配到的动作名称
        """
        for keyword, action in _KEYWORD_ACTION_MAP.items():
            if keyword in text:
                return action
        return None

    async def predict_from_history(self, user_id: str) -> list[PredictionResult]:
        """基于历史对话的批量预测。

        读取用户的历史对话记录，从中提取模式并生成预测列表。
        结果按置信度降序排列。

        Args:
            user_id: 用户 ID

        Returns:
            list[PredictionResult]: 预测结果列表
        """
        conn = await self._get_conn()

        # 获取用户的高频主题
        cursor = await conn.execute(
            "SELECT topic, count FROM topic_frequencies WHERE user_id = ? ORDER BY count DESC LIMIT 5",
            (user_id,),
        )
        topics = await cursor.fetchall()

        # 获取最近的 session_stats
        cursor = await conn.execute(
            "SELECT topics, sentiment_trend FROM session_stats WHERE user_id = ? ORDER BY started_at DESC LIMIT 10",
            (user_id,),
        )
        sessions = await cursor.fetchall()

        results: list[PredictionResult] = []

        # 基于高频主题生成预测
        actions_seen: set[str] = set()
        for row in topics:
            topic = row["topic"]
            count = row["count"]
            for keyword, action in _KEYWORD_ACTION_MAP.items():
                if keyword in topic and action not in actions_seen:
                    confidence = min(0.9, 0.4 + count * 0.02)
                    results.append(
                        PredictionResult(
                            predicted_action=action,
                            confidence=confidence,
                            suggested_response=f"根据历史记录，您经常处理{topic}相关任务，需要帮助吗？",
                            context={"source": "history", "matched_topic": topic},
                        )
                    )
                    actions_seen.add(action)
                    break

        # 基于最近会话的情绪趋势生成预测
        if sessions:
            sentiment_counts: dict[str, int] = Counter()
            for row in sessions:
                sentiment_counts[row["sentiment_trend"]] += 1

            most_common_sentiment = sentiment_counts.most_common(1)
            if most_common_sentiment and most_common_sentiment[0][0] == "negative":
                results.append(
                    PredictionResult(
                        predicted_action="emotional_support",
                        confidence=0.5,
                        suggested_response="我注意到您最近可能遇到了一些困难，需要聊聊吗？",
                        context={"source": "sentiment_trend", "trend": "negative"},
                    )
                )

        # 按置信度降序排列
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    async def get_frequent_topics(self, user_id: str, days: int = 7) -> list[tuple[str, int]]:
        """获取用户的高频主题。

        Args:
            user_id: 用户 ID
            days: 统计天数范围（默认 7 天）

        Returns:
            list[tuple[str, int]]: (主题, 频率) 列表，按频率降序排列
        """
        conn = await self._get_conn()
        cutoff_ms = current_time_ms() - days * 86400000

        cursor = await conn.execute(
            """
            SELECT topic, count FROM topic_frequencies
            WHERE user_id = ? AND last_used > ?
            ORDER BY count DESC
            LIMIT 20
            """,
            (user_id, cutoff_ms),
        )
        rows = await cursor.fetchall()
        return [(row["topic"], row["count"]) for row in rows]

    async def get_active_hours(self, user_id: str) -> list[int]:
        """获取用户活跃时段（小时）。

        Args:
            user_id: 用户 ID

        Returns:
            list[int]: 活跃小时列表（0-23），按活跃度降序排列
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT hour FROM active_hours
            WHERE user_id = ?
            ORDER BY activity_count DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [row["hour"] for row in rows]

    async def get_active_hours_with_labels(self, user_id: str) -> list[dict[str, Any]]:
        """获取用户活跃时段（含时间段标签）。

        Args:
            user_id: 用户 ID

        Returns:
            list[dict]: 包含 hour, label, activity_count 的列表
        """
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            SELECT hour, activity_count FROM active_hours
            WHERE user_id = ?
            ORDER BY activity_count DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "hour": row["hour"],
                "label": _TIME_PERIOD_LABELS.get(row["hour"], "未知"),
                "activity_count": row["activity_count"],
            }
            for row in rows
        ]

    async def update_user_model(
        self,
        conversation_id: str,
        message: str,
        response: str,
    ) -> None:
        """更新用户行为模型。

        每次对话交互后调用，更新 session_stats、topic_frequencies 和 active_hours 表。

        Args:
            conversation_id: 对话 ID
            message: 用户消息
            response: 系统回复
        """
        conn = await self._get_conn()
        now_ms = current_time_ms()

        # 1. 更新 session_stats
        topics = self._extract_topics(message)
        sentiment = self._detect_sentiment(message)

        cursor = await conn.execute(
            "SELECT id, message_count FROM session_stats WHERE conversation_id = ?",
            (conversation_id,),
        )
        existing = await cursor.fetchone()

        if existing:
            existing_topics = json.loads(
                (await conn.execute(
                    "SELECT topics FROM session_stats WHERE id = ?",
                    (existing["id"],),
                )).fetchone()["topics"]
            )
            merged_topics = list(set(existing_topics + topics))
            await conn.execute(
                """
                UPDATE session_stats
                SET message_count = message_count + 1,
                    topics = ?,
                    ended_at = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(merged_topics),
                    now_ms,
                    json.dumps({"last_message_length": len(message), "response_length": len(response)}),
                    existing["id"],
                ),
            )
        else:
            stats_id = uuid.uuid4().hex
            await conn.execute(
                """
                INSERT INTO session_stats
                    (id, user_id, conversation_id, message_count, sentiment_trend,
                     topics, started_at, ended_at, metadata_json)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    stats_id,
                    "anonymous",
                    conversation_id,
                    sentiment,
                    json.dumps(topics),
                    now_ms,
                    now_ms,
                    json.dumps({"last_message_length": len(message), "response_length": len(response)}),
                ),
            )

        # 2. 更新 topic_frequencies
        for topic in topics:
            cursor = await conn.execute(
                "SELECT id FROM topic_frequencies WHERE user_id = ? AND topic = ?",
                ("anonymous", topic),
            )
            existing_topic = await cursor.fetchone()
            if existing_topic:
                await conn.execute(
                    "UPDATE topic_frequencies SET count = count + 1, last_used = ? WHERE id = ?",
                    (now_ms, existing_topic["id"]),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO topic_frequencies (user_id, topic, count, last_used, created_at)
                    VALUES (?, ?, 1, ?, ?)
                    """,
                    ("anonymous", topic, now_ms, now_ms),
                )

        # 3. 更新 active_hours
        current_hour = time.localtime().tm_hour
        cursor = await conn.execute(
            "SELECT id FROM active_hours WHERE user_id = ? AND hour = ?",
            ("anonymous", current_hour),
        )
        existing_hour = await cursor.fetchone()
        if existing_hour:
            await conn.execute(
                "UPDATE active_hours SET activity_count = activity_count + 1, last_active = ? WHERE id = ?",
                (now_ms, existing_hour["id"]),
            )
        else:
            await conn.execute(
                """
                INSERT INTO active_hours (user_id, hour, activity_count, last_active)
                VALUES (?, ?, 1, ?)
                """,
                ("anonymous", current_hour, now_ms),
            )

        await conn.commit()
        logger.debug("Updated user model for conversation %s", conversation_id)

    def _extract_topics(self, text: str) -> list[str]:
        """从文本中提取主题关键词。

        Args:
            text: 用户消息文本

        Returns:
            list[str]: 提取到的主题列表
        """
        topics: list[str] = []
        for keyword, action in _KEYWORD_ACTION_MAP.items():
            if keyword in text:
                topics.append(action)
        # 去重
        seen: set[str] = set()
        return [t for t in topics if not (t in seen or seen.add(t))]

    def _detect_sentiment(self, text: str) -> str:
        """检测文本情绪倾向。

        Args:
            text: 用户消息文本

        Returns:
            str: 'positive' / 'negative' / 'neutral'
        """
        positive_count = sum(1 for word in _SENTIMENT_POSITIVE if word in text)
        negative_count = sum(1 for word in _SENTIMENT_NEGATIVE if word in text)

        if positive_count > negative_count:
            return "positive"
        if negative_count > positive_count:
            return "negative"
        return "neutral"

    def _calculate_confidence(self, text: str, history: list[str]) -> float:
        """计算预测置信度。

        基于以下因素综合计算：
        - 关键词匹配度（是否明确表达了意图）
        - 历史消息一致性（是否反复提到同类话题）
        - 消息长度（较长的消息通常意图更明确）

        Args:
            text: 用户当前消息
            history: 历史用户消息列表

        Returns:
            float: 置信度 (0.0 ~ 1.0)
        """
        confidence = 0.5  # 基础置信度

        # 1. 关键词匹配度：匹配到的关键词数量
        matched_count = sum(1 for kw in _KEYWORD_ACTION_MAP if kw in text)
        if matched_count > 0:
            confidence += min(0.2, matched_count * 0.1)

        # 2. 消息长度因素
        char_count = len(text)
        if 10 <= char_count <= 200:
            confidence += 0.1
        elif char_count > 200:
            confidence += 0.15

        # 3. 历史一致性：检查历史消息中是否提到过相同话题
        if history:
            current_keywords = {kw for kw in _KEYWORD_ACTION_MAP if kw in text}
            if current_keywords:
                historical_matches = sum(
                    1 for msg in history if any(kw in msg for kw in current_keywords)
                )
                if historical_matches >= 2:
                    confidence += 0.15
                elif historical_matches >= 1:
                    confidence += 0.08

        # 4. 是否有明确的问题意图（以问号或请求结尾）
        if re.search(r"[？?]$", text.strip()):
            confidence += 0.1

        # 5. 是否有帮忙/需要的请求模式
        if re.search(r"(帮[我我]|需要|想要|可以.*吗|能.*吗)", text):
            confidence += 0.1

        return max(0.0, min(1.0, confidence))

    async def get_user_model_summary(self, user_id: str) -> dict[str, Any]:
        """获取用户行为模型摘要。

        Args:
            user_id: 用户 ID

        Returns:
            dict: 包含活跃时段、高频主题、会话统计的摘要
        """
        active_hours = await self.get_active_hours_with_labels(user_id)
        topics = await self.get_frequent_topics(user_id)
        conn = await self._get_conn()

        cursor = await conn.execute(
            "SELECT COUNT(*) as total, AVG(message_count) as avg_msgs FROM session_stats WHERE user_id = ?",
            (user_id,),
        )
        stats = await cursor.fetchone()

        return {
            "user_id": user_id,
            "total_sessions": stats["total"] if stats else 0,
            "avg_messages_per_session": round(stats["avg_msgs"], 1) if stats and stats["avg_msgs"] else 0,
            "active_hours": active_hours,
            "frequent_topics": topics,
        }

    async def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None