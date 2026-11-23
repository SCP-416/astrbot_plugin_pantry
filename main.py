# -*- coding: utf-8 -*-
"""柴米油盐（astrbot_plugin_pantry）

记录家里常用的生活物品，每天按消耗率扣减。
某样物品接近见底（默认 <= 10%）时：
  1) 把「家里快缺货」注入人格提示词，让她聊天时自然提出来；
  2) （可选）主动给目标会话发一条采购邀约；
他应约演采购过家家，回来交代完（「到家了/买好了」等）自动补货。

作者：SCP-416 · MIT
"""
import asyncio
import json
import os
import random
import time
from datetime import datetime

from astrbot.api import logger, StarTools
from astrbot.api.event import EventMessageType, filter, AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register

from .pantry_core import (
    format_inventory,
    new_state,
    parse_items,
    restock,
    settle_day,
)

_CMD_WORDS = ("家里状态", "柴米油盐", "看看库存", "家里还有啥", "家里缺啥", "家里缺什么")

_DEFAULT_ITEMS = [
    {"name": "米", "max": 100, "daily": 4.0, "var": 0.3},
    {"name": "鸡蛋", "max": 100, "daily": 6.0, "var": 0.3},
    {"name": "食用油", "max": 100, "daily": 2.0, "var": 0.3},
    {"name": "盐", "max": 100, "daily": 0.8, "var": 0.3},
    {"name": "酱油", "max": 100, "daily": 1.5, "var": 0.3},
    {"name": "醋", "max": 100, "daily": 1.0, "var": 0.3},
    {"name": "纸巾", "max": 100, "daily": 5.0, "var": 0.3},
    {"name": "洗衣液", "max": 100, "daily": 2.5, "var": 0.3},
    {"name": "牙膏", "max": 100, "daily": 1.5, "var": 0.3},
    {"name": "洗发水", "max": 100, "daily": 1.2, "var": 0.3},
]

_PROPOSE_TEMPLATES = [
    "家里快见底了 陪我去趟超市呗 要买{items}",
    "走 去超市囤点货 {items}都快没了",
    "看看柜子 {items}见底了 陪我补点货去",
]


@register("astrbot_plugin_pantry", "SCP-416", "柴米油盐", "0.1.0")
class PantryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)
        self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_pantry"))
        os.makedirs(self.data_dir, exist_ok=True)
        self._state_path = os.path.join(self.data_dir, "pantry_state.json")

    # ---------- 状态读写 ----------
    def _items(self):
        return parse_items(self.config.get("items_json", "")) or list(_DEFAULT_ITEMS)

    def _threshold(self):
        try:
            return float(self.config.get("low_threshold", 10) or 10)
        except (TypeError, ValueError):
            return 10.0

    def _load_state(self):
        try:
            with open(self._state_path, encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st.get("items"), dict):
                raise ValueError("bad state")
            return st
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
        """补结算到今天；返回补结算期间新见底的物品。"""
        items = self._items()
        today = datetime.now().strftime("%Y-%m-%d")
        if st.get("date") == today:
            return []
        fresh = []
        try:
            last = st.get("date") or ""
            if not last:
                missed = 1
            else:
                missed = (datetime.now().date() - datetime.strptime(last, "%Y-%m-%d").date()).days
            missed = max(0, min(int(missed), 90))
        except Exception:
            missed = 1
        for _ in range(missed):
            fresh = settle_day(st, items, self._threshold())
        st["date"] = today
        self._save_state(st)
        if missed:
            logger.info("[柴米油盐] 补结算 %d 天，见底新增 %s", missed, fresh)
        return fresh

    # ---------- 人格注入：让她心里有数 ----------
    @filter.on_llm_request()
    async def inject_pantry(self, event: AstrMessageEvent, req):
        try:
            st = self._load_state()
            self._sync(st)
            pending = [str(x) for x in (st.get("pending") or [])]
            if not pending:
                return
            block = (
                "\n\n【家里·柴米油盐】家里这些快见底了："
                + "、".join(pending)
                + "。合适的时候（别生硬、别每轮都提）自然说一句「陪我去趟超市/买菜」，"
                "发起采购过家家；他应了就演采购场景（挑东西、比价、结账、拎回家），"
                "他回来交代完（到家了/买好了）就表示家里补上了。\n"
            )
            req.system_prompt = (req.system_prompt or "") + block
        except Exception as e:
            logger.warning("[柴米油盐] 注入失败: %s", e)

    # ---------- 消息处理 ----------
    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            text = event.message_str or ""
            st = self._load_state()
            self._sync(st)

            # 查家里状态
            if any(w in text for w in _CMD_WORDS):
                inv = format_inventory(st, self._items(), self._threshold())
                event.stop_event()
                await self.context.send_message(event.unified_msg_origin, [Plain(inv)])
                return

            # 采购完成 → 补货
            done_words = [w.strip() for w in str(self.config.get("done_words", "") or "").replace("，", ",").split(",") if w.strip()]
            if done_words and any(w in text for w in done_words) and st.get("pending"):
                names = restock(st, self._items())
                self._save_state(st)
                if names:
                    event.stop_event()
                    await self.context.send_message(
                        event.unified_msg_origin,
                        [Plain("（把买回来的东西归置进柜子）这下不缺了")],
                    )
                    logger.info("[柴米油盐] 采购完成，补货：%s", names)
                return

            # 用户主动张罗采购 → 记下时间（等 done 词回补）
            buy_words = [w.strip() for w in str(self.config.get("procurement_words", "") or "").replace("，", ",").split(",") if w.strip()]
            if buy_words and any(w in text for w in buy_words) and st.get("pending"):
                st["last_propose"] = time.time()
                self._save_state(st)
        except Exception as e:
            logger.warning("[柴米油盐] 消息处理失败: %s", e)

    # ---------- 主动邀约 ----------
    async def initialize(self):
        self._propose_task = asyncio.create_task(self._propose_loop())

    async def _propose_loop(self):
        while True:
            try:
                await asyncio.sleep(600)
                if not self.config.get("auto_propose", True):
                    continue
                target = str(self.config.get("target_umo", "") or "").strip()
                if not target:
                    continue
                st = self._load_state()
                self._sync(st)
                pending = [str(x) for x in (st.get("pending") or [])]
                if not pending:
                    continue
                cooldown = max(0.5, float(self.config.get("propose_cooldown_hours", 6) or 6)) * 3600
                if time.time() - float(st.get("last_propose") or 0) < cooldown:
                    continue
                msg = random.choice(_PROPOSE_TEMPLATES).format(items="、".join(pending[:3]))
                await self.context.send_message(target, [Plain(msg)])
                st["last_propose"] = time.time()
                self._save_state(st)
                logger.info("[柴米油盐] 采购提案已发：%s", msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("[柴米油盐] 提案循环异常: %s", e)
