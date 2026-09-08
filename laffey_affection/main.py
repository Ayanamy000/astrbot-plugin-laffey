"""laffey_affection — commander UID + affection levels + tone inject (AstrBot P2).

Lightweight companion to laffey_stickers / laffey_interrupt:
- persists per-UID scores under data/laffey_affection/
- caps non-commander at 友好; commander-only 喜欢/爱/誓约
- injects short tone guidance on_llm_request (万用助手档位表)
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api.web import error_response, json_response, request
except Exception:  # pragma: no cover
    error_response = None  # type: ignore
    json_response = None  # type: ignore
    request = None  # type: ignore

try:
    from astrbot.core.agent.message import TextPart
except Exception:  # pragma: no cover
    TextPart = None  # type: ignore

PLUGIN_NAME = "laffey_affection"
NAME_KEYS = ("拉菲", "laffey", "Laffey", "LAFFEY")

# Azur Lane–style bands (integer scores).
LEVEL_BANDS: List[Tuple[int, int, str]] = [
    (0, 30, "失望"),
    (31, 60, "陌生"),
    (61, 80, "友好"),
    (81, 99, "喜欢"),
    (100, 119, "爱"),
    (120, 200, "誓约"),
]
COMMANDER_ONLY_LEVELS = {"喜欢", "爱", "誓约"}
FRIEND_CAP_SCORE = 80  # 友好 upper bound
FRIEND_CAP_LEVEL = "友好"

# Short tone lines for LLM（万用定稿短句示例；第三人称「拉菲」）。
# 喜欢/爱/誓约仅指挥官；友好禁叫「指挥官」。
TONE_BY_LEVEL: Dict[str, str] = {
    "失望": (
        "档位：失望。几乎不想回话，极度困倦；极短或几乎不回。"
        "口吻示例：「……Zzz」「……」「唔……」（不要热情，不要长句）。"
    ),
    "陌生": (
        "档位：陌生。轻软疏离，可软软邀请对方休息/打盹；仍短句。"
        "口吻示例：「呼啊……要一起睡一会儿吗？」「拉菲……有点困。」"
    ),
    "友好": (
        "档位：友好。略熟悉但仍短句；对说话者必须用「你」，严禁称呼「指挥官」。"
        "口吻示例：「你……有点无聊，不过拉菲也没干劲……说不定合得来。」"
        "「嗯……你说的，拉菲听到了。」"
    ),
    "喜欢": (
        "档位：喜欢（仅指挥官）。依赖指挥官陪伴；自称「拉菲」，短句困倦。"
        "口吻示例：「虽然习惯一个人……和指挥官一起的话，总觉得这样更好……呣……」"
    ),
    "爱": (
        "档位：爱（仅指挥官）。Wiki 式依赖与安心；自称「拉菲」，仍短句。"
        "口吻示例：「只要在指挥官身边，拉菲就觉得很安心……能一直在一起吗？」"
        "「指挥官……拉菲，有点离不开了。」"
    ),
    "誓约": (
        "档位：誓约（仅指挥官）。誓约后的专一依赖；自称「拉菲」，短句温柔困倦。"
        "口吻示例：「被指挥官这么关心着……拉菲，会一直赖着指挥官的。」"
        "「指挥官……拉菲，不失望。」"
    ),
}

CARE_KEYS = (
    "关心", "抱抱", "摸摸", "摸摸头", "晚安", "早点睡", "休息", "别累",
    "辛苦", "加油", "想你", "陪我", "在吗", "吃饭", "喝水",
)
JUICE_KEYS = ("果汁", "氧气可乐", "可乐", "好喝", "喝一口")


def _as_str_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,，\s]+", raw.strip())
        return [p for p in parts if p]
    if isinstance(raw, list):
        out: List[str] = []
        for x in raw:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    return [str(raw).strip()] if str(raw).strip() else []


def _host_default_root() -> Path:
    for p in (
        Path("/AstrBot/data/laffey_affection"),
        Path("/opt/astrbot/data/laffey_affection"),
    ):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    p = Path("data/laffey_affection")
    p.mkdir(parents=True, exist_ok=True)
    return p


def score_to_level(score: int) -> str:
    score = int(score)
    for lo, hi, name in LEVEL_BANDS:
        if lo <= score <= hi:
            return name
    if score < 0:
        return "失望"
    return "誓约"


@register(PLUGIN_NAME, "Ayanamy000", "Laffey affection", "0.1.0")
class LaffeyAffection(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self._lock = threading.RLock()
        self._scores: Dict[str, int] = {}
        self._msg_times: Dict[str, List[float]] = {}
        self._last_gain: Dict[str, float] = {}
        self._load_scores()
        self._register_web()
        logger.info(
            "laffey_affection loaded data=%s commanders=%s scores=%d",
            self.data_dir,
            self.commander_uids,
            len(self._scores),
        )

    # ---- config ----
    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    @property
    def commander_uids(self) -> List[str]:
        return _as_str_list(self.config.get("commander_uids"))

    @property
    def allow_list_uids(self) -> List[str]:
        return _as_str_list(self.config.get("allow_list_uids"))

    @property
    def data_dir(self) -> Path:
        raw = (self.config.get("data_dir") or "").strip()
        if raw:
            return Path(raw)
        return _host_default_root()

    @property
    def scores_path(self) -> Path:
        return self.data_dir / "scores.json"

    def _int_cfg(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default

    @property
    def gain_at(self) -> int:
        return max(0, self._int_cfg("gain_at", 2))

    @property
    def gain_care(self) -> int:
        return max(0, self._int_cfg("gain_care", 3))

    @property
    def gain_juice(self) -> int:
        return max(0, self._int_cfg("gain_juice", 2))

    @property
    def spam_penalty(self) -> int:
        return max(0, self._int_cfg("spam_penalty", 5))

    @property
    def spam_window_seconds(self) -> int:
        return max(1, self._int_cfg("spam_window_seconds", 8))

    @property
    def spam_threshold(self) -> int:
        return max(2, self._int_cfg("spam_threshold", 4))

    @property
    def gain_cooldown_seconds(self) -> int:
        return max(0, self._int_cfg("gain_cooldown_seconds", 30))

    @property
    def inject_prompt(self) -> bool:
        return bool(self.config.get("inject_prompt", True))

    @property
    def default_score(self) -> int:
        return self._clamp(self._int_cfg("default_score", 45))

    @property
    def max_score(self) -> int:
        return max(80, self._int_cfg("max_score", 200))

    @property
    def min_score(self) -> int:
        return min(0, self._int_cfg("min_score", 0))

    def _clamp(self, score: int) -> int:
        return max(self.min_score, min(self.max_score, int(score)))

    def _save_config(self) -> None:
        try:
            if hasattr(self.config, "save"):
                self.config.save()  # type: ignore[attr-defined]
                return
        except Exception as e:
            logger.warning("config.save failed: %s", e)
        try:
            cfg_path = Path("/AstrBot/data/config/laffey_affection_config.json")
            if not cfg_path.parent.exists():
                cfg_path = Path("/opt/astrbot/data/config/laffey_affection_config.json")
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                payload = {k: self.config[k] for k in self.config.keys()}  # type: ignore
            except Exception:
                payload = dict(self.config) if isinstance(self.config, dict) else {}
            cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("fallback config write failed: %s", e)

    # ---- persistence ----
    def _load_scores(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("mkdir data_dir failed: %s", e)
        path = self.scores_path
        if not path.is_file():
            self._scores = {}
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            scores = raw.get("scores", raw) if isinstance(raw, dict) else {}
            out: Dict[str, int] = {}
            if isinstance(scores, dict):
                for k, v in scores.items():
                    try:
                        out[str(k)] = int(v)
                    except Exception:
                        continue
            self._scores = out
        except Exception as e:
            logger.warning("load scores failed: %s", e)
            self._scores = {}

    def _persist_scores(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": int(time.time()),
                "scores": dict(self._scores),
            }
            tmp = self.scores_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.scores_path)
        except Exception as e:
            logger.warning("persist scores failed: %s", e)

    # ---- identity / caps ----
    def _sender_uid(self, event: AstrMessageEvent) -> str:
        try:
            uid = event.get_sender_id()
            if uid is not None and str(uid).strip():
                return str(uid).strip()
        except Exception:
            pass
        try:
            sender = getattr(getattr(event, "message_obj", None), "sender", None)
            if sender is not None:
                for attr in ("user_id", "id", "uid"):
                    v = getattr(sender, attr, None)
                    if v is not None and str(v).strip():
                        return str(v).strip()
        except Exception:
            pass
        return ""

    def _is_commander(self, uid: str) -> bool:
        if not uid:
            return False
        commanders = self.commander_uids
        if not commanders:
            return False
        return uid in commanders

    def _in_allow_list(self, uid: str) -> bool:
        allow = self.allow_list_uids
        if not allow:
            return True
        return uid in allow

    def _cap_for(self, uid: str) -> int:
        """Non-commander (or no commander configured) capped at 友好."""
        if self._is_commander(uid):
            return self.max_score
        return min(FRIEND_CAP_SCORE, self.max_score)

    def get_score(self, uid: str) -> int:
        with self._lock:
            if uid not in self._scores:
                return self.default_score
            return self._clamp(self._scores[uid])

    def effective_level(self, uid: str) -> str:
        score = min(self.get_score(uid), self._cap_for(uid))
        level = score_to_level(score)
        if level in COMMANDER_ONLY_LEVELS and not self._is_commander(uid):
            return FRIEND_CAP_LEVEL
        return level

    def set_score(self, uid: str, score: int) -> int:
        uid = str(uid).strip()
        if not uid:
            return 0
        capped = min(self._clamp(score), self._cap_for(uid))
        with self._lock:
            self._scores[uid] = capped
            self._persist_scores()
        return capped

    def adjust_score(self, uid: str, delta: int) -> int:
        uid = str(uid).strip()
        if not uid or delta == 0:
            return self.get_score(uid)
        with self._lock:
            cur = self._scores.get(uid, self.default_score)
            nxt = min(self._clamp(cur + delta), self._cap_for(uid))
            # Non-commander must never enter commander-tier bands via rounding edge cases.
            if not self._is_commander(uid):
                nxt = min(nxt, FRIEND_CAP_SCORE)
            self._scores[uid] = nxt
            self._persist_scores()
            return nxt

    # ---- message signals ----
    def _is_named(self, event: AstrMessageEvent, text: str) -> bool:
        try:
            if event.is_at_or_wake_command:
                return True
        except Exception:
            pass
        try:
            chain = getattr(getattr(event, "message_obj", None), "message", None) or []
            for seg in chain:
                name = type(seg).__name__
                if name == "At":
                    return True
        except Exception:
            pass
        return bool(text) and any(k in text for k in NAME_KEYS)

    def _hit_any(self, text: str, keys: tuple) -> bool:
        if not text:
            return False
        t = text.lower()
        for k in keys:
            if k.lower() in t or k in text:
                return True
        return False

    def _note_spam(self, uid: str, now: float) -> bool:
        window = float(self.spam_window_seconds)
        thr = self.spam_threshold
        with self._lock:
            times = self._msg_times.setdefault(uid, [])
            times.append(now)
            # prune
            cutoff = now - window
            while times and times[0] < cutoff:
                times.pop(0)
            return len(times) >= thr

    def _can_gain(self, uid: str, now: float) -> bool:
        cd = self.gain_cooldown_seconds
        if cd <= 0:
            return True
        with self._lock:
            last = self._last_gain.get(uid, 0.0)
            if now - last < cd:
                return False
            self._last_gain[uid] = now
            return True

    def _apply_message_delta(self, event: AstrMessageEvent) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        uid = self._sender_uid(event)
        if not uid or not self._in_allow_list(uid):
            return None
        try:
            text = (event.message_str or "").strip()
        except Exception:
            text = ""
        now = time.time()
        delta = 0
        reasons: List[str] = []

        if self._note_spam(uid, now):
            pen = self.spam_penalty
            if pen:
                delta -= pen
                reasons.append(f"spam-{pen}")

        positive = 0
        if self._is_named(event, text) and self.gain_at:
            positive += self.gain_at
            reasons.append(f"at+{self.gain_at}")
        if self._hit_any(text, CARE_KEYS) and self.gain_care:
            positive += self.gain_care
            reasons.append(f"care+{self.gain_care}")
        if self._hit_any(text, JUICE_KEYS) and self.gain_juice:
            positive += self.gain_juice
            reasons.append(f"juice+{self.gain_juice}")

        if positive:
            if self._can_gain(uid, now):
                delta += positive
            else:
                reasons.append("gain_cd")

        if delta == 0:
            return {
                "uid": uid,
                "delta": 0,
                "score": self.get_score(uid),
                "level": self.effective_level(uid),
                "reasons": reasons,
            }

        # Commander-only high gains: non-commander still can gain within friend cap.
        new_score = self.adjust_score(uid, delta)
        level = self.effective_level(uid)
        logger.info(
            "laffey_affection uid=%s delta=%s score=%s level=%s reasons=%s commander=%s",
            uid,
            delta,
            new_score,
            level,
            ",".join(reasons) or "-",
            self._is_commander(uid),
        )
        return {
            "uid": uid,
            "delta": delta,
            "score": new_score,
            "level": level,
            "reasons": reasons,
        }

    def _tone_text(self, uid: str) -> str:
        level = self.effective_level(uid)
        score = min(self.get_score(uid), self._cap_for(uid))
        base = TONE_BY_LEVEL.get(level, TONE_BY_LEVEL["陌生"])
        role = "指挥官" if self._is_commander(uid) else "普通用户"
        return (
            f"<laffey_affection>\n"
            f"说话者身份：{role}；好感分≈{score}；档位：{level}。\n"
            f"口吻指导：{base}\n"
            f"始终保持拉菲短句、困倦语气；不要长篇说教。\n"
            f"</laffey_affection>"
        )

    # ---- hooks ----
    @filter.event_message_type(filter.EventMessageType.ALL, priority=50)
    async def on_message_score(self, event: AstrMessageEvent):
        """Track affection on incoming messages; never stop the event."""
        try:
            self._apply_message_delta(event)
        except Exception as e:
            logger.warning("affection score update failed: %s", e)

    @filter.on_llm_request(priority=40)
    async def inject_tone(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.enabled or not self.inject_prompt:
            return
        uid = self._sender_uid(event)
        if not uid or not self._in_allow_list(uid):
            return
        # Also apply light scoring when LLM is about to reply (covers @ wake paths).
        try:
            self._apply_message_delta(event)
        except Exception:
            pass
        text = self._tone_text(uid)
        try:
            if TextPart is not None and hasattr(req, "extra_user_content_parts"):
                part = TextPart(text=text)
                if hasattr(part, "mark_as_temp"):
                    try:
                        part = part.mark_as_temp()
                    except Exception:
                        pass
                req.extra_user_content_parts.append(part)
                return
        except Exception as e:
            logger.warning("extra_user_content_parts inject failed: %s", e)
        try:
            req.system_prompt = (req.system_prompt or "") + "\n" + text
        except Exception as e:
            logger.warning("system_prompt inject failed: %s", e)

    # ---- admin commands (optional convenience) ----
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("拉菲好感", alias={"laffey_aff", "好感查询"})
    async def cmd_query(self, event: AstrMessageEvent, uid: str = ""):
        target = (uid or "").strip() or self._sender_uid(event)
        if not target:
            yield event.plain_result("拉菲……找不到 UID。")
            return
        score = min(self.get_score(target), self._cap_for(target))
        level = self.effective_level(target)
        role = "指挥官" if self._is_commander(target) else "普通"
        yield event.plain_result(
            f"拉菲看了看……\nUID {target}（{role}）\n好感 {score} · 档位「{level}」"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("拉菲设好感", alias={"laffey_setaff"})
    async def cmd_set(self, event: AstrMessageEvent, uid: str, score: int):
        new = self.set_score(uid, score)
        yield event.plain_result(
            f"好感已设：{uid} → {new}（{self.effective_level(uid)}）"
        )

    # ---- WebUI ----
    def _register_web(self) -> None:
        if request is None or json_response is None:
            logger.warning("laffey_affection: astrbot.api.web unavailable, skip page APIs")
            return
        api = self.context.register_web_api
        api(f"/{PLUGIN_NAME}/state", self.api_state, ["GET"], "Affection state")
        api(f"/{PLUGIN_NAME}/settings", self.api_settings_save, ["POST"], "Save settings")
        api(f"/{PLUGIN_NAME}/scores", self.api_scores_list, ["GET"], "List scores")
        api(f"/{PLUGIN_NAME}/scores/set", self.api_score_set, ["POST"], "Set score")
        api(f"/{PLUGIN_NAME}/scores/delete", self.api_score_delete, ["POST"], "Delete score")

    def _public_state(self) -> dict:
        rows = []
        with self._lock:
            items = list(self._scores.items())
        for uid, score in sorted(items, key=lambda x: (-int(x[1]), x[0])):
            cap = self._cap_for(uid)
            eff = min(int(score), cap)
            rows.append(
                {
                    "uid": uid,
                    "score": eff,
                    "raw_score": int(score),
                    "level": self.effective_level(uid),
                    "is_commander": self._is_commander(uid),
                    "cap": cap,
                }
            )
        return {
            "enabled": self.enabled,
            "commander_uids": self.commander_uids,
            "allow_list_uids": self.allow_list_uids,
            "data_dir": str(self.data_dir),
            "inject_prompt": self.inject_prompt,
            "gain_at": self.gain_at,
            "gain_care": self.gain_care,
            "gain_juice": self.gain_juice,
            "spam_penalty": self.spam_penalty,
            "spam_window_seconds": self.spam_window_seconds,
            "spam_threshold": self.spam_threshold,
            "gain_cooldown_seconds": self.gain_cooldown_seconds,
            "default_score": self.default_score,
            "max_score": self.max_score,
            "levels": [
                {"name": n, "lo": lo, "hi": hi, "commander_only": n in COMMANDER_ONLY_LEVELS}
                for lo, hi, n in LEVEL_BANDS
            ],
            "scores": rows,
        }

    async def api_state(self):
        return json_response(self._public_state())

    async def api_settings_save(self):
        payload = await request.json(default={})
        if "enabled" in payload:
            self.config["enabled"] = bool(payload["enabled"])
        if "inject_prompt" in payload:
            self.config["inject_prompt"] = bool(payload["inject_prompt"])
        if "commander_uids" in payload:
            self.config["commander_uids"] = _as_str_list(payload["commander_uids"])
        if "allow_list_uids" in payload:
            self.config["allow_list_uids"] = _as_str_list(payload["allow_list_uids"])
        if "data_dir" in payload and isinstance(payload["data_dir"], str):
            self.config["data_dir"] = payload["data_dir"].strip() or str(self.data_dir)
        for key in (
            "gain_at",
            "gain_care",
            "gain_juice",
            "spam_penalty",
            "spam_window_seconds",
            "spam_threshold",
            "gain_cooldown_seconds",
            "default_score",
            "max_score",
        ):
            if key in payload:
                try:
                    self.config[key] = int(payload[key])
                except Exception:
                    return error_response(f"invalid {key}", status_code=400)
        self._save_config()
        # Re-cap existing scores after commander list change
        with self._lock:
            for uid in list(self._scores.keys()):
                self._scores[uid] = min(self._clamp(self._scores[uid]), self._cap_for(uid))
            self._persist_scores()
        return json_response({"saved": True, **self._public_state()})

    async def api_scores_list(self):
        return json_response({"scores": self._public_state()["scores"]})

    async def api_score_set(self):
        payload = await request.json(default={})
        uid = str(payload.get("uid", "")).strip()
        if not uid:
            return error_response("missing uid", status_code=400)
        try:
            score = int(payload.get("score"))
        except Exception:
            return error_response("invalid score", status_code=400)
        new = self.set_score(uid, score)
        return json_response(
            {
                "ok": True,
                "uid": uid,
                "score": new,
                "level": self.effective_level(uid),
                "is_commander": self._is_commander(uid),
            }
        )

    async def api_score_delete(self):
        payload = await request.json(default={})
        uid = str(payload.get("uid", "")).strip()
        if not uid:
            return error_response("missing uid", status_code=400)
        with self._lock:
            self._scores.pop(uid, None)
            self._persist_scores()
        return json_response({"ok": True})
