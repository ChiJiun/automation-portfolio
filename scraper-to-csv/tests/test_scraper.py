"""離線測試：用假的 HTML 與假的 Session，不會連到網路。"""
import csv
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scraper  # noqa: E402

BASE = "https://example.test/"


def card(title, price, rating, href, stock="In stock"):
    return f"""
    <article class="product_pod">
      <p class="star-rating {rating}"></p>
      <h3><a href="{href}" title="{title}">{title[:10]}...</a></h3>
      <p class="price_color">{price}</p>
      <p class="instock availability">{stock}</p>
    </article>"""


PAGE1 = f"""<html><body>
{card("Book One", "£10.50", "Three", "catalogue/one/index.html")}
{card("Book Two", "Â£1,200.00", "Five", "catalogue/two/index.html", stock="Out of stock")}
<ul class="pager"><li class="next"><a href="catalogue/page-2.html">next</a></li></ul>
</body></html>"""

PAGE2 = f"""<html><body>
{card("Book Three", "£7", "One", "three/index.html")}
</body></html>"""

DETAIL = """<html><body>
<ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="/b">Books</a></li><li><a href="/t">Travel</a></li><li>Book One</li></ul>
<div id="product_description"><h2>Product Description</h2></div><p>A fine book.</p>
<table class="table"><tr><th>UPC</th><td>abc123</td></tr>
<tr><th>Availability</th><td>In stock (19 available)</td></tr></table>
</body></html>"""


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status
        self.encoding, self.apparent_encoding = "utf-8", "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    """依網址回傳預先準備好的內容；值為 list 時依序回傳（模擬先失敗後成功）。"""

    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if url.endswith("robots.txt"):
            return FakeResponse(self.routes.get("robots", ""), 200 if "robots" in self.routes else 404)
        value = self.routes[url]
        if isinstance(value, list):
            value = value.pop(0)
        return value if isinstance(value, FakeResponse) else FakeResponse(value)


def test_parse_price_variants():
    assert scraper.parse_price("£51.77") == 51.77
    assert scraper.parse_price("Â£1,200.00") == 1200.0
    assert scraper.parse_price("NT$1,280") == 1280.0
    with pytest.raises(ValueError):
        scraper.parse_price("免費")


def test_parse_list_page_resolves_urls_and_next():
    books, next_url = scraper.parse_list_page(PAGE1, BASE)
    assert [b.title for b in books] == ["Book One", "Book Two"]  # 用 title 屬性，不是被截斷的文字
    assert books[0].url == "https://example.test/catalogue/one/index.html"
    assert (books[0].rating, books[1].rating) == (3, 5)
    assert (books[0].in_stock, books[1].in_stock) == (True, False)
    assert next_url == "https://example.test/catalogue/page-2.html"
    assert scraper.parse_list_page(PAGE2, BASE)[1] is None


def test_parse_detail_page():
    assert scraper.parse_detail_page(DETAIL) == {
        "upc": "abc123", "stock_count": 19, "description": "A fine book.", "category": "Travel",
    }


def test_crawl_follows_pagination_and_details():
    page2 = "https://example.test/catalogue/page-2.html"
    routes = {BASE: PAGE1, page2: PAGE2}
    for href in ["catalogue/one/index.html", "catalogue/two/index.html", "catalogue/three/index.html"]:
        routes[BASE + href] = DETAIL
    s = scraper.Scraper(session=FakeSession(routes), delay=0)
    books = s.crawl(BASE, details=True)
    assert [b.title for b in books] == ["Book One", "Book Two", "Book Three"]
    assert all(b.upc == "abc123" and b.stock_count == 19 for b in books)


def test_max_pages_limits_crawl():
    s = scraper.Scraper(session=FakeSession({BASE: PAGE1}), delay=0)
    assert len(s.crawl(BASE, max_pages=1)) == 2


def test_retries_on_server_error(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)
    session = FakeSession({BASE: [FakeResponse(status=503), FakeResponse(status=429), PAGE2]})
    books = scraper.Scraper(session=session, delay=0).crawl(BASE)
    assert len(books) == 1
    assert session.calls.count(BASE) == 3


def test_does_not_retry_404(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda _: None)
    session = FakeSession({BASE: [FakeResponse(status=404), PAGE2]})
    with pytest.raises(requests.HTTPError):
        scraper.Scraper(session=session, delay=0).crawl(BASE)
    assert session.calls.count(BASE) == 1


def test_respects_robots_txt():
    session = FakeSession({"robots": "User-agent: *\nDisallow: /", BASE: PAGE1})
    with pytest.raises(PermissionError):
        scraper.Scraper(session=session, delay=0).crawl(BASE)
    assert BASE not in session.calls


def test_save_csv_is_excel_friendly(tmp_path):
    books, _ = scraper.parse_list_page(PAGE1, BASE)
    books = scraper.dedupe(books + books)
    out = tmp_path / "books.csv"
    scraper.save_csv(books, out, include_details=False)
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM，Excel 才會用 UTF-8 開
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert len(rows) == 2
    assert rows[0]["書名"] == "Book One" and rows[0]["價格(GBP)"] == "10.5"
    assert "UPC" not in rows[0]
