# Copyright 2026 ShuyuanCore contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from src.config import MemoryConfig, get_settings
from src.memory.decay import current_time_ms

logger = logging.getLogger(__name__)

_DB_PATH: str = "data/state.db"


@dataclass
class UserState:
    emotional_state: float
    engagement_level: float
    trust_level: float
    frustration_level: float
    curiosity_level: float
    last_updated: int


@dataclass
class UserGoal:
    id: str
    content: str
    priority: int
    status: str
    created_at: int
    updated_at: int
    completed_at: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserPreference:
    category: str
    key: str
    value: str
    confidence: float
    source: str
    created_at: int
    updated_at: int


@dataclass
class PredictionResult:
    predicted_action: str
    confidence: float
    reasoning: str
    suggested_response: str | None = None
    alternative_actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserModel:
    user_id: str
    state: UserState
    goals: list[UserGoal]
    preferences: list[UserPreference]
    interaction_count: int
    last_interaction_at: int
    created_at: int
    updated_at: int
    metadata: dict[str, Any] = field(default_factory=dict)


class RelationalMemory:
    def __init__(
        self,
        db_path: str = _DB_PATH,
        config: MemoryConfig | None = None,
    ) -> None:
        self._db_path: str = db_path
        self._config: MemoryConfig = config or get_settings().memory
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA busy_timeout = 5000;")
            await self._init_tables()
        return self._conn

    async def _init_tables(self) -> None:
        conn = await self._get_conn()

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_models (
                user_id TEXT PRIMARY KEY,
                emotional_state REAL NOT NULL DEFAULT 0.5,
                engagement_level REAL NOT NULL DEFAULT 0.5,
                trust_level REAL NOT NULL DEFAULT 0.5,
                frustration_level REAL NOT NULL DEFAULT 0.0,
                curiosity_level REAL NOT NULL DEFAULT 0.5,
                state_updated_at INTEGER NOT NULL DEFAULT 0,
                interaction_count INTEGER NOT NULL DEFAULT 0,
                last_interaction_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT DEFAULT '{}'
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_goals (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                completed_at INTEGER,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (user_id) REFERENCES user_models(user_id)
                    ON DELETE CASCADE
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT NOT NULL DEFAULT 'inferred',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, category, key),
                FOREIGN KEY (user_id) REFERENCES user_models(user_id)
                    ON DELETE CASCADE
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_predictions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                predicted_action TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasoning TEXT,
                suggested_response TEXT,
                alternative_actions_json TEXT DEFAULT '[]',
                metadata_json TEXT DEFAULT '{}',
                is_correct BOOLEAN,
                feedback_at INTEGER,
                created_at INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES user_models(user_id)
                    ON DELETE CASCADE
            );
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_goals_user_id
            ON user_goals(user_id, status, priority DESC);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_preferences_user_id
            ON user_preferences(user_id, category);
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_predictions_user_id
            ON user_predictions(user_id, created_at DESC);
            """
        )

        await conn.commit()

    async def get_or_create_model(self, user_id: str) -> UserModel:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        cursor = await conn.execute(
            """
            SELECT * FROM user_models WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            await conn.execute(
                """
                INSERT INTO user_models
                    (user_id, state_updated_at, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, now_ms, now_ms, now_ms),
            )
            logger.info("Created new user model: %s", user_id)
            return await self.get_model(user_id)

        return self._row_to_model(row)

    async def update(
        self,
        user_id: str,
        emotional_state: float | None = None,
        engagement_level: float | None = None,
        trust_level: float | None = None,
        frustration_level: float | None = None,
        curiosity_level: float | None = None,
        goals: list[dict[str, Any]] | None = None,
        preferences: list[dict[str, Any]] | None = None,
    ) -> UserModel:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        if emotional_state is not None:
            await conn.execute(
                """
                UPDATE user_models
                SET emotional_state = ?, state_updated_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (emotional_state, now_ms, now_ms, user_id),
            )

        if engagement_level is not None:
            await conn.execute(
                """
                UPDATE user_models
                SET engagement_level = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (engagement_level, now_ms, user_id),
            )

        if trust_level is not None:
            await conn.execute(
                """
                UPDATE user_models
                SET trust_level = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (trust_level, now_ms, user_id),
            )

        if frustration_level is not None:
            await conn.execute(
                """
                UPDATE user_models
                SET frustration_level = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (frustration_level, now_ms, user_id),
            )

        if curiosity_level is not None:
            await conn.execute(
                """
                UPDATE user_models
                SET curiosity_level = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (curiosity_level, now_ms, user_id),
            )

        await conn.execute(
            """
            UPDATE user_models
            SET interaction_count = interaction_count + 1,
                last_interaction_at = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (now_ms, now_ms, user_id),
        )

        if goals:
            for goal_data in goals:
                goal_id = goal_data.get("id") or str(uuid.uuid4())
                content = goal_data.get("content", "")
                priority = goal_data.get("priority", 0)
                status = goal_data.get("status", "active")
                metadata = goal_data.get("metadata", {})

                existing = await conn.execute(
                    "SELECT id FROM user_goals WHERE id = ?", (goal_id,)
                )
                exists = await existing.fetchone()

                if exists:
                    await conn.execute(
                        """
                        UPDATE user_goals
                        SET content = ?, priority = ?, status = ?,
                            updated_at = ?, metadata_json = ?
                        WHERE id = ?
                        """,
                        (content, priority, status, now_ms, json.dumps(metadata), goal_id),
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO user_goals
                            (id, user_id, content, priority, status, created_at, updated_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (goal_id, user_id, content, priority, status, now_ms, now_ms, json.dumps(metadata)),
                    )

        if preferences:
            for pref_data in preferences:
                category = pref_data.get("category", "general")
                key = pref_data.get("key", "")
                value = pref_data.get("value", "")
                confidence = pref_data.get("confidence", 0.5)
                source = pref_data.get("source", "inferred")

                existing = await conn.execute(
                    "SELECT user_id FROM user_preferences WHERE user_id = ? AND category = ? AND key = ?",
                    (user_id, category, key),
                )
                exists = await existing.fetchone()

                if exists:
                    await conn.execute(
                        """
                        UPDATE user_preferences
                        SET value = ?, confidence = ?, source = ?, updated_at = ?
                        WHERE user_id = ? AND category = ? AND key = ?
                        """,
                        (value, confidence, source, now_ms, user_id, category, key),
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO user_preferences
                            (user_id, category, key, value, confidence, source, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (user_id, category, key, value, confidence, source, now_ms, now_ms),
                    )

        await conn.commit()
        return await self.get_model(user_id)

    async def get_model(self, user_id: str) -> UserModel:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT * FROM user_models WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"User model not found for user_id: {user_id}")

        model = self._row_to_model(row)

        goals_cursor = await conn.execute(
            """
            SELECT * FROM user_goals WHERE user_id = ?
            ORDER BY priority DESC, created_at ASC
            """,
            (user_id,),
        )
        goal_rows = await goals_cursor.fetchall()
        model.goals = [
            UserGoal(
                id=g["id"],
                user_id=user_id,
                content=g["content"],
                priority=g["priority"],
                status=g["status"],
                created_at=g["created_at"],
                updated_at=g["updated_at"],
                completed_at=g["completed_at"],
                metadata=json.loads(g["metadata_json"]) if g["metadata_json"] else {},
            )
            for g in goal_rows
        ]

        prefs_cursor = await conn.execute(
            """
            SELECT * FROM user_preferences WHERE user_id = ?
            """,
            (user_id,),
        )
        prefs_rows = await prefs_cursor.fetchall()
        model.preferences = [
            UserPreference(
                category=p["category"],
                key=p["key"],
                value=p["value"],
                confidence=p["confidence"],
                source=p["source"],
                created_at=p["created_at"],
                updated_at=p["updated_at"],
            )
            for p in prefs_rows
        ]

        return model

    async def predict_next(
        self,
        user_id: str,
        context: dict[str, Any],
    ) -> PredictionResult:
        model = await self.get_model(user_id)

        emotional_weight = (model.state.emotional_state - 0.5) * 0.3
        engagement_weight = (model.state.engagement_level - 0.5) * 0.3
        trust_weight = (model.state.trust_level - 0.5) * 0.2
        frustration_penalty = model.state.frustration_level * 0.2

        overall_score = 0.5 + emotional_weight + engagement_weight + trust_weight - frustration_penalty
        overall_score = max(0.0, min(1.0, overall_score))

        if overall_score > 0.7:
            predicted_action = "continue_deep_exploration"
            confidence = 0.75 + (overall_score - 0.7) * 0.5
            reasoning = "用户情绪积极，参与度高，信任度良好，适合深入探讨"
            suggested_response = "我们可以继续深入探讨这个话题，你有什么具体想了解的方面吗？"
        elif overall_score > 0.5:
            predicted_action = "maintain_current_pace"
            confidence = 0.6 + (overall_score - 0.5) * 0.3
            reasoning = "用户状态稳定，保持当前节奏"
            suggested_response = None
        elif overall_score > 0.3:
            predicted_action = "simplify_and_clarify"
            confidence = 0.5 + (0.5 - overall_score) * 0.3
            reasoning = "用户可能有些困惑或犹豫，需要简化解释"
            suggested_response = "我是不是讲得太复杂了？有什么地方需要我再解释一下吗？"
        else:
            predicted_action = "check_in_and_support"
            confidence = 0.6 + (0.3 - overall_score) * 0.4
            reasoning = "用户可能感到沮丧或不满，需要关心和支持"
            suggested_response = "感觉你可能有些困扰，有什么我可以帮到你的吗？"

        alternative_actions = []
        if overall_score > 0.4:
            alternative_actions.append("offer_examples")
        if overall_score < 0.6:
            alternative_actions.append("ask_for_feedback")
        if frustration_penalty > 0.3:
            alternative_actions.append("acknowledge_frustration")

        prediction_id = str(uuid.uuid4())
        await self._store_prediction(
            user_id=user_id,
            prediction_id=prediction_id,
            predicted_action=predicted_action,
            confidence=confidence,
            reasoning=reasoning,
            suggested_response=suggested_response,
            alternative_actions=alternative_actions,
        )

        return PredictionResult(
            predicted_action=predicted_action,
            confidence=confidence,
            reasoning=reasoning,
            suggested_response=suggested_response,
            alternative_actions=alternative_actions,
            metadata={"prediction_id": prediction_id, "overall_score": overall_score},
        )

    async def _store_prediction(
        self,
        user_id: str,
        prediction_id: str,
        predicted_action: str,
        confidence: float,
        reasoning: str,
        suggested_response: str | None,
        alternative_actions: list[str],
    ) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            INSERT INTO user_predictions
                (id, user_id, predicted_action, confidence, reasoning,
                 suggested_response, alternative_actions_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_id,
                user_id,
                predicted_action,
                confidence,
                reasoning,
                suggested_response,
                json.dumps(alternative_actions),
                now_ms,
            ),
        )

        await conn.commit()

    async def record_prediction_feedback(
        self,
        prediction_id: str,
        is_correct: bool,
    ) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            UPDATE user_predictions
            SET is_correct = ?, feedback_at = ?
            WHERE id = ?
            """,
            (is_correct, now_ms, prediction_id),
        )

        await conn.commit()
        logger.debug("Recorded prediction feedback: %s (correct=%s)", prediction_id, is_correct)

    async def get_prediction_statistics(self, user_id: str) -> dict[str, Any]:
        conn = await self._get_conn()

        cursor = await conn.execute(
            """
            SELECT
                COUNT(*) as total_predictions,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_predictions,
                AVG(confidence) as avg_confidence
            FROM user_predictions
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

        total = row["total_predictions"] or 0
        correct = row["correct_predictions"] or 0
        accuracy = correct / total if total > 0 else 0.0

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": accuracy,
            "avg_confidence": row["avg_confidence"] or 0.0,
        }

    async def add_goal(
        self,
        user_id: str,
        content: str,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> UserGoal:
        conn = await self._get_conn()
        now_ms = current_time_ms()
        goal_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO user_goals
                (id, user_id, content, priority, status, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (goal_id, user_id, content, priority, now_ms, now_ms, json.dumps(metadata or {})),
        )

        await conn.commit()

        return UserGoal(
            id=goal_id,
            user_id=user_id,
            content=content,
            priority=priority,
            status="active",
            created_at=now_ms,
            updated_at=now_ms,
            metadata=metadata or {},
        )

    async def complete_goal(self, goal_id: str) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        await conn.execute(
            """
            UPDATE user_goals
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now_ms, now_ms, goal_id),
        )

        await conn.commit()
        logger.debug("Completed goal: %s", goal_id)

    async def get_goals(self, user_id: str, status: str | None = None) -> list[UserGoal]:
        conn = await self._get_conn()

        status_filter = f"AND status = ?" if status else ""
        params = [user_id, status] if status else [user_id]

        cursor = await conn.execute(
            f"""
            SELECT * FROM user_goals
            WHERE user_id = ? {status_filter}
            ORDER BY priority DESC, created_at ASC
            """,
            params,
        )
        rows = await cursor.fetchall()

        return [
            UserGoal(
                id=r["id"],
                user_id=user_id,
                content=r["content"],
                priority=r["priority"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                completed_at=r["completed_at"],
                metadata=json.loads(r["metadata_json"]) if r["metadata_json"] else {},
            )
            for r in rows
        ]

    async def add_preference(
        self,
        user_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        source: str = "inferred",
    ) -> None:
        conn = await self._get_conn()
        now_ms = current_time_ms()

        existing = await conn.execute(
            "SELECT user_id FROM user_preferences WHERE user_id = ? AND category = ? AND key = ?",
            (user_id, category, key),
        )
        exists = await existing.fetchone()

        if exists:
            await conn.execute(
                """
                UPDATE user_preferences
                SET value = ?, confidence = ?, source = ?, updated_at = ?
                WHERE user_id = ? AND category = ? AND key = ?
                """,
                (value, confidence, source, now_ms, user_id, category, key),
            )
        else:
            await conn.execute(
                """
                INSERT INTO user_preferences
                    (user_id, category, key, value, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, category, key, value, confidence, source, now_ms, now_ms),
            )

        await conn.commit()

    async def get_preferences(self, user_id: str, category: str | None = None) -> list[UserPreference]:
        conn = await self._get_conn()

        category_filter = f"AND category = ?" if category else ""
        params = [user_id, category] if category else [user_id]

        cursor = await conn.execute(
            f"""
            SELECT * FROM user_preferences
            WHERE user_id = ? {category_filter}
            """,
            params,
        )
        rows = await cursor.fetchall()

        return [
            UserPreference(
                category=r["category"],
                key=r["key"],
                value=r["value"],
                confidence=r["confidence"],
                source=r["source"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def _row_to_model(self, row: aiosqlite.Row) -> UserModel:
        return UserModel(
            user_id=row["user_id"],
            state=UserState(
                emotional_state=row["emotional_state"],
                engagement_level=row["engagement_level"],
                trust_level=row["trust_level"],
                frustration_level=row["frustration_level"],
                curiosity_level=row["curiosity_level"],
                last_updated=row["state_updated_at"],
            ),
            goals=[],
            preferences=[],
            interaction_count=row["interaction_count"],
            last_interaction_at=row["last_interaction_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
