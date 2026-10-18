# 自動化作品集：把重複的手工作業交給程式

我專門幫小型企業與店家把**每天、每月重複做的事**自動化：整理 Excel 報表、蒐集網站資料、用 LINE 自動接預約。

以下三個作品都可以直接下載執行，也都附有自動化測試。

| 作品 | 解決的問題 | 一句話說明 |
|---|---|---|
| [📊 Excel 自動月報](excel-auto-report/) | 各分店寄來的 Excel 格式不一，每月要花半天整理 | 一行指令合併、清理髒資料，產出含圖表的月報，並列出每一筆被修正的資料 |
| [🕷️ 網站資料爬蟲](scraper-to-csv/) | 手動複製網站上的商品、價格、名錄 | 自動翻頁、進入細節頁、清理後輸出 Excel 可直接開的 CSV，遵守 robots.txt 並會自動重試 |
| [💬 LINE 預約機器人](line-booking-bot/) | 店家一則一則回訊息排時間 | 客人在 LINE 上點按鈕完成預約、查詢、取消，自動計算空檔、防止重複預約、即時通知店家 |

## 快速試用

```bash
pip install -r excel-auto-report/requirements.txt -r scraper-to-csv/requirements.txt -r line-booking-bot/requirements.txt

cd excel-auto-report && python make_sample_data.py && python report.py "data/*.xlsx"
cd ../scraper-to-csv && python scraper.py --max-pages 2
cd ../line-booking-bot && python simulator.py
```

不想安裝也可以直接看範例輸出：

- [銷售月報範例.xlsx](excel-auto-report/examples/銷售月報_2026-09.xlsx)
- [爬蟲輸出範例.csv](scraper-to-csv/examples/books_sample.csv)
- [LINE 預約對話紀錄](line-booking-bot/examples/demo-conversation.txt)

## 測試

```bash
pip install -r requirements-dev.txt
python -m pytest excel-auto-report/tests
python -m pytest scraper-to-csv/tests
python -m pytest line-booking-bot/tests
```

共 33 個測試：Excel 6 個、爬蟲 9 個、LINE bot 18 個。

## 我的工作方式

1. **先確認需求**：免費討論，確認要處理的資料、要產出的格式、交期
2. **報價與分期**：固定價格，先收訂金，交件驗收後付尾款
3. **交付**：程式碼、使用說明、測試。需要的話也協助部署與教學
4. **保固**：交件後一段時間內，免費修正因原始需求範圍內的錯誤

開發時使用 AI 輔助工具（Claude Code）加快速度。每一份交付的程式都經過我自己檢查，並附上自動化測試。

## 聯絡我

- 出任務 Tasker：https://www.tasker.com.tw/workroom/gino-lab
- GitHub：https://github.com/ChiJiun
- Email：0311gino@gmail.com

技術：Python · pandas · openpyxl · requests · BeautifulSoup · Flask · LINE Messaging API · SQLite · pytest
