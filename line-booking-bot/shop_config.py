"""店家設定：換成客戶的店時，通常只需要改這個檔案。"""
from datetime import time

SHOP_NAME = "小山髮廊"

# 代號: (名稱, 所需分鐘數, 價格)
SERVICES = {
    "cut": ("剪髮", 60, 500),
    "wash": ("洗髮造型", 30, 300),
    "color": ("染髮", 120, 1800),
    "perm": ("燙髮", 150, 2500),
}

# 星期一=0 … 星期日=6；不在表內的日子公休
OPENING_HOURS = {
    1: (time(10, 0), time(20, 0)),
    2: (time(10, 0), time(20, 0)),
    3: (time(10, 0), time(20, 0)),
    4: (time(10, 0), time(21, 0)),
    5: (time(9, 0), time(19, 0)),
    6: (time(9, 0), time(18, 0)),
}

STAFF = 2  # 同一時段最多可同時服務幾位客人
SLOT_MINUTES = 30  # 可預約的起始時間間隔
DAYS_AHEAD = 7  # 開放預約未來幾天
LEAD_MINUTES = 60  # 至少要提前幾分鐘預約
MAX_ACTIVE_BOOKINGS = 3  # 每位客人最多同時持有幾筆未來的預約
