"""SQLite 儲存層。建立預約時在同一個交易裡檢查名額，避免兩個人同時搶到同一時段。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    service    TEXT NOT NULL,
    start      TEXT NOT NULL,   -- ISO 8601，含 +08:00
    end        TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'booked',  -- booked / cancelled
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(start);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE TABLE IF NOT EXISTS sessions (
    user_id    TEXT PRIMARY KEY,
    options    TEXT NOT NULL,   -- 上一次給客人的選項，讓客人直接打字也能選
    updated_at TEXT NOT NULL
);
"""


class SlotTaken(Exception):
    """該時段已額滿。"""


@dataclass
class Booking:
    id: int
    user_id: str
    service: str
    start: datetime
    end: datetime
    status: str

    @property
    def code(self) -> str:
        return f"B{self.id:05d}"


def _row_to_booking(row) -> Booking:
    return Booking(row["id"], row["user_id"], row["service"],
                   datetime.fromisoformat(row["start"]), datetime.fromisoformat(row["end"]), row["status"])


class Store:
    def __init__(self, path: str = "bookings.db"):
        # isolation_level=None：自己控制 BEGIN IMMEDIATE，鎖住寫入再檢查名額
        self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @contextmanager
    def _write(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def busiest(self, start: datetime, end: datetime) -> int:
        """[start, end) 之間「同一時刻」最多有幾筆預約。

        不能只數有幾筆重疊：10–11 點和 11–12 點各一筆時，10–12 點其實同時只有 1 人。
        """
        events = []
        for b in self.bookings_between(start, end):
            events += [(max(b.start, start), 1), (min(b.end, end), -1)]
        busiest = current = 0
        for _, delta in sorted(events, key=lambda e: (e[0], e[1])):  # 同時間先結束再開始
            current += delta
            busiest = max(busiest, current)
        return busiest

    def bookings_between(self, start: datetime, end: datetime) -> list[Booking]:
        # 時間以相同時區的 ISO 字串儲存，可以直接比較字串大小
        rows = self.conn.execute(
            "SELECT * FROM bookings WHERE status='booked' AND start < ? AND end > ? ORDER BY start",
            (end.isoformat(), start.isoformat()),
        )
        return [_row_to_booking(r) for r in rows]

    def create(self, user_id: str, service: str, start: datetime, end: datetime, capacity: int, now: datetime) -> Booking:
        with self._write():
            if self.busiest(start, end) >= capacity:
                raise SlotTaken
            cur = self.conn.execute(
                "INSERT INTO bookings (user_id, service, start, end, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, service, start.isoformat(), end.isoformat(), now.isoformat()),
            )
        return self.get(cur.lastrowid)

    def get(self, booking_id: int) -> Booking | None:
        row = self.conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        return _row_to_booking(row) if row else None

    def upcoming_for(self, user_id: str, now: datetime) -> list[Booking]:
        rows = self.conn.execute(
            "SELECT * FROM bookings WHERE user_id=? AND status='booked' AND start > ? ORDER BY start",
            (user_id, now.isoformat()),
        )
        return [_row_to_booking(r) for r in rows]

    def cancel(self, booking_id: int, user_id: str) -> bool:
        with self._write():
            cur = self.conn.execute(
                "UPDATE bookings SET status='cancelled' WHERE id=? AND user_id=? AND status='booked'",
                (booking_id, user_id),
            )
        return cur.rowcount == 1

    def save_options(self, user_id: str, options: dict[str, str], now: datetime) -> None:
        self.conn.execute(
            "INSERT INTO sessions (user_id, options, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET options=excluded.options, updated_at=excluded.updated_at",
            (user_id, json.dumps(options, ensure_ascii=False), now.isoformat()),
        )

    def load_options(self, user_id: str) -> dict[str, str]:
        row = self.conn.execute("SELECT options FROM sessions WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row["options"]) if row else {}
