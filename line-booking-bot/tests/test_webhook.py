"""模擬 LINE 平台呼叫 webhook：用 channel secret 簽章，確認驗證與回覆都正確。"""
import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, to_line_message  # noqa: E402
from booking import Option, Reply  # noqa: E402
from db import Store  # noqa: E402

SECRET = "test-channel-secret"


class FakeMessenger:
    def __init__(self):
        self.replies, self.pushes = [], []

    def reply(self, token, reply):
        self.replies.append((token, reply))

    def push(self, user_id, text):
        self.pushes.append((user_id, text))


def event(kind, **extra):
    base = {
        "type": kind,
        "mode": "active",
        "timestamp": 1760000000000,
        "source": {"type": "user", "userId": "U-customer"},
        "replyToken": "reply-token-1",
        "webhookEventId": "01TEST",
        "deliveryContext": {"isRedelivery": False},
    }
    return {**base, **extra}


def post(client, payload, secret=SECRET):
    body = json.dumps({"destination": "U-bot", "events": [payload]}, ensure_ascii=False)
    signature = base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()
    return client.post("/callback", data=body.encode(), headers={"X-Line-Signature": signature,
                                                                 "Content-Type": "application/json"})


def make_client():
    messenger = FakeMessenger()
    app = create_app(SECRET, messenger, Store(":memory:"), owner_user_id="U-owner")
    return app.test_client(), messenger


def test_text_message_gets_reply():
    client, messenger = make_client()
    resp = post(client, event("message", message={"type": "text", "id": "1", "text": "預約", "quoteToken": "q"}))
    assert resp.status_code == 200
    token, reply = messenger.replies[0]
    assert token == "reply-token-1"
    assert "請選擇服務項目" in reply.text


def test_postback_is_routed():
    client, messenger = make_client()
    post(client, event("postback", postback={"data": "action=book&svc=cut"}))
    assert "要預約哪一天" in messenger.replies[0][1].text


def test_follow_event_shows_menu():
    client, messenger = make_client()
    post(client, event("follow", follow={"isUnblocked": False}))
    assert "歡迎來到" in messenger.replies[0][1].text


def test_invalid_signature_rejected():
    client, messenger = make_client()
    resp = post(client, event("postback", postback={"data": "action=menu"}), secret="wrong-secret")
    assert resp.status_code == 400
    assert messenger.replies == []


def test_line_message_shape():
    options = [Option(f"選項{i}", f"action=menu&i={i}") for i in range(15)]
    msg = to_line_message(Reply("hi", options)).to_dict()
    items = msg["quickReply"]["items"]
    assert len(items) == 13  # LINE 上限
    assert items[0]["action"] == {"type": "postback", "label": "選項0", "data": "action=menu&i=0",
                                  "displayText": "選項0"}
