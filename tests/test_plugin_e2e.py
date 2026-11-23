# -*- coding: utf-8 -*-
"""端到端测试：假 AstrBot 事件驱动插件处理器（需 AstrBot 运行环境）。"""
import asyncio
import importlib.util
import os
import sys
import tempfile
import types

sys.path.insert(0, r"D:\ASTRBOT\backend\app")
ROOT = r"D:\PET\repos\astrbot_plugin_pantry"

pkg = types.ModuleType("pantry_pkg")
pkg.__path__ = [ROOT]
sys.modules["pantry_pkg"] = pkg
spec = importlib.util.spec_from_file_location("pantry_pkg.main", os.path.join(ROOT, "main.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["pantry_pkg.main"] = mod
spec.loader.exec_module(mod)


class FakeEvent:
    def __init__(self, text):
        self.message_str = text
        self.unified_msg_origin = "qqjiejie:FriendMessage:2498108903"
        self.stopped = False

    def is_private_chat(self):
        return True

    def stop_event(self):
        self.stopped = True


class FakeContext:
    def __init__(self):
        self.sent = []

    async def send_message(self, umo, chain):
        self.sent.append((umo, "".join(getattr(x, "text", "") for x in getattr(chain, "chain", []))))

    def get_using_provider(self, umo):
        return None

    def register_web_api(self, *args):
        pass


async def main():
    ctx = FakeContext()
    cfg = {"items_json": "", "llm_propose": False, "target_umo": ""}
    plugin = mod.PantryPlugin(ctx, cfg)
    plugin.config = cfg  # 真实环境由 AstrBot 加载器注入
    plugin.data_dir = tempfile.mkdtemp(prefix="pantry-test-")
    plugin._state_path = os.path.join(plugin.data_dir, "pantry_state.json")

    # 1. 家里状态命令
    await plugin.on_message(FakeEvent("家里状态"))
    assert ctx.sent and "家里·柴米油盐" in ctx.sent[-1][1], ctx.sent
    print("CMD OK:", ctx.sent[-1][1][:40].replace("\n", " | "))

    # 2. 购物清单命令（先人为见底）
    st = plugin._load_state()
    st["items"]["米"] = 2.0
    st["pending"] = ["米"]
    plugin._save_state(st)
    ctx.sent.clear()
    await plugin.on_message(FakeEvent("购物清单"))
    assert ctx.sent and "购物清单" in ctx.sent[-1][1] and "米" in ctx.sent[-1][1], ctx.sent
    print("LIST OK:", ctx.sent[-1][1][:40].replace("\n", " | "))

    # 3. 人格注入
    req = types.SimpleNamespace(system_prompt="原有提示词")
    await plugin.inject_pantry(FakeEvent("你好"), req)
    assert "快见底" in req.system_prompt and "米" in req.system_prompt, req.system_prompt
    print("INJECT OK:", req.system_prompt[-60:].replace("\n", " | "))

    # 4. 消耗事件
    st = plugin._load_state()
    before = st["items"].get("鸡蛋", 100.0)
    await plugin.on_message(FakeEvent("我刚做了饭"))
    st = plugin._load_state()
    assert st["items"]["鸡蛋"] < before, (before, st["items"]["鸡蛋"])
    assert any("做了饭" in e["text"] for e in st["events"])
    print("EVENT OK: 鸡蛋 %.1f -> %.1f" % (before, st["items"]["鸡蛋"]))

    print("PLUGIN E2E ALL PASSED")


asyncio.run(main())
