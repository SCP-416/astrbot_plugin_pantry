# -*- coding: utf-8 -*-
"""柴米油盐核心逻辑单测：模拟 60 天消耗 + 见底 + 补货闭环。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pantry_core import parse_items, new_state, settle_day, restock, format_inventory  # noqa: E402

ITEMS = parse_items("""
[
  {"name": "米", "max": 100, "daily": 4.0, "var": 0.0},
  {"name": "鸡蛋", "max": 100, "daily": 6.0, "var": 0.0},
  {"name": "盐", "max": 100, "daily": 0.8, "var": 0.0}
]
""")
assert len(ITEMS) == 3, "parse_items failed"

st = new_state(ITEMS)
assert st["items"] == {"米": 100.0, "鸡蛋": 100.0, "盐": 100.0}

# 模拟 30 天（var=0，确定性）
seen_pending = []
for _ in range(30):
    fresh = settle_day(st, ITEMS, threshold=10.0)
    seen_pending += fresh

# 米 30 天后 = 100 - 4*30 = -20 → clamp 0（约第 23 天 <= 10 触发）
# 鸡蛋 30 天后 = 100 - 6*30 < 0（约第 15 天触发）
# 盐 30 天后 = 100 - 24 = 76（不触发）
assert "米" in st["pending"], "米应该见底"
assert "鸡蛋" in st["pending"], "鸡蛋应该见底"
assert "盐" not in st["pending"], "盐不该见底"
assert st["items"]["米"] == 0.0
assert st["items"]["鸡蛋"] == 0.0
assert st["items"]["盐"] == 76.0

# 补货闭环
done = restock(st, ITEMS)
assert set(done) == {"米", "鸡蛋"}, "补货名单不对"
assert st["pending"] == []
assert st["items"]["米"] == 100.0
assert st["items"]["鸡蛋"] == 100.0
assert st["items"]["盐"] == 76.0

# 库存文本
inv = format_inventory(st, ITEMS)
assert "米 100%" in inv and "盐 76%" in inv

print("ALL TESTS PASSED")
