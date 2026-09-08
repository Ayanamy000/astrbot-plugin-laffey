# astrbot-plugin-laffey

家庭群「拉菲」AstrBot 插件 monorepo。

| 目录 | 插件 | 说明 |
|------|------|------|
| [`laffey_stickers/`](./laffey_stickers/) | P1 拉菲表情包 | 关键词标签、冷却/日限/免打扰、WebUI 上传 |
| [`laffey_affection/`](./laffey_affection/) | P2 拉菲好感 | 指挥官 UID（仅配置/WebUI）、好感档位、LLM 口吻注入 |

作者：Ayanamy000 \<185235465+Ayanamy000@users.noreply.github.com\>  
仓库：https://github.com/Ayanamy000/astrbot-plugin-laffey

## 安装（两个都装）

AstrBot 每个插件需单独拷到 `data/plugins/<插件名>/`（目录名 = `metadata.yaml` 的 `name`）。

```bash
git clone https://github.com/Ayanamy000/astrbot-plugin-laffey.git
cd astrbot-plugin-laffey

# Docker 宿主机示例（按实际路径改）
sudo cp -a laffey_stickers  /opt/astrbot/data/plugins/
sudo cp -a laffey_affection /opt/astrbot/data/plugins/

# 运行时数据目录
sudo mkdir -p /opt/astrbot/data/laffey_stickers/{zzz,juice,rabbit,blush,poke,wave,ok,nope,idle}
sudo mkdir -p /opt/astrbot/data/laffey_affection

cd /opt/astrbot && sudo docker compose restart
# 或 WebUI → 插件 → 启用并重载
```

容器内路径对应：

- 插件：`/AstrBot/data/plugins/laffey_stickers`、`.../laffey_affection`
- 表情：`/AstrBot/data/laffey_stickers/<tag>/`
- 好感：`/AstrBot/data/laffey_affection/scores.json`

## 配置要点

### P1 `laffey_stickers`

- WebUI → 插件页 **manager**：上传表情、改标签与冷却  
- 详见 [`laffey_stickers/README.md`](./laffey_stickers/README.md)

### P2 `laffey_affection`

- **指挥官 UID 只在插件设置 / WebUI dashboard 填写，不要写进代码**  
- **未填写** → 全员仅「陌生～友好」，无法进入喜欢/爱/誓约  
- **非指挥官** 永远钳在「友好」及以下；友好档对说话者用「你」，禁叫「指挥官」  
- 喜欢 / 爱 / 誓约：仅 `commander_uids` 内 UID  
- WebUI → 插件页 **dashboard**：填指挥官、看分、调加减分  
- 详见 [`laffey_affection/README.md`](./laffey_affection/README.md)

## 兼容

两插件均不抢主回复链：表情只在 `on_decorating_result` 附加；好感只计分 + `on_llm_request` 注入。可与 `laffey_interrupt` / `active_reply` 同开。

## 目录结构

```
astrbot-plugin-laffey/
├── README.md                 # 本文件
├── laffey_stickers/          # P1
│   ├── main.py
│   ├── metadata.yaml
│   ├── _conf_schema.json
│   ├── README.md
│   └── pages/manager/
└── laffey_affection/         # P2
    ├── main.py
    ├── metadata.yaml
    ├── _conf_schema.json
    ├── README.md
    └── pages/dashboard/
```

## License

内部项目交付用；按团队约定。
