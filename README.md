# laffey_stickers（拉菲表情包 · AstrBot P1）

AstrBot 插件：按关键词匹配标签，在机器人**即将发出回复**时最多附加 **1** 张表情图。  
兼容 `laffey_interrupt` / `active_reply`（约 12% 插话）：本插件**不**自行决定是否回复，只装饰已有回复链。

## 功能

- 默认标签：`zzz` `juice` `rabbit` `blush` `poke` `wave` `ok` `nope` `idle`（可增删改）
- 标签 → 触发关键词（插件配置 `_conf_schema.json` / WebUI 均可管理）
- 每标签冷却（默认 10 分钟）、每日上限（默认 10）、免打扰 0–8（强 @ / 点名「拉菲」可穿透）
- Plugin Page WebUI：CRUD 标签、上传/删除/预览图片、改冷却与限额
- **P1 不要求指挥官 UID**（P2 再加好感/口吻档位）

## 目录结构

```
laffey_stickers/
├── metadata.yaml
├── main.py
├── _conf_schema.json
├── README.md
└── pages/
    └── manager/
        ├── index.html
        ├── app.js
        └── style.css
```

表情文件（运行时，不在本仓库）：

```
<data>/laffey_stickers/{tag}/*.png|jpg|gif|webp
```

Docker 常见映射：宿主机 `/opt/astrbot/data/laffey_stickers` ↔ 容器 `/AstrBot/data/laffey_stickers`。

## 安装

### 方式 A：拷贝到 data/plugins

```bash
# 克隆（仓库 URL 由维护者提供后替换）
git clone <REPO_URL> laffey_stickers

# 拷到 AstrBot 插件目录（Docker 示例）
sudo cp -a laffey_stickers /opt/astrbot/data/plugins/
# 或容器内：
# cp -a laffey_stickers /AstrBot/data/plugins/

# 创建空标签目录（可选，插件启动也会 mkdir）
sudo mkdir -p /opt/astrbot/data/laffey_stickers/{zzz,juice,rabbit,blush,poke,wave,ok,nope,idle}

# 重启 / 重载
cd /opt/astrbot && sudo docker compose restart
# 或 WebUI → 插件 → 重载
```

### 方式 B：AstrBot WebUI 安装

1. 打开 Dashboard（如 `http://<host>:6185` 或现有 Tunnel HTTPS）
2. **插件** → 安装 / 上传（若支持 zip / 本地目录）→ 选择本插件目录或打包 zip
3. 启用 `laffey_stickers` → **重载插件**
4. 进入插件详情 → 打开页面 **manager**（拉菲表情包管理）

## WebUI 入口

登录 AstrBot 后：

**插件 → laffey_stickers（拉菲表情包）→ 页面 / Pages → manager**

直达形态（Dashboard 内嵌页，需已登录）：

- 插件详情页内打开 `manager`
- 后端 API 前缀：`/api/v1/plugins/extensions/laffey_stickers/...`（由 Dashboard bridge 转发，页面内用 `window.AstrBotPluginPage`）

## 上传表情

1. 打开 `manager` 页  
2. 选中或新建标签（如 `zzz`）  
3. 选择图片 → **上传到当前标签**  
4. 可在同页删除、预览；也可直接把文件丢进  
   `/opt/astrbot/data/laffey_stickers/<tag>/`

## 默认配置

| 项 | 默认 |
|----|------|
| enabled | true |
| stickers_root | `/AstrBot/data/laffey_stickers` |
| cooldown_minutes | 10 |
| daily_cap | 10 |
| quiet_start_hour / quiet_end_hour | 0 / 8 |
| max_per_reply | 1 |
| tags | 见 `_conf_schema.json` 默认关键词表 |

配置落盘：`data/config/laffey_stickers_config.json`（AstrBot 按 schema 生成）。也可在 WebUI「插件配置」改。

## 行为说明

- Hook：`on_decorating_result` — 仅在已有回复链时尝试附加图片  
- 按用户消息关键词匹配标签（长词优先）；无图的标签跳过  
- 冷却按**标签**；日限额全局；免打扰时段非强点名不发图  
- 不修改 `laffey_interrupt`、不改 QQ webhook

## 开发自检

```bash
python3 -m py_compile main.py
```

## 版本

- P1：`0.1.0` 标签 + WebUI 上传 + 冷却/限额/免打扰  
- P2（未实现）：指挥官 UID、好感封顶「友好」、档位语气表  

## License

内部项目交付用；按团队约定。
