# -*- coding: utf-8 -*-
"""柴米油盐 · 纯逻辑核心（不依赖 AstrBot，可单测）。

v0.2 数据层：物品分类/价格/保质期 + 消耗事件 + 采购场景分步 + 购物清单 + 周报。

状态结构（pantry_state.json）:
{
  "date": "2026-11-24",              # 上次每日结算日
  "items": {"米": 62.5},             # 剩余量（0~max）
  "pending": ["米"],                 # 见底物品
  "last_propose": 0.0,               # 上次主动邀约时间戳
  "events": [                        # 最近消耗事件
    {"ts":..., "text":"做了番茄炒蛋", "used":["鸡蛋","食用油"]}
  ],
  "scene": {                         # 进行中的采购场景
    "active": "", "step": 0, "started": 0.0,
    "list": [{"name":"米","qty":2}]  # 购物清单
  },
  "purchases": [{"ts":..., "items":{...}, "cost":0.0}]  # 采购历史
}

物品配置:
  name / max / daily / var / category / price / expire_days
  daily  = 每天消耗（占满量百分比）
  var    = 波动 0~1
  price  = 单价（用于预算与周报）
  expire_days = 保质期天数（临期提醒用，可选）
"""
import json
import random
from datetime import datetime

SCENE_STEPS = ["出门", "到店", "挑东西", "结账", "拎回家"]


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
        try:
            price = max(0.0, float(it.get("price", 0.0)))
            expire_days = max(0.0, float(it.get("expire_days", 0.0)))
        except (TypeError, ValueError):
            price, expire_days = 0.0, 0.0
        out.append({
            "name": name, "max": maxv, "daily": daily,
            "var": max(0.0, min(var, 1.0)),
            "category": str(it.get("category") or "其他").strip() or "其他",
            "price": price, "expire_days": expire_days,
        })
    return out


def new_state(items):
    """按物品配置初始化一份全新状态。"""
    return {
        "date": "",
        "items": {it["name"]: float(it["max"]) for it in items},
        "pending": [],
        "last_propose": 0.0,
        "events": [],
        "scene": {"active": "", "step": 0, "started": 0.0, "list": []},
        "purchases": [],
    }


def ensure_shape(st, items):
    """老版本状态升级：补齐缺失字段。"""
    st.setdefault("date", "")
    st.setdefault("items", {})
    st.setdefault("pending", [])
    st.setdefault("last_propose", 0.0)
    st.setdefault("events", [])
    st.setdefault("scene", {"active": "", "step": 0, "started": 0.0, "list": []})
    st.setdefault("purchases", [])
    for it in items:
        st["items"].setdefault(it["name"], float(it["max"]))
    sc = st["scene"]
    sc.setdefault("active", "")
    sc.setdefault("step", 0)
    sc.setdefault("started", 0.0)
    sc.setdefault("list", [])
    return st


def settle_day(st, items, threshold=10.0):
    """结算一天消耗；返回本日新见底的物品名列表。"""
    fresh = []
    for it in items:
        name = it["name"]
        use = it["daily"] * (1 + random.uniform(-it["var"], it["var"]))
        st["items"][name] = max(0.0, round(st["items"][name] - use, 2))
        if st["items"][name] <= threshold and name not in st["pending"]:
            st["pending"].append(name)
            fresh.append(name)
    return fresh


def consume_event(st, text, used, max_events=30):
    """记一笔消耗事件（做了什么菜 -> 消耗哪些食材）。"""
    st["events"].append({
        "ts": datetime.now().timestamp(),
        "text": str(text)[:80],
        "used": [str(x) for x in used],
    })
    del st["events"][:-max_events]


def apply_usage(st, usage):
    """额外扣减：usage = {物品名: 消耗百分比}。"""
    for name, amt in (usage or {}).items():
        if name in st["items"]:
            try:
                st["items"][name] = max(0.0, round(st["items"][name] - float(amt), 2))
            except (TypeError, ValueError):
                pass


def make_shopping_list(st, items, threshold=10.0):
    """按见底物品生成购物清单（数量 = 缺多少，至少 1 件）。"""
    by_name = {it["name"]: it for it in items}
    out = []
    for name in st["pending"]:
        it = by_name.get(name)
        if not it:
            continue
        need = max(0.0, float(it["max"]) - float(st["items"].get(name, 0.0)))
        qty = max(1, round(need / max(1.0, float(it["max"])) * 3))
        out.append({
            "name": name,
            "qty": qty,
            "price": float(it.get("price") or 0.0),
            "category": it.get("category") or "其他",
        })
    st["scene"]["list"] = out
    return out


def start_scene(st, act="采购"):
    """开一场采购场景。"""
    st["scene"] = {
        "active": act, "step": 0, "started": datetime.now().timestamp(),
        "list": st["scene"].get("list") or [],
    }


def advance_scene(st, hint=""):
    """按用户话语推进场景；返回 (是否推进, 当前节点名)。"""
    sc = st["scene"]
    if not sc.get("active"):
        return False, ""
    text = str(hint or "")
    keywords = [
        ("出门", ("走", "出门", "出发", "换个鞋", "拿袋子")),
        ("到店", ("到了", "进超市", "进店", "门口")),
        ("挑东西", ("挑", "看看", "拿", "这个", "那个", "比较")),
        ("结账", ("结账", "付钱", "扫码", "多少钱")),
        ("拎回家", ("拎", "回家", "到家", "回来了")),
    ]
    step = int(sc.get("step") or 0)
    # 命中当前或之后的节点才推进，避免一句话连跳
    for target in range(step, len(SCENE_STEPS)):
        words = keywords[target][1]
        if any(w in text for w in words):
            sc["step"] = target + 1
            return True, SCENE_STEPS[min(target, len(SCENE_STEPS) - 1)]
    return False, SCENE_STEPS[min(step, len(SCENE_STEPS) - 1)]


def scene_direction(st):
    """当前场景的提示词片段（注入人格）。"""
    sc = st.get("scene") or {}
    if not sc.get("active"):
        return ""
    step = min(int(sc.get("step") or 0), len(SCENE_STEPS) - 1)
    name = SCENE_STEPS[step]
    directions = {
        "出门": "你们正准备出门：想想拿袋子、换鞋、路上说什么，推进到超市门口。",
        "到店": "你们刚到店里：写看到的货架/灯光/人声，推着车往需要的区域走。",
        "挑东西": "正在挑东西：拿起来看看、比价、放回去又拿起来，按购物清单逐样过。",
        "结账": "在结账：排队、扫码、报总价、付钱，可以吐槽花费。",
        "拎回家": "拎着东西回家：写手上沉甸甸的感觉、回家归置进柜子的动作。",
    }
    shopping = "、".join("%s×%d" % (x["name"], x["qty"]) for x in sc.get("list") or [])
    return (
        "\n\n【采购场景·进行中】当前节点：%s。%s"
        "购物清单：%s。每轮只走这一个节点，加新细节，别把场景一次走完、别报节点名。\n"
    ) % (name, directions[name], shopping or "（还没列）")


def restock(st, items, cost=0.0):
    """采购完成：pending 回满，记一笔采购历史。"""
    done = []
    by_name = {it["name"]: it for it in items}
    total = 0.0
    for x in (st["scene"].get("list") or []):
        it = by_name.get(x.get("name"))
        if it:
            total += float(x.get("qty") or 0) * float(it.get("price") or 0.0)
    for name in list(st.get("pending") or []):
        if name in by_name:
            st["items"][name] = float(by_name[name]["max"])
            done.append(name)
    st["pending"] = []
    st["purchases"].append({
        "ts": datetime.now().timestamp(), "items": done,
        "cost": round(cost or total, 2),
    })
    del st["purchases"][:-30]
    st["scene"] = {"active": "", "step": 0, "started": 0.0, "list": []}
    return done


def weekly_report(st, items):
    """近 7 天采购与消耗小结。"""
    now = datetime.now().timestamp()
    purchases = [p for p in st.get("purchases") or [] if now - p.get("ts", 0) < 7 * 86400]
    events = [e for e in st.get("events") or [] if now - e.get("ts", 0) < 7 * 86400]
    total = round(sum(float(p.get("cost") or 0) for p in purchases), 2)
    lines = ["【最近一周·柴米油盐】", "采购 %d 次，花费 %s 元" % (len(purchases), total)]
    for p in purchases[-5:]:
        day = datetime.fromtimestamp(p["ts"]).strftime("%m-%d")
        lines.append("· %s 买了 %s%s" % (
            day, "、".join(p.get("items") or []),
            ("（%s 元）" % p["cost"]) if p.get("cost") else "",
        ))
    for e in events[-5:]:
        day = datetime.fromtimestamp(e["ts"]).strftime("%m-%d")
        lines.append("· %s %s" % (day, e.get("text", "")))
    low = [x for x in st.get("pending") or []]
    if low:
        lines.append("还缺：%s" % "、".join(low))
    return "\n".join(lines)


def format_inventory(st, items, threshold=10.0):
    """家里状态 -> 给用户看的清单文本。"""
    lines = []
    cats = {}
    for it in items:
        cats.setdefault(it.get("category") or "其他", []).append(it)
    for cat, group in cats.items():
        lines.append("— %s —" % cat)
        for it in group:
            name = it["name"]
            q = float(st["items"].get(name, it["max"]))
            pct = q / it["max"] * 100.0
            flag = " ⚠️快见底" if q <= threshold else ""
            lines.append("%s %.0f%%%s" % (name, pct, flag))
    tail = "\n\n快见底了，该去采购了。" if st.get("pending") else ""
    return "【家里·柴米油盐】\n" + "\n".join(lines) + tail
