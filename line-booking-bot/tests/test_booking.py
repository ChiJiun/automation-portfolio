import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from booking import TZ, BookingBot  # noqa: E402
from db import SlotTaken, Store  # noqa: E402

# 2026-10-19 是星期一（公休），10-20 星期二 10:00–20:00 營業
NOW = datetime(2026, 10, 19, 15, 0, tzinfo=TZ)


@pytest.fixture
def notices():
    return []


@pytest.fixture
def bot(notices):
    return BookingBot(Store(":memory:"), now=lambda: NOW, notify_owner=notices.append)


def pick(reply, label):
    """模擬客人點某個選項，回傳該選項的 data。"""
    for option in reply.options:
        if option.label == label:
            return option.data
    raise AssertionError(f"找不到選項 {label!r}，現有：{[o.label for o in reply.options]}")


def book(bot, user, svc="剪髮", day="10/20(二)", time="10:00"):
    r = bot.handle_postback(user, "action=book")
    r = bot.handle_postback(user, pick(r, svc))
    r = bot.handle_postback(user, pick(r, day))
    r = bot.handle_postback(user, pick(r, time))
    return bot.handle_postback(user, pick(r, "✅ 確認預約"))


def test_full_booking_flow(bot, notices):
    reply = book(bot, "U1")
    assert "預約成功" in reply.text and "B00001" in reply.text
    assert notices == ["🆕 新預約 B00001\n剪髮　10/20(二) 10:00"]
    assert "B00001　10/20(二) 10:00 剪髮" in bot.handle_text("U1", "我的預約").text


def test_closed_day_and_today_lead_time(bot):
    r = bot.handle_postback("U1", "action=book&svc=cut")
    labels = [o.label for o in r.options]
    assert "10/19(一)" not in labels  # 星期一公休
    assert labels[0] == "10/20(二)"
    assert len(labels) == 6  # 7 天扣掉公休日


def test_lead_time_hides_slots_too_soon(bot):
    # 星期二 15:00 時，16:00 以前的時段都不能訂（LEAD_MINUTES=60）
    tuesday_bot = BookingBot(bot.store, now=lambda: datetime(2026, 10, 20, 15, 0, tzinfo=TZ))
    starts = tuesday_bot.available_starts("cut", datetime(2026, 10, 20).date())
    assert starts[0].strftime("%H:%M") == "16:00"
    assert starts[-1].strftime("%H:%M") == "19:00"  # 60 分鐘的服務最晚 19:00 開始


def test_slot_disappears_when_full(bot):
    book(bot, "U1")
    book(bot, "U2")  # STAFF=2，同時段第二位
    times = [o.label for o in bot.handle_postback("U3", "action=book&svc=cut&date=2026-10-20").options]
    assert "10:00" not in times and "10:30" not in times  # 跟 10:00–11:00 重疊
    assert "11:00" in times


def test_non_overlapping_bookings_do_not_block_long_service(bot):
    book(bot, "U1", time="10:00")  # 10:00–11:00
    book(bot, "U2", time="11:00")  # 11:00–12:00
    # 染髮 10:00–12:00：同一時刻最多只有 1 人，還有 1 位設計師有空
    starts = bot.available_starts("color", datetime(2026, 10, 20).date())
    assert datetime(2026, 10, 20, 10, 0, tzinfo=TZ) in starts


def test_stale_confirm_button_is_rejected(bot):
    r = bot.handle_postback("U3", "action=book&svc=cut&date=2026-10-20")
    stale_confirm = bot.handle_postback("U3", pick(r, "10:00"))
    book(bot, "U1")
    book(bot, "U2")
    reply = bot.handle_postback("U3", pick(stale_confirm, "✅ 確認預約"))
    assert "已經無法預約" in reply.text


def test_store_rejects_double_booking_race():
    store = Store(":memory:")
    start, end = datetime(2026, 10, 20, 10, 0, tzinfo=TZ), datetime(2026, 10, 20, 11, 0, tzinfo=TZ)
    store.create("U1", "cut", start, end, capacity=1, now=NOW)
    with pytest.raises(SlotTaken):
        store.create("U2", "cut", start, end, capacity=1, now=NOW)


def test_typed_text_matches_last_options(bot):
    bot.handle_text("U1", "預約")
    reply = bot.handle_text("U1", "染髮")  # 用打字代替點按鈕
    assert reply.text == "「染髮」要預約哪一天？"


def test_cancel_flow_and_ownership(bot, notices):
    book(bot, "U1")
    # 別人不能取消 U1 的預約
    assert "沒有可取消" in bot.handle_postback("U2", "action=cancel&id=1&confirm=1").text
    r = bot.handle_text("U1", "取消預約")
    r = bot.handle_postback("U1", pick(r, "10/20(二) 10:00 剪髮"))
    r = bot.handle_postback("U1", pick(r, "確定取消"))
    assert "已取消 B00001" in r.text
    assert notices[-1].startswith("❌ 取消預約 B00001")
    assert "沒有預約" in bot.handle_text("U1", "我的預約").text


def test_max_active_bookings(bot):
    for time in ["10:00", "12:00", "14:00"]:
        book(bot, "U1", time=time)
    assert "已有 3 筆預約" in bot.handle_text("U1", "預約").text


def test_time_picker_pagination(bot):
    r = bot.handle_postback("U1", "action=book&svc=wash&date=2026-10-20")  # 30 分鐘服務，20 個起始時間
    assert len(r.options) <= 13
    r2 = bot.handle_postback("U1", pick(r, "較晚時段 ▶"))
    assert r2.options[0].label == "15:00"
    assert "◀ 較早時段" in [o.label for o in r2.options]


def test_tampered_postback_is_safe(bot):
    assert "請選擇服務項目" in bot.handle_postback("U1", "action=book&svc=hack").text
    r = bot.handle_postback("U1", "action=book&svc=cut&date=2026-10-20&start=2026-10-20T03:00:00%2B08:00&confirm=1")
    assert "已經無法預約" in r.text
    assert bot.store.upcoming_for("U1", NOW) == []


def test_unknown_text_shows_menu(bot):
    reply = bot.handle_text("U1", "你好")
    assert "看得懂預約相關" in reply.text
    assert {dict(parse_qsl(o.data))["action"] for o in reply.options} == {"book", "mine", "cancel"}
