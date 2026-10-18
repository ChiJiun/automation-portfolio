"""商品資料爬蟲：抓列表 → 進每一頁抓細節 → 清理 → 輸出 CSV / Excel。

示範目標是 books.toscrape.com（專門開放給人練習爬蟲的網站）。
換成客戶指定的網站時，只需要改 parse_list_page / parse_detail_page 兩個函式。

用法：
    python scraper.py                            # 抓全站 1000 本書（約 1～2 分鐘）
    python scraper.py --max-pages 2 --details    # 只抓前 2 頁，並進入每本書抓 UPC、庫存、簡介
    python scraper.py --category travel_2 -o output/travel.csv --xlsx
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
USER_AGENT = "portfolio-demo-scraper/1.0 (+https://github.com/)"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

log = logging.getLogger("scraper")


@dataclass
class Book:
    title: str
    price: float
    rating: int
    in_stock: bool
    url: str
    category: str = ""
    upc: str = ""
    stock_count: int | None = None
    description: str = ""


# ---------- 解析（純函式，方便測試、換網站時只改這裡） ----------

def parse_price(text: str) -> float:
    """「£51.77」、「Â£51.77」(編碼錯誤)、「NT$1,280」→ 數字。"""
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"找不到價格：{text!r}")
    return float(match.group().replace(",", ""))


def parse_list_page(html: str, page_url: str) -> tuple[list[Book], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        rating_class = next((c for c in card.select_one("p.star-rating")["class"] if c in RATINGS), None)
        books.append(
            Book(
                title=link["title"].strip(),
                price=parse_price(card.select_one("p.price_color").get_text()),
                rating=RATINGS.get(rating_class, 0),
                in_stock="In stock" in card.select_one("p.availability").get_text(),
                url=urljoin(page_url, link["href"]),
            )
        )
    next_link = soup.select_one("li.next a")
    return books, urljoin(page_url, next_link["href"]) if next_link else None


def parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    table = {row.th.get_text(strip=True): row.td.get_text(strip=True) for row in soup.select("table.table tr")}
    stock = re.search(r"\((\d+) available\)", table.get("Availability", ""))
    desc = soup.select_one("#product_description + p")
    crumbs = soup.select("ul.breadcrumb li a")
    return {
        "upc": table.get("UPC", ""),
        "stock_count": int(stock.group(1)) if stock else 0,
        "description": desc.get_text(strip=True) if desc else "",
        "category": crumbs[-1].get_text(strip=True) if len(crumbs) >= 3 else "",
    }


# ---------- 抓取（禮貌爬取：robots.txt、間隔、重試） ----------

class Scraper:
    def __init__(self, session: requests.Session | None = None, delay: float = 0.5, retries: int = 3):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.delay, self.retries = delay, retries
        self._robots: dict[str, robotparser.RobotFileParser] = {}
        self.requests_made = 0

    def allowed(self, url: str) -> bool:
        root = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{root}/robots.txt", timeout=10)
                # 404 代表網站沒有限制；其他錯誤保守起見當作全部允許但記錄下來
                rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except requests.RequestException as exc:
                log.warning("讀不到 %s/robots.txt：%s", root, exc)
                rp.parse([])
            self._robots[root] = rp
        return self._robots[root].can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> str:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt 不允許抓取 {url}")
        for attempt in range(1, self.retries + 1):
            try:
                time.sleep(self.delay if self.requests_made else 0)
                self.requests_made += 1
                resp = self.session.get(url, timeout=15)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            except requests.RequestException as exc:
                status = getattr(exc.response, "status_code", None)
                if attempt == self.retries or (status is not None and status < 500 and status != 429):
                    raise
                wait = 2 ** attempt
                log.warning("第 %d 次抓取失敗（%s），%d 秒後重試：%s", attempt, exc, wait, url)
                time.sleep(wait)
        raise AssertionError("unreachable")

    def crawl(self, start_url: str, max_pages: int | None = None, details: bool = False) -> list[Book]:
        books, url, page = [], start_url, 0
        while url and (max_pages is None or page < max_pages):
            page += 1
            found, url = parse_list_page(self.fetch(url), url)
            log.info("第 %d 頁：%d 本", page, len(found))
            books.extend(found)
        if details:
            for i, book in enumerate(books, 1):
                try:
                    for key, value in parse_detail_page(self.fetch(book.url)).items():
                        setattr(book, key, value)
                except requests.RequestException as exc:
                    log.error("細節頁失敗，略過：%s（%s）", book.url, exc)
                if i % 20 == 0:
                    log.info("細節頁進度 %d/%d", i, len(books))
        return books


# ---------- 輸出 ----------

COLUMN_NAMES = {
    "title": "書名", "price": "價格(GBP)", "rating": "評分", "in_stock": "有庫存", "url": "網址",
    "category": "分類", "upc": "UPC", "stock_count": "庫存數量", "description": "簡介",
}


def save_csv(books: list[Book], path: Path, include_details: bool) -> None:
    keys = [f.name for f in fields(Book)]
    if not include_details:
        keys = [k for k in keys if k not in {"category", "upc", "stock_count", "description"}]
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：讓 Excel 直接開啟也不會亂碼
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=[COLUMN_NAMES[k] for k in keys])
        writer.writeheader()
        for book in books:
            row = asdict(book)
            writer.writerow({COLUMN_NAMES[k]: row[k] for k in keys})


def save_xlsx(csv_path: Path) -> Path:
    import pandas as pd

    out = csv_path.with_suffix(".xlsx")
    pd.read_csv(csv_path, encoding="utf-8-sig").to_excel(out, index=False)
    return out


def dedupe(books: list[Book]) -> list[Book]:
    seen, unique = set(), []
    for book in books:
        if book.url not in seen:
            seen.add(book.url)
            unique.append(book)
    return unique


def main(argv=None):
    parser = argparse.ArgumentParser(description="爬取 books.toscrape.com 並輸出 CSV")
    parser.add_argument("--category", help="分類代號，例如 travel_2（見網站左側分類網址）")
    parser.add_argument("--max-pages", type=int, help="最多抓幾頁列表（每頁 20 本）")
    parser.add_argument("--details", action="store_true", help="進入每本書的頁面抓 UPC、庫存數量、簡介")
    parser.add_argument("--delay", type=float, default=0.5, help="每次請求間隔秒數（預設 0.5）")
    parser.add_argument("-o", "--output", type=Path, default=Path("output/books.csv"))
    parser.add_argument("--xlsx", action="store_true", help="另外輸出一份 Excel")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    start = urljoin(BASE_URL, f"catalogue/category/books/{args.category}/index.html") if args.category else BASE_URL
    scraper = Scraper(delay=args.delay)
    started = time.perf_counter()
    books = dedupe(scraper.crawl(start, max_pages=args.max_pages, details=args.details))
    save_csv(books, args.output, include_details=args.details)

    elapsed = time.perf_counter() - started
    avg = sum(b.price for b in books) / len(books) if books else 0
    print(f"完成：{len(books)} 筆，{scraper.requests_made} 次請求，耗時 {elapsed:.1f} 秒，平均價格 £{avg:.2f}")
    print(f"已輸出 {args.output}")
    if args.xlsx:
        print(f"已輸出 {save_xlsx(args.output)}")


if __name__ == "__main__":
    main()
