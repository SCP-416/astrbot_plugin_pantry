# -*- coding: utf-8 -*-
"""柴米油盐核心逻辑单测（v0.2）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pantry_core import (  # noqa: E402
    advance_scene,
    apply_usage,
    consume_event,
    ensure_shape,
    format_inventory,
    make_shopping_list,
    new_state,
    parse_items,
    restock,
    scene_direction,
    settle_day,
    start_scene,
    weekly_report,
)

ITEMS = parse_items("""
[
  {"name":"米","max":100,"daily":4.0,"var":0.0,"category":"主食","price":3.5},
  {"name":"鸡蛋","max":100,"daily":6.0,"var":0.0,"category":"生鲜","price":1.2},
  {"name":"盐","max":100,"daily":0.8,"var":0.0,"category":"调料","price":2.0}
]
""")
assert len(ITEMS) == 3
assert ITEMS[0]["category"] == "主食" and ITEMS[0]["price"] == 3.5

# --- 每日结算 ---
st = new_state(ITEMS)
assert st["items"] == {"米": 100.0, "鸡蛋": 100.0, "盐": 100.0}
for _ in range(30):
    settle_day(st, ITEMS, threshold=10.0)
assert "米" in st["pending"] and "鸡蛋" in st["pending"]
assert "盐" not in st["pending"]
assert st["items"]["盐"] == 76.0

# --- 购物清单 ---
lst = make_shopping_list(st, ITEMS)
assert len(lst) == 2
assert all(x["qty"] >= 1 and x["price"] >= 0 for x in lst)
assert st["scene"]["list"] == lst

# --- 场景推进 ---
start_scene(st, "采购")
assert st["scene"]["active"] == "采购"
moved, node = advance_scene(st, "走 出门")
assert moved and node == "出门"
moved, node = advance_scene(st, "到了 进超市")
assert moved and node == "到店"
moved, node = advance_scene(st, "挑 这个")
assert moved and node == "挑东西"
moved, node = advance_scene(st, "结账")
assert moved and node == "结账"
assert "拎回家" in scene_direction(st)
for _ in range(5):
    advance_scene(st, "拎回家")
assert st["scene"]["step"] == 5

# --- 补货 ---
done = restock(st, ITEMS)
assert set(done) == {"米", "鸡蛋"}
assert st["pending"] == []
assert st["items"]["米"] == 100.0
assert st["items"]["盐"] == 76.0
assert st["scene"]["active"] == ""
assert len(st["purchases"]) == 1 and st["purchases"][0]["cost"] > 0

# --- 消耗事件 ---
consume_event(st, "做了番茄炒蛋", ["鸡蛋", "食用油"])
apply_usage(st, {"鸡蛋": 7, "食用油": 5})
assert st["events"][-1]["text"] == "做了番茄炒蛋"
assert st["items"]["鸡蛋"] == 93.0
assert st["items"].get("食用油", 100.0) <= 100.0

# --- 周报 ---
report = weekly_report(st, ITEMS)
assert "柴米油盐" in report and "采购" in report and "番茄炒蛋" in report

# --- 状态升级（老版本） ---
old = {"date": "2026-11-01", "items": {"米": 50}, "pending": [], "last_propose": 0}
up = ensure_shape(old, ITEMS)
assert "events" in up and "scene" in up and "purchases" in up
assert up["items"]["鸡蛋"] == 100.0

# --- 分类展示 ---
inv = format_inventory(st, ITEMS)
assert "主食" in inv and "调料" in inv and "米 100%" in inv

print("ALL TESTS PASSED")
