# -*- coding: utf-8 -*-
"""柴米油盐 · 纯逻辑核心（不依赖 AstrBot，可单测）。

状态结构（pantry_state.json）:
{
  "date": "2026-11-23",            # 上次结算日
  "items": {"米": 62.5},           # 剩余量（0~满量的数值，不是百分比）
  "pending": ["米"],               # 见底的物品
  "last_propose": 0.0,             # 上次主动提案时间戳（秒）
}

物品配置项:
  name  = 物品名
  max   = 满量数值（随便取，建议 100）
  daily = 每天消耗（按满量的百分比计，例如 daily=4 表示每天掉 4%）
  var   = 随机波动幅度（0~1，实际消耗 = daily * (1 ± var)）
"""
import json
import random


def parse_items(items_json):
    """配置文本 -> 物品列表；非法配置返回 []。"""
    if isinstance(items_json, str):
        try:
            items_json = json.loads(items_json)
        except Exception:
            return []
    if not isinstance(items_json, list):
        return []
    out = []
    for it in items_json:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        try:
            maxv = float(it.get("max", 100))
            daily = float(it.get("daily", 0.0))
            var = float(it.get("var", 0.3))
        except (TypeError, ValueError):
            continue
        if maxv <= 0 or daily <= 0:
            continue
        out.append({
            "name": name,
            "max": maxv,
            "daily": daily,
            "var": max(0.0, min(var, 1.0)),
        })
    return out


def new_state(items):
    """按物品配置初始化一份全新状态。"""
    return {
        "date": "",
        "items": {it["name"]: float(it["max"]) for it in items},
        "pending": [],
        "last_propose": 0.0,
    }


def settle_day(state, items, threshold=10.0):
    """结算一天消耗；返回本日新见底的物品名列表。"""
    fresh = []
    for it in items:
        name = it["name"]
        if name not in state["items"]:
            state["items"][name] = float(it["max"])
        use = it["daily"] * (1 + random.uniform(-it["var"], it["var"]))
        state["items"][name] = max(0.0, round(state["items"][name] - use, 2))
        if state["items"][name] <= threshold and name not in state["pending"]:
            state["pending"].append(name)
            fresh.append(name)
    return fresh


def restock(state, items):
    """采购完成：pending 物品回满并清空；返回回满的名单。"""
    done = []
    for name in list(state.get("pending") or []):
        for it in items:
            if it["name"] == name:
                state["items"][name] = float(it["max"])
                done.append(name)
                break
        if name in state["pending"]:
            state["pending"].remove(name)
    return done


def format_inventory(state, items, threshold=10.0):
    """家里状态 -> 给用户看的清单文本。"""
    lines = []
    for it in items:
        name = it["name"]
        q = float(state["items"].get(name, it["max"]))
        pct = q / it["max"] * 100.0
        flag = " ⚠️快见底" if q <= threshold else ""
        lines.append("%s %.0f%%%s" % (name, pct, flag))
    tail = "\n\n快见底了，该去采购了。" if state.get("pending") else ""
    return "【家里·柴米油盐】\n" + "\n".join(lines) + tail
