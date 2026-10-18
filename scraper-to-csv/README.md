# 網站資料爬蟲：自動抓取商品資料並輸出 CSV / Excel

> **適合誰**：需要定期整理競品價格、商品清單、公開名錄，卻還在手動複製貼上的人。

示範目標是 [books.toscrape.com](https://books.toscrape.com/)，這是專門開放給人練習爬蟲的網站，共 50 頁、1,000 本書。

## 功能

- **自動翻頁**：沿著「下一頁」抓完整個列表，也可以用 `--max-pages` 限制頁數
- **進入細節頁**：`--details` 會進入每個商品頁，抓 UPC、庫存數量、分類、簡介
- **資料清理**：價格轉成數字（連編碼錯誤的 `Â£` 也能處理）、星等轉成 1–5、網址轉成完整網址、依網址去除重複
- **禮貌爬取**：遵守 robots.txt、每次請求之間有間隔、帶 User-Agent
- **自動重試**：遇到 429 / 5xx 或網路錯誤時，以指數退避重試；404 這類錯誤不重試，直接回報
- **Excel 友善**：CSV 用 UTF-8 BOM 輸出，Excel 直接開啟中文不會亂碼；加上 `--xlsx` 另外輸出 Excel 檔

## 使用方式

```bash
pip install -r requirements.txt
python scraper.py --max-pages 2 --details --xlsx   # 前 2 頁 40 本，含細節
python scraper.py --category travel_2 -o output/travel.csv
python scraper.py                                  # 全站 1,000 本
```

輸出範例：[examples/books_sample.csv](examples/books_sample.csv)

```
12:00:01 INFO 第 1 頁：20 本
12:00:02 INFO 第 2 頁：20 本
12:00:17 INFO 細節頁進度 20/40
12:00:32 INFO 細節頁進度 40/40
完成：40 筆，42 次請求，耗時 32.0 秒，平均價格 £34.96
```

| 書名 | 價格(GBP) | 評分 | 有庫存 | 分類 | UPC | 庫存數量 |
|---|---|---|---|---|---|---|
| A Light in the Attic | 51.77 | 3 | True | Poetry | a897fe39b1053632 | 22 |

## 程式架構

```
parse_list_page()    純函式：HTML → 商品列表 + 下一頁網址
parse_detail_page()  純函式：HTML → 細節欄位
Scraper              負責連線：robots.txt、間隔、重試
save_csv / save_xlsx 輸出
```

**換成其他網站時，通常只需要改兩個 `parse_*` 函式裡的 CSS 選擇器**，連線、重試、輸出的部分都可以沿用。

## 接案前會先確認的事

- 目標網站的使用條款與 robots.txt 是否允許抓取
- 是否需要登入。需要登入的資料要另外評估，我不接繞過驗證或防護機制的需求
- 抓取頻率，避免對對方伺服器造成負擔
- 動態載入（JavaScript 渲染）的網站要改用 Playwright，報價會不同

## 測試

```bash
pip install pytest
python -m pytest tests
```

測試完全離線，使用假的 HTML 與假的連線，涵蓋解析、翻頁、細節頁、重試、遵守 robots.txt、CSV 編碼。
