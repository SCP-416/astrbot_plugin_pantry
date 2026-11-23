<p align="center">
  <img src="logo.png" width="160" alt="柴米油盐 logo" />
</p>

<h1 align="center">柴米油盐</h1>

<p align="center">
  <b>家里的柴米油盐，见底了会喊你一起去采购。</b><br/>
  一个给 AstrBot 的「过日子」插件：库存会消耗，剧情被库存驱动。
</p>

<p align="center">
  <a href="https://github.com/SCP-416/astrbot_plugin_pantry/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="license" /></a>
  <a href="https://github.com/SCP-416/astrbot_plugin_pantry"><img src="https://img.shields.io/badge/version-0.1.0-green.svg" alt="version" /></a>
  <a href="https://docs.astrbot.app"><img src="https://img.shields.io/badge/AstrBot-%3E%3D4.17.0-orange.svg" alt="AstrBot" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-yellow.svg" alt="Python" />
</p>

---

## 这是什么

记录家里常用的生活物品，**每天按消耗率扣减**；某样东西快见底时，她会**主动发起采购过家家剧情**（「陪我去趟超市呗」）；你们演完采购（挑东西、比价、结账、拎回家），她自动把家里补满。

不是养成游戏，不是数值面板——**库存是剧情发动机**：缺什么，就聊什么。

## 功能特性

- 📦 **库存系统**：十来样家常物品（米、油、盐、酱、醋、鸡蛋、纸巾……），每样有满量和日耗率，带随机波动（今天多炒两个菜，油就掉得多）
- ⏰ **每日结算**：每天自动扣减一次；插件好几天没开也没关系，下次启动会把错过的天数补结算（最多补 90 天）
- ⚠️ **见底触发**：某样 ≤ 阈值（默认 10%）→ 挂起采购任务
- 🗣️ **人格注入**：见底清单会注入她的提示词，聊天时她自然提「家里没米了 陪我去趟超市呗」，不是生硬通知
- ✉️ **主动邀约**（可选）：配置目标会话后，冷却时间一到她主动发采购邀约
- 🛒 **采购闭环**：你说「到家了 / 买好了 / 归置好了」→ 自动补货，家里回满
- 🔍 **查询命令**：发「家里状态」「柴米油盐」查看每样的剩余百分比

## 安装

1. 下载本仓库，把文件夹放进 AstrBot 的 `data/plugins/`（文件夹名建议改成 `astrbot_plugin_pantry`）
2. 重启 AstrBot（或面板里重载插件）
3. 配置里按需改物品清单、阈值、主动邀约

也可以直接从 AstrBot 面板的插件市场搜索「柴米油盐」安装（收录后）。

## 配置说明

| 配置项 | 默认 | 说明 |
|---|---|---|
| `items_json` | 10 样家常物品 | 物品清单（JSON）。`name` 名字 / `max` 满量 / `daily` 每天消耗（满量百分比）/ `var` 波动 0~1 |
| `low_threshold` | 10 | 见底阈值（%） |
| `auto_propose` | true | 是否主动发采购邀约 |
| `target_umo` | 空 | 邀约发往的会话（如 `qqjiejie:FriendMessage:2498108903`）。留空 = 只靠人格注入 |
| `propose_cooldown_hours` | 6 | 邀约冷却（小时） |
| `procurement_words` | 买菜,逛超市,囤货… | 采购开始关键词 |
| `done_words` | 到家了,回家了,买好了… | 采购完成关键词（命中自动补货） |

**日耗手感参考**：日用品 4~6（一两周触发一次采购）、耐用品 0.8~2.5（一个月上下）。

## 使用示例

```
你：家里状态
她：【家里·柴米油盐】
    米 88%
    鸡蛋 9% ⚠️快见底
    食用油 45%
    ……
    快见底了，该去采购了。

（第二天，她主动或聊天时自然提）
她：家里鸡蛋快没了 陪我去趟超市呗
你：走
她：（换鞋拿环保袋）先去生鲜区 今天的鸡蛋好像有活动
你：好
……（演采购过程）……
你：到家了
她：（把买回来的东西归置进柜子）这下不缺了
```

## 和「过家家」怎么搭

本插件只管「家里缺什么」和「补货闭环」。想让采购场景演得更像样（剧本、节点推进），可以配合任意过家家 / 角色扮演玩法一起用；她的人格里只要有人设，采购对话自然就是戏。

## 常见问题

**Q：会不会天天催采购招人烦？**
不会。只有见底物品才触发，而且有冷却；日常消耗带波动，节奏是「一两周一次」的量级。觉得烦就调大 `daily` 或调高阈值。

**Q：好几天没开 AstrBot，库存会变成负数吗？**
不会。补结算时扣到 0 为止，见底物品都进 pending，等一次采购一起补。

**Q：怎么重置库存？**
删掉插件数据目录里的 `pantry_state.json`（路径见 AstrBot 日志），重启插件即可。

**Q：能加物品 / 改消耗速度吗？**
能。`items_json` 里增删条目、调 `daily`（每天消耗百分比）就行，改完重启生效。

## 开发

- `pantry_core.py`：纯逻辑核心（消耗 / 结算 / 补货 / 格式化），不依赖 AstrBot，可单测
- `tests/test_core.py`：60 天消耗模拟、见底、补货闭环测试

```bash
python tests/test_core.py   # ALL TESTS PASSED
```

## 协议

[MIT](LICENSE)
