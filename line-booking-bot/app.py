"""LINE Messaging API webhook（Flask + line-bot-sdk v3）。

本機執行：
    cp .env.example .env    # 填入 Channel secret / access token
    python app.py           # 預設 http://localhost:5000/callback
再用 ngrok 等工具把網址公開，填到 LINE Developers 後台的 Webhook URL。
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PostbackAction,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import FollowEvent, MessageEvent, PostbackEvent, TextMessageContent

from booking import BookingBot, Reply
from db import Store

log = logging.getLogger("line-booking-bot")


def to_line_message(reply: Reply) -> TextMessage:
    quick_reply = None
    if reply.options:
        quick_reply = QuickReply(items=[
            # display_text：客人點了之後，聊天室裡會像是客人自己說了這句話
            QuickReplyItem(action=PostbackAction(label=o.label[:20], data=o.data, display_text=o.label))
            for o in reply.options[:13]
        ])
    return TextMessage(text=reply.text, quick_reply=quick_reply)


class LineMessenger:
    def __init__(self, access_token: str):
        self.configuration = Configuration(access_token=access_token)

    def reply(self, reply_token: str, reply: Reply) -> None:
        with ApiClient(self.configuration) as client:
            MessagingApi(client).reply_message(
                ReplyMessageRequest(reply_token=reply_token, messages=[to_line_message(reply)])
            )

    def push(self, user_id: str, text: str) -> None:
        with ApiClient(self.configuration) as client:
            MessagingApi(client).push_message(PushMessageRequest(to=user_id, messages=[TextMessage(text=text)]))


def create_app(channel_secret: str, messenger, store: Store, owner_user_id: str | None = None) -> Flask:
    app = Flask(__name__)
    handler = WebhookHandler(channel_secret)

    def notify_owner(text: str) -> None:
        if owner_user_id:
            try:
                messenger.push(owner_user_id, text)
            except Exception:  # 通知失敗不能讓客人的預約失敗
                log.exception("通知店家失敗")

    bot = BookingBot(store, notify_owner=notify_owner)

    @handler.add(MessageEvent, message=TextMessageContent)
    def on_text(event):
        messenger.reply(event.reply_token, bot.handle_text(event.source.user_id, event.message.text))

    @handler.add(PostbackEvent)
    def on_postback(event):
        messenger.reply(event.reply_token, bot.handle_postback(event.source.user_id, event.postback.data))

    @handler.add(FollowEvent)
    def on_follow(event):  # 客人加好友時
        messenger.reply(event.reply_token, bot.handle_postback(event.source.user_id, "action=menu"))

    @app.post("/callback")
    def callback():
        signature = request.headers.get("X-Line-Signature", "")
        body = request.get_data(as_text=True)
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            abort(400)  # 不是 LINE 送來的請求
        return "OK"

    @app.get("/")
    def health():
        return "LINE booking bot is running"

    app.extensions["booking_bot"] = bot
    return app


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    secret = os.environ.get("LINE_CHANNEL_SECRET")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not secret or not token:
        raise SystemExit("請先在 .env 設定 LINE_CHANNEL_SECRET 與 LINE_CHANNEL_ACCESS_TOKEN（可參考 .env.example）")
    app = create_app(
        secret,
        LineMessenger(token),
        Store(os.environ.get("DATABASE_PATH", "bookings.db")),
        owner_user_id=os.environ.get("OWNER_USER_ID") or None,
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


if __name__ == "__main__":
    main()
