# -*- coding: utf-8 -*-
"""柴米油盐（astrbot_plugin_pantry）v0.2

家里生活物品库存 + 采购过家家剧情引擎。

- 每日消耗结算（带波动、可补算错过的天数）
- 消耗事件化：他随口一句「做了番茄炒蛋」就扣对应食材
- 见底触发：LLM 按人设写邀约 + 自动列购物清单 + 采购场景分步推进
- 分类/价格/保质期/预算 + 周报
- WebUI 面板：库存仪表盘，直接改数量

作者：SCP-416 · MIT
"""
import asyncio
import json
import os
import random
import time
from datetime import datetime

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.event.filter import EventMessageType
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, StarTools, register
from quart import Response, request

from .pantry_core import (
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

_CMD_WORDS = ("家里状态", "柴米油盐", "看看库存", "家里还有啥", "家里缺啥", "家里缺什么")
_LIST_WORDS = ("购物清单", "采购清单", "买什么", "要买啥")
_REPORT_WORDS = ("周报", "这周花了", "一周消费", "最近一周")
_FOOD_WORDS = ("做饭", "炒菜", "炒了", "煮了", "做了", "炖了", "蒸了", "烤了", "吃火锅", "煮面", "炒饭")
# 做菜 -> 对应食材消耗（百分比）
_FOOD_USAGE = {
    "鸡蛋": 7, "食用油": 5, "盐": 2, "酱油": 3, "醋": 2,
    "米": 6, "番茄": 8, "青菜": 8, "葱": 5,
}
_PROPOSE_TEMPLATES = [
    "家里快见底了 陪我去趟超市呗 要买{items}",
    "走 去超市囤点货 {items}都快没了",
    "看看柜子 {items}见底了 陪我补点货去",
]
_PAGE_PREFIX = "/astrbot_plugin_pantry/page"

_DEFAULT_ITEMS = [
    {"name": "米", "max": 100, "daily": 4.0, "var": 0.3, "category": "主食", "price": 3.5},
    {"name": "鸡蛋", "max": 100, "daily": 6.0, "var": 0.3, "category": "生鲜", "price": 1.2},
    {"name": "食用油", "max": 100, "daily": 2.0, "var": 0.3, "category": "调料", "price": 12.0},
    {"name": "盐", "max": 100, "daily": 0.8, "var": 0.3, "category": "调料", "price": 2.0},
    {"name": "酱油", "max": 100, "daily": 1.5, "var": 0.3, "category": "调料", "price": 8.0},
    {"name": "醋", "max": 100, "daily": 1.0, "var": 0.3, "category": "调料", "price": 6.0},
    {"name": "纸巾", "max": 100, "daily": 5.0, "var": 0.3, "category": "日用", "price": 4.0},
    {"name": "洗衣液", "max": 100, "daily": 2.5, "var": 0.3, "category": "日用", "price": 15.0},
    {"name": "牙膏", "max": 100, "daily": 1.5, "var": 0.3, "category": "日用", "price": 9.0},
    {"name": "洗发水", "max": 100, "daily": 1.2, "var": 0.3, "category": "日用", "price": 20.0},
]


@register("astrbot_plugin_pantry", "SCP-416", "柴米油盐", "0.3.0")
class PantryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)
        self._cfg = config or {}
        self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_pantry"))
        os.makedirs(self.data_dir, exist_ok=True)
        self._state_path = os.path.join(self.data_dir, "pantry_state.json")
        self._items_path = os.path.join(self.data_dir, "pantry_items.json")

    # ---------- 配置 / 状态 ----------
    def _items(self):
        """自定义物品（面板里增删改的）优先，其次配置里的 items_json，最后默认清单。"""
        try:
            if os.path.exists(self._items_path):
                with open(self._items_path, encoding="utf-8") as f:
                    custom = json.load(f)
                if isinstance(custom, list):
                    parsed = parse_items(custom)
                    if parsed:
                        return parsed
        except Exception:
            pass
        return parse_items(self._cfg.get("items_json", "")) or list(_DEFAULT_ITEMS)

    def _save_items(self, items):
        try:
            tmp = self._items_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._items_path)
        except Exception as e:
            logger.warning("[柴米油盐] 自定义物品保存失败: %s", e)

    def _threshold(self):
        try:
            return float(self._cfg.get("low_threshold", 10) or 10)
        except (TypeError, ValueError):
            return 10.0

    def _load_state(self):
        try:
            with open(self._state_path, encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st.get("items"), dict):
                raise ValueError("bad state")
            return ensure_shape(st, self._items())
        except Exception:
            return new_state(self._items())

    def _save_state(self, st):
        try:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._state_path)
        except Exception as e:
            logger.warning("[柴米油盐] 状态保存失败: %s", e)

    def _sync(self, st):
        """补结算到今天；返回新见底的物品。"""
        items = self._items()
        today = datetime.now().strftime("%Y-%m-%d")
        if st.get("date") == today:
            return []
        fresh = []
        try:
            last = st.get("date") or ""
            missed = (datetime.now().date() - datetime.strptime(last, "%Y-%m-%d").date()).days if last else 1
            missed = max(0, min(int(missed), 90))
        except Exception:
            missed = 1
        for _ in range(missed):
            fresh = settle_day(st, items, self._threshold())
        st["date"] = today
        if fresh:
            consume_event(st, "日常消耗（%d 天）" % missed, fresh)
        self._save_state(st)
        return fresh

    # ---------- 人格注入 ----------
    @filter.on_llm_request()
    async def inject_pantry(self, event: AstrMessageEvent, req):
        try:
            st = self._load_state()
            self._sync(st)
            pending = [str(x) for x in (st.get("pending") or [])]
            parts = []
            if pending:
                parts.append(
                    "\n\n【家里·柴米油盐】家里这些快见底了："
                    + "、".join(pending)
                    + "。合适的时候（别生硬、别每轮都提）自然说一句「陪我去趟超市/买菜」，"
                    "发起采购；他应了就按场景节点往下演。\n"
                )
            sd = scene_direction(st)
            if sd:
                parts.append(sd)
            events = [e for e in (st.get("events") or [])[-2:]]
            if events:
                parts.append(
                    "\n\n【最近家里的事】"
                    + "；".join(e.get("text", "") for e in events if e.get("text"))
                    + "。这些是真发生过的，自然带出来，别报账。\n"
                )
            if parts:
                req.system_prompt = (req.system_prompt or "") + "".join(parts)
        except Exception as e:
            logger.warning("[柴米油盐] 注入失败: %s", e)

    # ---------- 消息处理 ----------
    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            text = event.message_str or ""
            st = self._load_state()
            self._sync(st)
            items = self._items()

            # 查询命令
            if any(w in text for w in _CMD_WORDS):
                await self._send(event, format_inventory(st, items, self._threshold()))
                return
            if any(w in text for w in _LIST_WORDS):
                lst = st["scene"].get("list") or make_shopping_list(st, items, self._threshold())
                self._save_state(st)
                lines = ["【购物清单】"] + [
                    "· %s ×%d%s" % (x["name"], x["qty"], ("（约 %s 元）" % (x["qty"] * x["price"])) if x.get("price") else "")
                    for x in lst
                ] or ["【购物清单】家里暂时不缺什么"]
                await self._send(event, "\n".join(lines))
                return
            if any(w in text for w in _REPORT_WORDS):
                await self._send(event, weekly_report(st, items))
                return

            # 消耗事件：他说做了什么菜
            if any(w in text for w in _FOOD_WORDS):
                usage = {}
                for name, amt in _FOOD_USAGE.items():
                    if name in text and name in st["items"]:
                        usage[name] = amt
                if not usage:
                    usage = {
                        k: v for k, v in (("鸡蛋", 6), ("食用油", 4), ("盐", 2))
                        if k in st["items"]
                    }
                apply_usage(st, usage)
                consume_event(st, text, list(usage))
                self._save_state(st)
                logger.info("[柴米油盐] 消耗事件：%s", text[:30])

            # 场景推进
            moved, node = advance_scene(st, text)
            if moved:
                self._save_state(st)
                logger.info("[柴米油盐] 场景推进到：%s", node)

            # 采购完成 -> 补货
            done_words = [w.strip() for w in str(self._cfg.get("done_words", "") or "").replace("，", ",").split(",") if w.strip()]
            if done_words and any(w in text for w in done_words) and st.get("pending"):
                names = restock(st, items)
                self._save_state(st)
                if names:
                    await self._send(event, "（把买回来的东西归置进柜子）这下不缺了")
                    logger.info("[柴米油盐] 采购完成，补货：%s", names)
                return

            buy_words = [w.strip() for w in str(self._cfg.get("procurement_words", "") or "").replace("，", ",").split(",") if w.strip()]
            if buy_words and any(w in text for w in buy_words) and st.get("pending"):
                st["last_propose"] = time.time()
                self._save_state(st)
        except Exception as e:
            logger.warning("[柴米油盐] 消息处理失败: %s", e)

    async def _send(self, event, text):
        event.stop_event()
        await self.context.send_message(event.unified_msg_origin, MessageChain([Plain(text)]))

    # ---------- LLM 邀约 ----------
    async def _llm_proposal(self, st, umo):
        """按人设写一句采购邀约；失败退回模板。"""
        if not self._cfg.get("llm_propose", True):
            return ""
        pending = [str(x) for x in (st.get("pending") or [])[:4]]
        if not pending:
            return ""
        try:
            provider = self.context.get_using_provider(umo)
            if provider is None:
                return ""
            prompt = (
                "【现在时间 %s】你想主动约他一起采购家里缺的东西：%s。\n"
                "写一句要发出去的聊天消息：像亲近的人随口张罗，短、口语、带一点你自己的小脾气/撒娇，"
                "空格分条，不超过三个气泡的量，不用句号，不要提「系统/库存/百分比」这些词。"
                "只输出这句话本身。" % (datetime.now().strftime("%H:%M"), "、".join(pending))
            )
            resp = await provider.text_chat(prompt=prompt)
            text = (getattr(resp, "completion_text", "") or "").strip().strip("\"'“”")
            return text if 0 < len(text) <= 120 else ""
        except Exception as e:
            logger.warning("[柴米油盐] LLM 邀约失败，用模板: %s", e)
            return ""

    # ---------- 主动邀约 ----------
    async def initialize(self):
        self._propose_task = asyncio.create_task(self._propose_loop())
        try:
            self.context.register_web_api(
                _PAGE_PREFIX + "/state", self._web_state, ["GET"], "柴米油盐库存状态"
            )
            self.context.register_web_api(
                _PAGE_PREFIX + "/update", self._web_update, ["POST"], "柴米油盐库存编辑"
            )
            self.context.register_web_api(
                _PAGE_PREFIX + "/index", self._web_index, ["GET"], "柴米油盐面板"
            )
            self.context.register_web_api(
                _PAGE_PREFIX + "/items", self._web_items, ["GET"], "柴米油盐自定义物品"
            )
            self.context.register_web_api(
                _PAGE_PREFIX + "/item", self._web_item, ["POST"], "柴米油盐增删改物品"
            )
            self.context.register_web_api(
                _PAGE_PREFIX + "/reset", self._web_reset, ["POST"], "柴米油盐重置库存"
            )
        except Exception as e:
            logger.warning("[柴米油盐] WebUI 注册跳过: %s", e)

    async def _web_state(self):
        st = self._load_state()
        self._sync(st)
        return {
            "items": st["items"], "pending": st["pending"],
            "scene": st["scene"], "events": st["events"][-10:],
            "purchases": st["purchases"][-10:], "config": [
                {"name": x["name"], "max": x["max"], "daily": x["daily"],
                 "category": x.get("category"), "price": x.get("price")}
                for x in self._items()
            ],
        }

    async def _web_update(self):
        try:
            data = await request.get_json()
            name = str(data.get("name") or "")
            qty = float(data.get("qty"))
            st = self._load_state()
            if name in st["items"]:
                st["items"][name] = max(0.0, qty)
                if name in st["pending"] and qty > self._threshold():
                    st["pending"].remove(name)
                self._save_state(st)
                return {"ok": True, "name": name, "qty": st["items"][name]}
            return {"ok": False, "error": "unknown item"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _web_items(self):
        return {"items": self._items(), "custom": os.path.exists(self._items_path)}

    async def _web_item(self):
        """增 / 改 / 删消耗品。POST {action: add|update|delete, item: {...}, old_name: ...}"""
        try:
            data = await request.get_json()
            action = str(data.get("action") or "add")
            items = list(self._items())  # 已经是 dict 列表
            old_name = str(data.get("old_name") or "")
            if action == "delete":
                items = [x for x in items if x["name"] != old_name]
            else:
                raw = data.get("item") or {}
                parsed = parse_items([raw])
                if not parsed:
                    return {"ok": False, "error": "字段不合法（需要 name / daily）"}
                new = parsed[0]
                if action == "update" and old_name:
                    items = [new if x["name"] == old_name else x for x in items]
                    if new["name"] != old_name:
                        # 改名：把库存值迁过去
                        st = self._load_state()
                        if old_name in st["items"]:
                            st["items"][new["name"]] = st["items"].pop(old_name)
                            st["pending"] = [new["name"] if x == old_name else x for x in st["pending"]]
                            self._save_state(st)
                else:
                    if any(x["name"] == new["name"] for x in items):
                        return {"ok": False, "error": "物品名已存在"}
                    items.append(new)
                    st = self._load_state()
                    st["items"][new["name"]] = float(new["max"])
                    self._save_state(st)
            self._save_items(items)
            return {"ok": True, "items": items}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _web_reset(self):
        try:
            st = new_state(self._items())
            self._save_state(st)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _web_index(self):
        html = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>柴米油盐 · 家里状态</title>
<style>
body{font-family:system-ui;background:#f6f3ee;color:#2b2b2b;margin:0;padding:24px}
h1{font-size:22px} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.card{background:#fff;border-radius:12px;padding:14px;box-shadow:0 2px 8px #0001}
.bar{height:8px;background:#eee;border-radius:4px;overflow:hidden;margin:8px 0}
.bar i{display:block;height:100%;background:#6ba}
.low i{background:#e66} input{width:70px} button{padding:4px 10px;border:0;border-radius:6px;background:#6ba;color:#fff}
pre{background:#fff;padding:12px;border-radius:10px}
</style></head><body>
<h1>🏠 柴米油盐 · 家里状态</h1>
<div id="grid" class="grid"></div>
<h2>购物清单 / 场景</h2><pre id="scene"></pre>
<h2>最近记录</h2><pre id="events"></pre>
<script>
async function load(){
 const s=await (await fetch('/astrbot_plugin_pantry/page/state')).json();
 const cfg=s.config||{};
 document.getElementById('grid').innerHTML=(s.config||[]).map(x=>{
  const q=s.items[x.name]??x.max, p=Math.round(q/x.max*100), low=p<=10;
  return `<div class="card${low?' low':''}"><b>${x.name}</b><span style="float:right;color:${low?'#e66':'#999'}">${p}%</span>
  <div class="bar"><i style="width:${p}%"></i></div>
  <small>${x.category||''} · 日耗 ${x.daily}%</small><br>
  <input id="i-${x.name}" value="${q}" type="number" min="0" step="1"> <button onclick="set('${x.name}')">改</button></div>`;
 }).join('');
 document.getElementById('scene').textContent=JSON.stringify(s.scene,null,2);
 document.getElementById('events').textContent=(s.events||[]).map(e=>e.text).join('\n')||'（暂无）';
}
async function set(name){
 const qty=document.getElementById('i-'+name).value;
 await fetch('/astrbot_plugin_pantry/page/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,qty:Number(qty)})});
 load();
}
load();setInterval(load,30000);
</script></body></html>"""
        return Response(html, content_type="text/html; charset=utf-8")

    async def _propose_loop(self):
        while True:
            try:
                await asyncio.sleep(600)
                if not self._cfg.get("auto_propose", True):
                    continue
                target = str(self._cfg.get("target_umo", "") or "").strip()
                if not target:
                    continue
                st = self._load_state()
                self._sync(st)
                pending = [str(x) for x in (st.get("pending") or [])]
                if not pending:
                    continue
                cooldown = max(0.5, float(self._cfg.get("propose_cooldown_hours", 6) or 6)) * 3600
                if time.time() - float(st.get("last_propose") or 0) < cooldown:
                    continue
                items = self._items()
                make_shopping_list(st, items, self._threshold())
                start_scene(st, "采购")
                msg = await self._llm_proposal(st, target) or random.choice(_PROPOSE_TEMPLATES).format(items="、".join(pending[:3]))
                await self.context.send_message(target, MessageChain([Plain(msg)]))
                st["last_propose"] = time.time()
                self._save_state(st)
                logger.info("[柴米油盐] 采购提案已发：%s", msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[柴米油盐] 提案循环异常: %s", e)
