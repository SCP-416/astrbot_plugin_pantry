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
  <a href="https://github.com/SCP-416/astrbot_plugin_pantry"><img src="https://img.shields.io/badge/version-0.2.0-green.svg" alt="version" /></a>
  <a href="https://docs.astrbot.app"><img src="https://img.shields.io/badge/AstrBot-%3E%3D4.17.0-orange.svg" alt="AstrBot" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-yellow.svg" alt="Python" />
</p>

---

## 这是什么

记录家里常用的生活物品，**每天按消耗率扣减**；某样东西快见底时，她会**按人设写一句采购邀约**，你们一起演挑东西、比价、结账、拎回家，回来交代一句「到家了」，家里自动补满。

库存不是冷冰冰的数字，而是**剧情发动机**：缺什么就聊什么；你随口说「做了番茄炒蛋」，鸡蛋和油就真的少下去；她下次聊天还会自然提起「昨天那盘炒蛋」。

## 功能特性

### 🛒 剧情引擎（0.2 新增）
- **LLM 邀约**：按她的人设写「家里鸡蛋快没了 陪我去趟超市呗」，不是死板模板（可关，省钱用模板）
- **购物清单**：自动按缺口数量列清单（米×2、鸡蛋×3），带单价估算
- **场景分步推进**：出门 → 到店 → 挑东西 → 结账 → 拎回家，每轮只走一个节点，按你的话自动推进
- **消耗事件化**：说「做了番茄炒蛋」「煮面了」就扣对应食材，并记进「最近家里的事」，人格注入会自然带出

### 📦 库存模型
- 十来样家常物品，按主食/生鲜/调料/日用分类展示
- 日耗带随机波动；停机多天自动补结算（最多 90 天）
- 单价与花费统计，发「周报」看最近一周采购与消耗
- 见底阈值可配（默认 10%）

### 🖥️ 控制台面板（0.3 新增）
- 插件加载后，在 AstrBot 控制台的插件卡片上打开「面板」（自动发现 `views/dashboard/index.html`）
- 可视化库存仪表盘；**直接新增 / 编辑 / 删除消耗品**（名字、满量、日耗%、波动、分类、单价），改名自动迁移库存
- 一键重置库存；实时看购物清单、采购场景、最近家里的事
- 原有的 `/api/astrbot_plugin_pantry/page/*` 接口仍可用

### 🔧 其它
- 「家里状态」「购物清单」「周报」查询命令
- 采购邀约目标会话 + 冷却时间可配
- 纯逻辑核心可单测；GitHub Actions CI（ruff + 单测）

## 安装

1. 下载本仓库，把文件夹放进 AstrBot 的 `data/plugins/`（文件夹名建议改成 `astrbot_plugin_pantry`）
2. 重启 AstrBot（或面板里重载插件）
3. 配置里按需改物品清单、阈值、邀约目标会话

也可以从 AstrBot 面板的插件市场搜索「柴米油盐」安装。

## 配置说明

| 配置项 | 默认 | 说明 |
|---|---|---|
| `items_json` | 10 样家常物品 | JSON 数组：`name` / `max` / `daily` / `var` / `category` / `price` / `expire_days` |
| `low_threshold` | 10 | 见底阈值（%） |
| `auto_propose` | true | 见底时主动发邀约（需配 `target_umo`） |
| `llm_propose` | true | 用 LLM 写邀约文案；关闭则用固定模板（省钱） |
| `target_umo` | 空 | 邀约发往的会话，如 `qqjiejie:FriendMessage:2498108903`；留空 = 只在聊天里自然提 |
| `propose_cooldown_hours` | 6 | 邀约冷却（小时） |
| `procurement_words` | 买菜,逛超市,囤货… | 采购开始关键词 |
| `done_words` | 到家了,买好了… | 采购完成关键词（命中自动补货） |

**日耗手感**：日用品 4~6（一两周触发一次采购）、调料 0.8~2.5（一个月上下）。

## 使用示例

```
你：做了个番茄炒蛋
她：（悄悄记下）鸡蛋 93% 油 95%……

（过几天，鸡蛋见底）
她：家里鸡蛋快没了 陪我去趟超市呗
你：走
她：（拿环保袋）出门 路上想吃什么
你：到了
她：（推着车）先去生鲜区 鸡蛋今天有活动
你：这个不错
她：（放进车里）再拿两盒 够吃一周
你：结账
她：（扫码）一共三十八 比上周便宜
你：到家了
她：（把鸡蛋放进冰箱）这下不缺了 晚上给你煎两个
```

## 常见问题

**Q：会不会天天催采购？**
不会。只有见底才触发，有冷却，日耗带波动，节奏约一两周一次。

**Q：LLM 邀约会花钱吗？**
会走你当前 chat provider 的一次短请求（很短）。想省就关 `llm_propose`，用固定模板。

**Q：怎么自定义消耗品？**
打开控制台里柴米油盐的「面板」，点「＋ 新增消耗品」填名字/满量/日耗%就行；卡片上「编辑」可改日耗、分类、单价，「删除」移除。自定义清单存在插件数据目录的 `pantry_items.json`，不会被插件更新覆盖。改完立即生效（下轮结算就用新清单）。

**Q：面板在哪？**
AstrBot 控制台 → 插件 → 柴米油盐 → 面板。如果没看到，重载插件再刷新控制台。

**Q：怎么重置库存？**
面板里「重置库存为满」，或删掉 `pantry_state.json` 重启插件。

## 开发

```bash
python tests/test_core.py   # ALL TESTS PASSED
ruff check .                # CI 自动跑
```

- `pantry_core.py`：纯逻辑（结算、事件、场景、清单、周报），不依赖 AstrBot
- `main.py`：AstrBot 插件胶水 + WebUI

## 协议

[MIT](LICENSE)
