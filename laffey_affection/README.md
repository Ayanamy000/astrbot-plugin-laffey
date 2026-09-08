# laffey_affection（拉菲好感 · AstrBot P2）

按 UID 持久化好感分，向 LLM 注入短口吻指导。  
**指挥官 UID 仅通过插件配置 / WebUI 填写，代码内不写死。** 未配置时全员封顶在「陌生～友好」。

兼容 `laffey_stickers` / `laffey_interrupt`：本插件不抢回复、不改表情逻辑，只改分 + 注入提示。

## 档位

| 档位 | 分数 | 谁可用 | 口吻要点 |
|------|------|--------|----------|
| 失望 | 0–30 | 全员 | 几乎不回，极困。例：「……Zzz」 |
| 陌生 | 31–60 | 全员 | 软软邀请休息。例：「呼啊……要一起睡一会儿吗？」 |
| 友好 | 61–80 | 全员（非指挥官封顶） | 略熟悉仍短句；**用「你」，禁「指挥官」** |
| 喜欢 | 81–99 | **仅指挥官** | 「和指挥官一起的话，总觉得这样更好……」 |
| 爱 | 100–119 | **仅指挥官** | 「只要在指挥官身边，拉菲就觉得很安心……」 |
| 誓约 | 120–200 | **仅指挥官** | 「被指挥官这么关心着……拉菲，会一直赖着指挥官的。」 |

规则：

1. `commander_uids` 留空 → 所有人最高「友好」（80），无法进入喜欢/爱/誓约  
2. 非指挥官永远钳在友好及以下  
3. 可选 `allow_list_uids`：非空时仅名单内计分/注入  

## 加分 / 扣分（可配）

- `+`：@ / 点名「拉菲」、关心词、果汁/氧气可乐玩笑（有冷却，防刷分）  
- `-`：短时刷屏（窗口 + 条数阈值）  
- 非指挥官加分也不会突破友好封顶  

数据文件：`data/laffey_affection/scores.json`（Docker 常见宿主机 `/opt/astrbot/data/laffey_affection`）。

## 安装

本仓库 monorepo，插件在子目录 `laffey_affection/`：

```bash
git clone https://github.com/Ayanamy000/astrbot-plugin-laffey.git
sudo cp -a astrbot-plugin-laffey/laffey_affection /opt/astrbot/data/plugins/
# 或容器内：cp -a ... /AstrBot/data/plugins/

sudo mkdir -p /opt/astrbot/data/laffey_affection
cd /opt/astrbot && sudo docker compose restart
# 或 WebUI → 插件 → 重载
```

启用后在 **插件配置** 或页面 **dashboard** 填写 `commander_uids`（你的 QQ/平台 UID）。

## WebUI

**插件 → laffey_affection（拉菲好感）→ 页面 dashboard**

可：改指挥官 UID、查看/覆盖好感分、调加减分参数。

## 配置摘要

| 项 | 默认 | 说明 |
|----|------|------|
| enabled | true | 总开关 |
| commander_uids | [] | 指挥官 UID 列表（WebUI 填） |
| allow_list_uids | [] | 可选白名单 |
| data_dir | `/AstrBot/data/laffey_affection` | 分数落盘目录 |
| gain_at / gain_care / gain_juice | 2 / 3 / 2 | 正向加分 |
| spam_penalty | 5 | 刷屏扣分 |
| inject_prompt | true | `on_llm_request` 注入口吻 |

配置落盘：`data/config/laffey_affection_config.json`。

## 行为

- 消息监听：更新分数（不 `stop_event`）  
- `on_llm_request`：按档位注入短提示（优先 `extra_user_content_parts`，失败则追加 system_prompt）  
- 管理命令（需管理员）：`拉菲好感 [uid]`、`拉菲设好感 <uid> <score>`  

## 自检

```bash
python3 -m py_compile main.py
```

## 版本

- P2 `0.1.0`：指挥官 UID（仅配置）、好感持久化、档位口吻、WebUI dashboard  

## License

内部项目交付用；按团队约定。
