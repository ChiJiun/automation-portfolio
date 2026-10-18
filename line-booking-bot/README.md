# LINE 預約機器人：讓客人在 LINE 上自己選服務、日期、時段

> **適合誰**：髮廊、美甲、診所、工作室、補習班。不想再一則一則回訊息排時間的店家。

## 客人看到的流程

客人全程只需要點按鈕（LINE 快速回覆），也可以直接打字：

```
客人：預約
Bot ：請選擇服務項目：剪髮 / 洗髮造型 / 染髮 / 燙髮
客人：（點）剪髮
Bot ：「剪髮」要預約哪一天？10/20(二) / 10/21(三) / …（公休日自動不顯示）
客人：（點）10/20(二)
Bot ：可預約的時間（共 19 個）：10:00 / 10:30 / 11:00 / … / 較晚時段 ▶
客人：（點）11:00
Bot ：請確認：剪髮（約 60 分鐘）10/20(二) 11:00 NT$500  [✅ 確認預約]
客人：（點）✅ 確認預約
Bot ：🎉 預約成功！預約編號：B00001
店家：📣 收到推播「🆕 新預約 B00001 剪髮 10/20(二) 11:00」
```

完整對話紀錄：[examples/demo-conversation.txt](examples/demo-conversation.txt)

## 功能

- **預約、查詢、取消**：客人自己完成，取消時店家也會收到通知
- **自動計算空檔**：依營業時間、公休日、服務時長、設計師人數計算可預約的時段
- **不會重複預約**：在資料庫交易內再確認一次名額，兩人同時搶同一時段也只有一人成功
- **正確處理不同長度的服務**：10–11 點和 11–12 點各有一位客人時，10–12 點的染髮仍然可以預約
- **防呆**：
  - 必須提前一段時間預約
  - 每人最多同時持有 3 筆預約
  - 點到舊按鈕或已額滿的時段時，會請客人重選
  - 竄改按鈕資料也訂不到不存在的時段
- **Webhook 簽章驗證**：只接受 LINE 平台送來的請求

## 先試玩（不需要 LINE 帳號）

```bash
pip install -r requirements.txt
python simulator.py
```

在終端機裡輸入選項的數字，就能走完整個預約流程。適合直接 demo 給客戶看。

## 串接真正的 LINE

1. 到 [LINE Developers](https://developers.line.biz/) 建立 Messaging API channel
2. `cp .env.example .env`，填入 Channel secret 與 Channel access token
3. `python app.py`，用 ngrok 等工具公開 `http://localhost:5000/callback`
4. 把公開網址填到後台的 Webhook URL，並開啟「Use webhook」
5. （選填）在 `.env` 填入店家自己的 `OWNER_USER_ID`，就能收到預約通知

正式上線可以部署到 Render、Railway、Fly.io 或客戶自己的主機。

## 換成客戶的店

大部分只需要改 [`shop_config.py`](shop_config.py)：店名、服務項目與時長、價格、各天營業時間、設計師人數、開放預約的天數。

## 程式架構

```
shop_config.py   店家設定
booking.py       對話與預約邏輯（不依賴 LINE，可單獨測試）
db.py            SQLite：預約資料、防止重複預約
app.py           Flask webhook，把 LINE 事件轉給 booking.py
simulator.py     終端機模擬器
```

每個按鈕都帶齊目前的選擇（例如 `action=book&svc=cut&date=2026-10-20`），不需要記住客人進行到哪一步。伺服器重啟、客人隔天才點按鈕，流程都能接續。

## 常見延伸需求

- 店家後台網頁：查看、修改當日預約
- 前一天自動推播提醒
- 指定設計師
- 改用 Google 日曆或 Google Sheets 存資料
- Rich Menu 圖文選單

## 測試

```bash
pip install pytest
python -m pytest tests
```

共 18 個測試，包含完整預約流程、額滿、重疊計算、併發搶位、取消權限、分頁、竄改資料，以及用真實簽章模擬 LINE 呼叫 webhook。
