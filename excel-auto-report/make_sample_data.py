"""產生 3 間門市的「髒」銷售資料，模擬客戶每月寄來、格式各不相同的 Excel。

每間門市的欄位名稱、日期格式、數量寫法都不一樣，還混了重複列、空白單價、
全形字元，正好是 report.py 要處理的真實情境。

用法：python make_sample_data.py [輸出資料夾]
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PRODUCTS = [
    ("美式咖啡", "飲品", 60),
    ("拿鐵", "飲品", 80),
    ("燕麥拿鐵", "飲品", 95),
    ("伯爵紅茶", "飲品", 55),
    ("可頌", "烘焙", 45),
    ("肉桂捲", "烘焙", 65),
    ("巴斯克乳酪蛋糕", "甜點", 120),
    ("提拉米蘇", "甜點", 110),
    ("咖啡豆(半磅)", "零售", 380),
    ("濾掛包(10入)", "零售", 250),
]

START = date(2026, 7, 1)
END = date(2026, 9, 30)


def _orders(rng: random.Random, busy: float, prefix: str):
    """逐日產生訂單：(單號, 日期, 商品, 類別, 數量, 單價)。"""
    day = START
    while day <= END:
        weekend = day.weekday() >= 5
        for n in range(1, rng.randint(8, 18) + (8 if weekend else 0) + 1):
            name, cat, price = rng.choices(PRODUCTS, weights=[9, 10, 5, 4, 8, 5, 3, 3, 1, 2])[0]
            qty = rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
            if rng.random() < busy:
                qty += 1
            yield f"{prefix}{day:%Y%m%d}{n:03d}", day, name, cat, qty, price
        day += timedelta(days=1)


def make_taipei(rng):
    """欄位標準、日期是真正的日期格式，但有幾筆重複輸入。"""
    rows = [
        {"單號": o, "日期": d, "商品名稱": n, "類別": c, "數量": q, "單價": p}
        for o, d, n, c, q, p in _orders(rng, busy=0.25, prefix="TP")
    ]
    rows += rng.sample(rows, 6)  # 店員重複貼上
    return pd.DataFrame(rows)


def make_taichung(rng):
    """欄位名稱不同、日期是文字「2026/07/03」、數量寫成「3個」。"""
    rows = []
    for o, d, n, c, q, p in _orders(rng, busy=0.1, prefix="TC"):
        qty = f"{q}個" if rng.random() < 0.3 else str(q)
        rows.append({"訂單編號": o, "交易日期": d.strftime("%Y/%m/%d"), "品名": n, "分類": c, "數量": qty, "單價": p})
    rows[rng.randrange(len(rows))]["數量"] = "N/A"  # 無法辨識的數量
    rows[rng.randrange(len(rows))]["交易日期"] = "2026/13/01"  # 打錯的日期
    return pd.DataFrame(rows)


def make_kaohsiung(rng):
    """商品名稱有多餘空白與全形括號、部分單價空白。"""
    rows = []
    for o, d, n, c, q, p in _orders(rng, busy=0.15, prefix="KH"):
        name = n.replace("(", "（").replace(")", "）") if rng.random() < 0.5 else n
        if rng.random() < 0.15:
            name = f" {name} "
        price = None if rng.random() < 0.03 else p
        rows.append({"單號": o, "日期": d.isoformat(), "商品": name, "類別": c, "銷售數量": q, "售價": price})
    return pd.DataFrame(rows)


def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    for store, maker in [("台北店", make_taipei), ("台中店", make_taichung), ("高雄店", make_kaohsiung)]:
        path = out_dir / f"{store}_2026Q3.xlsx"
        maker(rng).to_excel(path, index=False)
        print(f"已產生 {path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data")
