"""不用 LINE 帳號，在終端機裡跟預約 bot 對話（給客戶 demo 或自己測試用）。

    python simulator.py
輸入選項前面的數字，或直接打字（例如「預約」「我的預約」）；輸入 q 離開。
資料存在記憶體裡，關掉就清空。
"""
import sys

from booking import BookingBot
from db import Store


def show(reply):
    print("\n🤖 " + reply.text.replace("\n", "\n   "))
    for i, option in enumerate(reply.options, 1):
        print(f"   [{i}] {option.label}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 終端機顯示 emoji
    bot = BookingBot(Store(":memory:"), notify_owner=lambda text: print("\n   📣 (通知店家) " + text.replace("\n", " ")))
    user = "U-demo"
    reply = bot.handle_postback(user, "action=menu")
    show(reply)
    while True:
        try:
            text = input("\n🙋 ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {"q", "quit", "exit"}:
            break
        if text.isdigit() and 1 <= int(text) <= len(reply.options):
            option = reply.options[int(text) - 1]
            print(f"   （點選「{option.label}」）")
            reply = bot.handle_postback(user, option.data)
        else:
            reply = bot.handle_text(user, text)
        show(reply)


if __name__ == "__main__":
    main()
