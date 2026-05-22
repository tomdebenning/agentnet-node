"""Simple SQLite conversation store."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from gateway.schemas import Message


class ConversationStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    round INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def get_messages(self, conversation_id: str) -> list[Message]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT payload FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            )
            rows = await cursor.fetchall()
        return [Message.model_validate(json.loads(row[0])) for row in rows]

    async def append_message(
        self,
        conversation_id: str,
        round: int,
        message: Message,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (conversation_id, round, payload) VALUES (?, ?, ?)",
                (conversation_id, round, json.dumps(message.model_dump(mode="json"))),
            )
            await db.execute(
                """
                INSERT INTO conversations (conversation_id, status)
                VALUES (?, 'active')
                ON CONFLICT(conversation_id) DO UPDATE SET status='active'
                """,
                (conversation_id,),
            )
            await db.commit()

    async def get_max_round(self, conversation_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT MAX(round) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            row = await cursor.fetchone()
        return int(row[0] or 0)
