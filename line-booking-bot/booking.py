"""預約對話邏輯，完全不依賴 LINE：輸入「客人說了什麼」，輸出「要回什麼＋可點的選項」。

每個選項的 data 都帶齊目前的選擇（例如 action=book&svc=cut&date=2026-10-20），
所以不需要記住對話進行到哪一步：客人點到舊按鈕、或伺服器重啟，都能正確接續。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.parse import parse_qsl, urlencode

import shop_config
from db import Booking, SlotTaken, Store

TZ = timezone(timedelta(hours=8), "Asia/Taipei")  # 台灣沒有日光節約時間
WEEKDAYS = "一二三四五六日"
SLOTS_PER_PAGE = 10  # LINE 快速回覆最多 13 個：10 個時段 + 上一頁 / 下一頁 / 換日期


@dataclass
class Option:
    label: str  # LINE 限制 20 字以內
    data: str


@dataclass
class Reply:
    text: str
    options: list[Option] = field(default_factory=list)


def fmt_day(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def fmt_dt(dt: datetime) -> str:
    return f"{fmt_day(dt.date())} {dt:%H:%M}"


def q(**params) -> str:
    return urlencode(params)


KEYWORDS = {
    "預約": "book", "我要預約": "book", "訂位": "book",
    "我的預約": "mine", "查詢": "mine", "查預約": "mine",
    "取消預約": "cancel",
    "選單": "menu", "menu": "menu", "help": "menu", "?": "menu", "？": "menu",
}
RESET_WORDS = {"重來", "取消", "算了", "不用了"}


class BookingBot:
    def __init__(
        self,
        store: Store,
        config=shop_config,
        now: Callable[[], datetime] = lambda: datetime.now(TZ),
        notify_owner: Callable[[str], None] | None = None,
    ):
        self.store, self.cfg, self.now = store, config, now
        self.notify_owner = notify_owner or (lambda _text: None)

    # ---------- 入口 ----------

    def handle_text(self, user_id: str, text: str) -> Reply:
        text = text.strip()
        last_options = self.store.load_options(user_id)
        if text in last_options:  # 客人用打字的方式選了上一則訊息的選項
            return self.handle_postback(user_id, last_options[text])
        if text.lower() in KEYWORDS:
            return self.handle_postback(user_id, q(action=KEYWORDS[text.lower()]))
        if text in RESET_WORDS:
            return self._respond(user_id, self._menu("好的，已取消目前的操作。"))
        return self._respond(user_id, self._menu("不好意思，我只看得懂預約相關的指令 🙏"))

    def handle_postback(self, user_id: str, data: str) -> Reply:
        p = dict(parse_qsl(data))
        action = p.get("action")
        if action == "book":
            reply = self._book(user_id, p)
        elif action == "mine":
            reply = self._mine(user_id)
        elif action == "cancel":
            reply = self._cancel(user_id, p)
        else:
            reply = self._menu()
        return self._respond(user_id, reply)

    def _respond(self, user_id: str, reply: Reply) -> Reply:
        self.store.save_options(user_id, {o.label: o.data for o in reply.options}, self.now())
        return reply

    # ---------- 共用 ----------

    def _menu(self, prefix: str = "") -> Reply:
        text = (prefix + "\n\n" if prefix else "") + f"歡迎來到{self.cfg.SHOP_NAME}！請選擇要做什麼："
        return Reply(text, [
            Option("📅 我要預約", q(action="book")),
            Option("📋 我的預約", q(action="mine")),
            Option("❌ 取消預約", q(action="cancel")),
        ])

    def _service(self, code: str):
        name, minutes, price = self.cfg.SERVICES[code]
        return name, timedelta(minutes=minutes), price

    def bookable_days(self) -> list[date]:
        today = self.now().date()
        return [today + timedelta(days=i) for i in range(self.cfg.DAYS_AHEAD)]

    def available_starts(self, svc: str, day: date) -> list[datetime]:
        hours = self.cfg.OPENING_HOURS.get(day.weekday())
        if not hours or day not in self.bookable_days():
            return []
        _, duration, _ = self._service(svc)
        opening = datetime.combine(day, hours[0], TZ)
        closing = datetime.combine(day, hours[1], TZ)
        earliest = self.now() + timedelta(minutes=self.cfg.LEAD_MINUTES)
        slots, t = [], opening
        while t + duration <= closing:
            if t >= earliest and self.store.busiest(t, t + duration) < self.cfg.STAFF:
                slots.append(t)
            t += timedelta(minutes=self.cfg.SLOT_MINUTES)
        return slots

    # ---------- 預約流程 ----------

    def _book(self, user_id: str, p: dict) -> Reply:
        svc = p.get("svc")
        if svc not in self.cfg.SERVICES:
            if len(self.store.upcoming_for(user_id, self.now())) >= self.cfg.MAX_ACTIVE_BOOKINGS:
                return self._menu(f"您目前已有 {self.cfg.MAX_ACTIVE_BOOKINGS} 筆預約，請先完成或取消後再預約。")
            lines = [f"・{n}　約 {m} 分鐘　NT${price:,}" for n, m, price in self.cfg.SERVICES.values()]
            return Reply("請選擇服務項目：\n" + "\n".join(lines),
                         [Option(n, q(action="book", svc=code)) for code, (n, _, _) in self.cfg.SERVICES.items()])

        name, duration, price = self._service(svc)
        if "date" not in p:
            days = [d for d in self.bookable_days() if self.available_starts(svc, d)]
            if not days:
                return self._menu(f"抱歉，未來 {self.cfg.DAYS_AHEAD} 天的「{name}」都已額滿。")
            return Reply(f"「{name}」要預約哪一天？",
                         [Option(fmt_day(d), q(action="book", svc=svc, date=d.isoformat())) for d in days])

        try:
            day = date.fromisoformat(p["date"])
        except ValueError:
            return self._book(user_id, {"svc": svc})

        if "start" not in p:
            return self._time_picker(svc, day, int(p.get("page", 0)))

        try:
            start = datetime.fromisoformat(p["start"]).astimezone(TZ)
        except ValueError:
            return self._time_picker(svc, day, 0)
        if start not in self.available_starts(svc, day):
            return self._time_picker(svc, day, 0, notice=f"{fmt_dt(start)} 已經無法預約，請重新選擇。")

        if p.get("confirm") != "1":
            return Reply(
                f"請確認預約內容：\n服務：{name}（約 {duration.seconds // 60} 分鐘）\n"
                f"時間：{fmt_dt(start)}\n價格：NT${price:,}",
                [
                    Option("✅ 確認預約", q(action="book", svc=svc, date=day.isoformat(), start=start.isoformat(), confirm=1)),
                    Option("🔄 換時間", q(action="book", svc=svc, date=day.isoformat())),
                    Option("✖ 不預約了", q(action="menu")),
                ],
            )

        if len(self.store.upcoming_for(user_id, self.now())) >= self.cfg.MAX_ACTIVE_BOOKINGS:
            return self._menu(f"您目前已有 {self.cfg.MAX_ACTIVE_BOOKINGS} 筆預約，請先完成或取消後再預約。")
        try:
            booking = self.store.create(user_id, svc, start, start + duration, self.cfg.STAFF, self.now())
        except SlotTaken:
            return self._time_picker(svc, day, 0, notice="哎呀，這個時段剛剛被訂走了，請改選其他時間。")
        self.notify_owner(f"🆕 新預約 {booking.code}\n{name}　{fmt_dt(start)}")
        return Reply(
            f"🎉 預約成功！\n預約編號：{booking.code}\n服務：{name}\n時間：{fmt_dt(start)}\n\n"
            "如需取消，請輸入「取消預約」。期待您的光臨！",
            [Option("📋 我的預約", q(action="mine")), Option("📅 再預約一筆", q(action="book"))],
        )

    def _time_picker(self, svc: str, day: date, page: int, notice: str = "") -> Reply:
        name, _, _ = self._service(svc)
        slots = self.available_starts(svc, day)
        if not slots:
            reply = self._book("", {"svc": svc})
            reply.text = f"{fmt_day(day)} 已經沒有可預約的時段。\n" + reply.text
            return reply
        pages = (len(slots) - 1) // SLOTS_PER_PAGE + 1
        page = min(max(page, 0), pages - 1)
        shown = slots[page * SLOTS_PER_PAGE:(page + 1) * SLOTS_PER_PAGE]
        base = {"action": "book", "svc": svc, "date": day.isoformat()}
        options = [Option(f"{t:%H:%M}", q(**base, start=t.isoformat())) for t in shown]
        if page > 0:
            options.append(Option("◀ 較早時段", q(**base, page=page - 1)))
        if page < pages - 1:
            options.append(Option("較晚時段 ▶", q(**base, page=page + 1)))
        options.append(Option("📆 換日期", q(action="book", svc=svc)))
        header = f"{notice}\n" if notice else ""
        return Reply(f"{header}{fmt_day(day)}「{name}」可預約的時間（共 {len(slots)} 個）：", options)

    # ---------- 查詢與取消 ----------

    def _describe(self, b: Booking) -> str:
        return f"{fmt_dt(b.start)} {self.cfg.SERVICES[b.service][0]}"

    def _mine(self, user_id: str) -> Reply:
        bookings = self.store.upcoming_for(user_id, self.now())
        if not bookings:
            return self._menu("您目前沒有預約。")
        lines = [f"・{b.code}　{self._describe(b)}" for b in bookings]
        return self._menu("您的預約：\n" + "\n".join(lines))

    def _cancel(self, user_id: str, p: dict) -> Reply:
        bookings = {b.id: b for b in self.store.upcoming_for(user_id, self.now())}
        if not bookings:
            return self._menu("您目前沒有可取消的預約。")
        booking = bookings.get(int(p["id"])) if p.get("id", "").isdigit() else None
        if booking is None:
            options = [Option(self._describe(b)[:20], q(action="cancel", id=b.id)) for b in bookings.values()]
            return Reply("要取消哪一筆預約？", options + [Option("↩ 返回", q(action="menu"))])
        if p.get("confirm") != "1":
            return Reply(f"確定要取消這筆預約嗎？\n{booking.code}　{self._describe(booking)}", [
                Option("確定取消", q(action="cancel", id=booking.id, confirm=1)),
                Option("保留預約", q(action="menu")),
            ])
        if not self.store.cancel(booking.id, user_id):
            return self._menu("這筆預約已經取消過了。")
        self.notify_owner(f"❌ 取消預約 {booking.code}\n{self._describe(booking)}")
        return self._menu(f"已取消 {booking.code}（{self._describe(booking)}）。")
