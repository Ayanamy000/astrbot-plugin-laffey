"""laffey_stickers — keyword stickers for Laffey (AstrBot P1).

Compatible with laffey_interrupt / active_reply: attaches at most one sticker
when a reply is about to be sent (on_decorating_result). Respects per-tag
cooldown, daily cap, quiet hours (strong @ bypasses quiet).
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api.web import PluginUploadFile, error_response, file_response, json_response, request
except Exception:  # pragma: no cover - older builds
    PluginUploadFile = None  # type: ignore
    error_response = None  # type: ignore
    file_response = None  # type: ignore
    json_response = None  # type: ignore
    request = None  # type: ignore

PLUGIN_NAME = "laffey_stickers"
TZ = ZoneInfo("Asia/Shanghai")
NAME_KEYS = ("拉菲", "laffey", "Laffey", "LAFFEY")
DEFAULT_TAGS: Dict[str, List[str]] = {
    "zzz": ["困", "睡觉", "晚安", "Zzz", "zzz", "想睡"],
    "juice": ["果汁", "氧气可乐", "喝", "好喝"],
    "rabbit": ["兔子", "兔兔", "兔"],
    "blush": ["害羞", "脸红", "不好意思"],
    "poke": ["戳", "捅", "poke"],
    "wave": ["你好", "嗨", "hi", "hello", "再见", "拜拜"],
    "ok": ["好的", "可以", "嗯嗯", "OK", "ok", "行"],
    "nope": ["不要", "不行", "拒绝", "no", "Nope"],
    "idle": ["在吗", "干嘛", "摸鱼", "发呆"],
}
IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _safe_tag(name: str) -> str:
    name = (name or "").strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]{1,32}", name):
        raise ValueError("invalid tag name")
    return name


def _host_default_root() -> Path:
    # Prefer container data path; fall back to host-style path when running outside Docker.
    for p in (Path("/AstrBot/data/laffey_stickers"), Path("/opt/astrbot/data/laffey_stickers")):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    p = Path("data/laffey_stickers")
    p.mkdir(parents=True, exist_ok=True)
    return p


@register(PLUGIN_NAME, "project-dev", "Laffey stickers", "0.1.0")
class LaffeyStickers(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._tag_cd_until: Dict[str, float] = {}
        self._daily_count = 0
        self._daily_day: Optional[date] = None
        self._ensure_roots()
        self._register_web()
        logger.info("laffey_stickers loaded root=%s tags=%s", self.stickers_root, list(self.tags.keys()))

    # ---- config helpers ----
    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    @property
    def stickers_root(self) -> Path:
        raw = (self.config.get("stickers_root") or "").strip()
        if raw:
            return Path(raw)
        return _host_default_root()

    @property
    def cooldown_minutes(self) -> int:
        try:
            return max(0, int(self.config.get("cooldown_minutes", 10)))
        except Exception:
            return 10

    @property
    def daily_cap(self) -> int:
        try:
            return max(0, int(self.config.get("daily_cap", 10)))
        except Exception:
            return 10

    @property
    def quiet_start(self) -> int:
        try:
            return int(self.config.get("quiet_start_hour", 0)) % 24
        except Exception:
            return 0

    @property
    def quiet_end(self) -> int:
        try:
            return int(self.config.get("quiet_end_hour", 8)) % 24
        except Exception:
            return 8

    @property
    def max_per_reply(self) -> int:
        try:
            return max(1, min(3, int(self.config.get("max_per_reply", 1))))
        except Exception:
            return 1

    @property
    def tags(self) -> Dict[str, List[str]]:
        raw = self.config.get("tags")
        if isinstance(raw, dict) and raw:
            out: Dict[str, List[str]] = {}
            for k, v in raw.items():
                try:
                    tk = _safe_tag(str(k))
                except ValueError:
                    continue
                if isinstance(v, list):
                    out[tk] = [str(x) for x in v if str(x).strip()]
                elif isinstance(v, str) and v.strip():
                    out[tk] = [v.strip()]
                else:
                    out[tk] = []
            return out or dict(DEFAULT_TAGS)
        return dict(DEFAULT_TAGS)

    def _save_config(self) -> None:
        """Persist config dict if AstrBot config object supports save."""
        try:
            if hasattr(self.config, "save"):
                self.config.save()  # type: ignore[attr-defined]
                return
        except Exception as e:
            logger.warning("config.save failed: %s", e)
        # Fallback: write data/config/laffey_stickers_config.json
        try:
            cfg_path = Path("/AstrBot/data/config/laffey_stickers_config.json")
            if not cfg_path.parent.exists():
                cfg_path = Path("/opt/astrbot/data/config/laffey_stickers_config.json")
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(self.config) if not isinstance(self.config, dict) else self.config
            # AstrBot config may be a special mapping
            try:
                payload = {k: self.config[k] for k in self.config.keys()}  # type: ignore
            except Exception:
                payload = dict(self.config) if isinstance(self.config, dict) else {}
            cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("fallback config write failed: %s", e)

    def _set_tags(self, tags: Dict[str, List[str]]) -> None:
        try:
            self.config["tags"] = tags
        except Exception:
            if isinstance(self.config, dict):
                self.config["tags"] = tags
        self._ensure_roots()
        self._save_config()

    def _ensure_roots(self) -> None:
        root = self.stickers_root
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("cannot mkdir stickers root %s: %s", root, e)
            return
        for tag in self.tags.keys():
            try:
                (root / tag).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    # ---- runtime gates ----
    def _is_named(self, event: AstrMessageEvent) -> bool:
        try:
            if event.is_at_or_wake_command:
                return True
        except Exception:
            pass
        text = ""
        try:
            text = (event.message_str or "").strip()
        except Exception:
            text = ""
        return bool(text) and any(k in text for k in NAME_KEYS)

    def _in_quiet_hours(self) -> bool:
        h = datetime.now(TZ).hour
        s, e = self.quiet_start, self.quiet_end
        if s == e:
            return False
        if s < e:
            return s <= h < e
        return h >= s or h < e

    def _roll_daily(self) -> None:
        today = datetime.now(TZ).date()
        if self._daily_day != today:
            self._daily_day = today
            self._daily_count = 0

    def _can_send_tag(self, tag: str, *, strong: bool) -> bool:
        if not self.enabled:
            return False
        self._roll_daily()
        if self.daily_cap and self._daily_count >= self.daily_cap:
            return False
        if self._in_quiet_hours() and not strong:
            return False
        until = self._tag_cd_until.get(tag, 0)
        if time.time() < until:
            return False
        imgs = self._list_images(tag)
        return bool(imgs)

    def _mark_sent(self, tag: str) -> None:
        self._roll_daily()
        self._daily_count += 1
        self._tag_cd_until[tag] = time.time() + self.cooldown_minutes * 60

    def _list_images(self, tag: str) -> List[Path]:
        d = self.stickers_root / tag
        if not d.is_dir():
            return []
        out: List[Path] = []
        try:
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() in IMG_EXTS:
                    out.append(p)
        except Exception:
            return []
        return out

    def _match_tags(self, text: str) -> List[str]:
        text_l = text.lower()
        hits: List[Tuple[int, str]] = []
        for tag, keys in self.tags.items():
            best = -1
            for k in keys:
                if not k:
                    continue
                if k.lower() in text_l or k in text:
                    best = max(best, len(k))
            if best >= 0:
                hits.append((best, tag))
        hits.sort(key=lambda x: (-x[0], x[1]))
        return [t for _, t in hits]

    def _pick_sticker(self, event: AstrMessageEvent) -> Optional[Tuple[str, Path]]:
        try:
            text = (event.message_str or "").strip()
        except Exception:
            text = ""
        if not text:
            return None
        strong = self._is_named(event)
        for tag in self._match_tags(text):
            if not self._can_send_tag(tag, strong=strong):
                continue
            imgs = self._list_images(tag)
            if not imgs:
                continue
            return tag, random.choice(imgs)
        return None

    @filter.on_decorating_result(priority=20)
    async def attach_sticker(self, event: AstrMessageEvent):
        if not self.enabled:
            return
        try:
            result = event.get_result()
        except Exception:
            return
        if result is None or not getattr(result, "chain", None):
            return
        # already has image → still allow at most max_per_reply stickers total images from us
        existing_imgs = sum(1 for c in result.chain if isinstance(c, Comp.Image))
        if existing_imgs >= self.max_per_reply:
            return
        picked = self._pick_sticker(event)
        if not picked:
            return
        tag, path = picked
        try:
            result.chain.append(Comp.Image.fromFileSystem(str(path)))
            self._mark_sent(tag)
            logger.info("laffey_stickers attached tag=%s file=%s", tag, path.name)
        except Exception as e:
            logger.warning("attach sticker failed: %s", e)

    # ---- WebUI APIs ----
    def _register_web(self) -> None:
        if request is None or json_response is None:
            logger.warning("laffey_stickers: astrbot.api.web unavailable, skip plugin page APIs")
            return
        api = self.context.register_web_api
        api(f"/{PLUGIN_NAME}/state", self.api_state, ["GET"], "Get sticker state")
        api(f"/{PLUGIN_NAME}/settings", self.api_settings_save, ["POST"], "Save settings")
        api(f"/{PLUGIN_NAME}/tags", self.api_tags_list, ["GET"], "List tags")
        api(f"/{PLUGIN_NAME}/tags/upsert", self.api_tag_upsert, ["POST"], "Create/update tag")
        api(f"/{PLUGIN_NAME}/tags/delete", self.api_tag_delete, ["POST"], "Delete tag")
        api(f"/{PLUGIN_NAME}/images", self.api_images_list, ["GET"], "List images in tag")
        api(f"/{PLUGIN_NAME}/images/upload", self.api_image_upload, ["POST"], "Upload image")
        api(f"/{PLUGIN_NAME}/images/upload/<tag>", self.api_image_upload_tagged, ["POST"], "Upload image to tag")
        api(f"/{PLUGIN_NAME}/images/delete", self.api_image_delete, ["POST"], "Delete image")
        api(f"/{PLUGIN_NAME}/images/preview/<tag>/<filename>", self.api_image_preview, ["GET"], "Preview image")
        api(f"/{PLUGIN_NAME}/images/preview_b64", self.api_image_preview_b64, ["GET"], "Preview image as base64")

    async def api_state(self):
        self._roll_daily()
        return json_response(
            {
                "enabled": self.enabled,
                "stickers_root": str(self.stickers_root),
                "cooldown_minutes": self.cooldown_minutes,
                "daily_cap": self.daily_cap,
                "daily_count": self._daily_count,
                "quiet_start_hour": self.quiet_start,
                "quiet_end_hour": self.quiet_end,
                "max_per_reply": self.max_per_reply,
                "tags": self.tags,
                "tag_image_counts": {t: len(self._list_images(t)) for t in self.tags},
            }
        )

    async def api_settings_save(self):
        payload = await request.json(default={})
        for key, caster in (
            ("enabled", bool),
            ("cooldown_minutes", int),
            ("daily_cap", int),
            ("quiet_start_hour", int),
            ("quiet_end_hour", int),
            ("max_per_reply", int),
        ):
            if key in payload:
                try:
                    self.config[key] = caster(payload[key])
                except Exception:
                    return error_response(f"invalid {key}", status_code=400)
        if "stickers_root" in payload and isinstance(payload["stickers_root"], str):
            self.config["stickers_root"] = payload["stickers_root"].strip() or str(self.stickers_root)
        self._ensure_roots()
        self._save_config()
        return json_response(
            {
                "saved": True,
                "enabled": self.enabled,
                "cooldown_minutes": self.cooldown_minutes,
                "daily_cap": self.daily_cap,
                "quiet_start_hour": self.quiet_start,
                "quiet_end_hour": self.quiet_end,
                "max_per_reply": self.max_per_reply,
                "stickers_root": str(self.stickers_root),
            }
        )

    async def api_tags_list(self):
        return json_response({"tags": self.tags, "counts": {t: len(self._list_images(t)) for t in self.tags}})

    async def api_tag_upsert(self):
        payload = await request.json(default={})
        try:
            tag = _safe_tag(str(payload.get("tag", "")))
        except ValueError:
            return error_response("invalid tag", status_code=400)
        triggers = payload.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [x.strip() for x in re.split(r"[,，\n]", triggers) if x.strip()]
        if not isinstance(triggers, list):
            return error_response("triggers must be list", status_code=400)
        tags = dict(self.tags)
        tags[tag] = [str(x).strip() for x in triggers if str(x).strip()]
        self._set_tags(tags)
        return json_response({"ok": True, "tag": tag, "triggers": tags[tag]})

    async def api_tag_delete(self):
        payload = await request.json(default={})
        try:
            tag = _safe_tag(str(payload.get("tag", "")))
        except ValueError:
            return error_response("invalid tag", status_code=400)
        delete_files = bool(payload.get("delete_files", False))
        tags = dict(self.tags)
        if tag in tags:
            del tags[tag]
            self._set_tags(tags)
        if delete_files:
            d = self.stickers_root / tag
            if d.is_dir():
                for p in self._list_images(tag):
                    try:
                        p.unlink()
                    except Exception:
                        pass
                try:
                    d.rmdir()
                except Exception:
                    pass
        return json_response({"ok": True})

    async def api_images_list(self):
        tag = request.query.get("tag", "")
        try:
            tag = _safe_tag(tag)
        except ValueError:
            return error_response("invalid tag", status_code=400)
        files = [p.name for p in self._list_images(tag)]
        return json_response({"tag": tag, "files": files})


    async def api_image_upload_tagged(self, tag: str):
        # reuse upload; inject tag into query via monkeypatch on form path
        # simplest: set on request query by calling shared impl
        return await self._do_upload(tag)

    async def api_image_upload(self):
        form = await request.form()
        tag_raw = form.get("tag") or request.query.get("tag", "")
        return await self._do_upload(tag_raw)

    async def _do_upload(self, tag_raw):
        files = await request.files()
        try:
            tag = _safe_tag(str(tag_raw))
        except ValueError:
            return error_response("invalid tag", status_code=400)
        upload = files.get("file") if files else None
        if PluginUploadFile is not None and not isinstance(upload, PluginUploadFile):
            # also accept if duck-typed
            if upload is None:
                return error_response("missing file", status_code=400)
        if upload is None:
            return error_response("missing file", status_code=400)
        filename = Path(getattr(upload, "filename", None) or "sticker.png").name
        ext = Path(filename).suffix.lower()
        if ext not in IMG_EXTS:
            return error_response("unsupported image type", status_code=400)
        # ensure tag exists
        tags = dict(self.tags)
        if tag not in tags:
            tags[tag] = []
            self._set_tags(tags)
        dest_dir = self.stickers_root / tag
        dest_dir.mkdir(parents=True, exist_ok=True)
        # unique name
        stem = re.sub(r"[^A-Za-z0-9_\-]+", "_", Path(filename).stem)[:40] or "img"
        dest = dest_dir / f"{stem}_{int(time.time())}{ext}"
        try:
            await upload.save(dest)
        except Exception:
            # fallback write
            data = await upload.read() if hasattr(upload, "read") else None
            if data is None:
                return error_response("save failed", status_code=500)
            dest.write_bytes(data)
        return json_response({"ok": True, "tag": tag, "file": dest.name})

    async def api_image_delete(self):
        payload = await request.json(default={})
        try:
            tag = _safe_tag(str(payload.get("tag", "")))
        except ValueError:
            return error_response("invalid tag", status_code=400)
        filename = Path(str(payload.get("file", ""))).name
        if not filename:
            return error_response("missing file", status_code=400)
        path = self.stickers_root / tag / filename
        if path.is_file() and path.resolve().parent == (self.stickers_root / tag).resolve():
            try:
                path.unlink()
            except Exception as e:
                return error_response(str(e), status_code=500)
        return json_response({"ok": True})


    async def api_image_preview_b64(self):
        tag = request.query.get("tag", "")
        filename = request.query.get("file", "")
        try:
            tag = _safe_tag(tag)
        except ValueError:
            return error_response("invalid tag", status_code=400)
        filename = Path(filename).name
        path = self.stickers_root / tag / filename
        if not path.is_file():
            return error_response("not found", status_code=404)
        try:
            if path.resolve().parent != (self.stickers_root / tag).resolve():
                return error_response("forbidden", status_code=403)
        except Exception:
            return error_response("forbidden", status_code=403)
        data = path.read_bytes()
        if len(data) > 2_500_000:
            return error_response("too large", status_code=400)
        import base64 as _b64
        ctype = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(path.suffix.lower(), "application/octet-stream")
        return json_response({
            "tag": tag,
            "file": filename,
            "content_type": ctype,
            "data_url": f"data:{ctype};base64," + _b64.b64encode(data).decode("ascii"),
        })

    async def api_image_preview(self, tag: str, filename: str):
        try:
            tag = _safe_tag(tag)
        except ValueError:
            return error_response("invalid tag", status_code=400)
        filename = Path(filename).name
        path = self.stickers_root / tag / filename
        if not path.is_file():
            return error_response("not found", status_code=404)
        try:
            if path.resolve().parent != (self.stickers_root / tag).resolve():
                return error_response("forbidden", status_code=403)
        except Exception:
            return error_response("forbidden", status_code=403)
        ctype = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(path.suffix.lower(), "application/octet-stream")
        return file_response(path, filename=filename, content_type=ctype)
