import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yt_dlp

from app.enmus.note_enums import DownloadQuality
from app.gpt.gpt_factory import GPTFactory
from app.models.model_config import ModelConfig
from app.services.note import NoteGenerator
from app.services.provider import ProviderService
from app.utils.logger import get_logger

logger = get_logger(__name__)

SUBSCRIPTION_DATA_FILE = Path(os.getenv("SUBSCRIPTION_DATA_FILE", "backend/data/subscriptions.json"))
NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))


class SubscriptionService:
    def __init__(self):
        SUBSCRIPTION_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- public API ----------
    def pull_latest_note(
        self,
        channel_url: str,
        model_name: str,
        provider_id: str,
        quality: DownloadQuality,
        style: Optional[str] = None,
        extras: Optional[str] = None,
    ) -> Dict[str, Any]:
        channel = self._upsert_channel(channel_url)
        entries = self._fetch_channel_entries(channel_url, limit=1)
        if not entries:
            return {"status": "empty", "message": "未获取到频道视频", "channel": channel}

        latest = entries[0]
        last_video_id = channel.get("last_video_id")
        if last_video_id == latest["video_id"]:
            return {"status": "no_update", "message": "暂无新视频", "channel": channel}

        note_result = self._generate_note_for_video(
            video_url=latest["video_url"],
            model_name=model_name,
            provider_id=provider_id,
            quality=quality,
            style=style,
            extras=extras,
        )

        channel["last_video_id"] = latest["video_id"]
        channel["last_checked_at"] = self._now_iso()
        channel["history"].append(
            {
                "task_id": note_result["task_id"],
                "video_id": latest["video_id"],
                "video_title": latest["title"],
                "video_url": latest["video_url"],
                "upload_date": latest.get("upload_date"),
                "generated_at": self._now_iso(),
            }
        )
        self._save_channel(channel)

        return {
            "status": "success",
            "message": "已抓取最新视频并生成笔记",
            "channel": channel,
            "video": latest,
            "task": note_result,
        }

    def fetch_recent_notes(
        self,
        channel_url: str,
        count: int,
        model_name: str,
        provider_id: str,
        quality: DownloadQuality,
        style: Optional[str] = None,
        extras: Optional[str] = None,
    ) -> Dict[str, Any]:
        channel = self._upsert_channel(channel_url)
        entries = self._fetch_channel_entries(channel_url, limit=count)
        if not entries:
            return {"status": "empty", "message": "未获取到频道视频", "channel": channel, "tasks": []}

        history_video_ids = {item.get("video_id") for item in channel.get("history", [])}
        new_tasks: List[Dict[str, Any]] = []
        for entry in entries:
            if entry["video_id"] in history_video_ids:
                continue

            note_result = self._generate_note_for_video(
                video_url=entry["video_url"],
                model_name=model_name,
                provider_id=provider_id,
                quality=quality,
                style=style,
                extras=extras,
            )
            channel["history"].append(
                {
                    "task_id": note_result["task_id"],
                    "video_id": entry["video_id"],
                    "video_title": entry["title"],
                    "video_url": entry["video_url"],
                    "upload_date": entry.get("upload_date"),
                    "generated_at": self._now_iso(),
                }
            )
            history_video_ids.add(entry["video_id"])
            new_tasks.append({"video": entry, "task": note_result})

        channel["last_checked_at"] = self._now_iso()
        if entries:
            channel["last_video_id"] = entries[0]["video_id"]
        self._save_channel(channel)

        message = "抓取完成" if new_tasks else "暂无新视频"
        return {
            "status": "success",
            "message": message,
            "channel": channel,
            "tasks": new_tasks,
            "requested_count": count,
        }

    def merge_and_summarize(
        self,
        start_date: str,
        end_date: str,
        channel_url: Optional[str] = None,
        summarize: bool = True,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        channels = self._load_subscriptions()

        notes = []
        for channel in channels:
            if channel_url and channel.get("channel_url") != channel_url:
                continue
            for item in channel.get("history", []):
                upload_date = self._parse_upload_date(item.get("upload_date"))
                if not upload_date:
                    continue
                if start_dt.date() <= upload_date.date() <= end_dt.date():
                    markdown = self._read_markdown(item.get("task_id"))
                    if markdown:
                        notes.append(
                            {
                                "channel_title": channel.get("channel_title"),
                                "video_title": item.get("video_title"),
                                "video_url": item.get("video_url"),
                                "upload_date": item.get("upload_date"),
                                "markdown": markdown,
                            }
                        )

        if not notes:
            return {"status": "empty", "message": "所选时间范围内暂无可合并的笔记"}

        merged_markdown = self._merge_notes_markdown(notes, start_date, end_date, channel_url)
        ai_summary = None
        if summarize:
            if not model_name or not provider_id:
                raise ValueError("开启总结时必须传入 model_name 和 provider_id")
            ai_summary = self._summarize_markdown(merged_markdown, model_name, provider_id)

        export_name = f"merged_{start_date}_{end_date}_{uuid.uuid4().hex[:8]}.md"
        export_path = NOTE_OUTPUT_DIR / export_name
        export_path.write_text(merged_markdown, encoding="utf-8")

        return {
            "status": "success",
            "message": "合并导出完成",
            "count": len(notes),
            "export_file": str(export_path),
            "summary": ai_summary,
        }

    # ---------- private helpers ----------
    def _generate_note_for_video(
        self,
        video_url: str,
        model_name: str,
        provider_id: str,
        quality: DownloadQuality,
        style: Optional[str],
        extras: Optional[str],
    ) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        note = NoteGenerator().generate(
            video_url=video_url,
            platform="youtube",
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            style=style,
            extras=extras,
            _format=[],
        )
        if not note or not note.markdown:
            raise RuntimeError(f"视频 {video_url} 笔记生成失败")

        with (NOTE_OUTPUT_DIR / f"{task_id}.json").open("w", encoding="utf-8") as fp:
            json.dump(asdict(note), fp, ensure_ascii=False, indent=2)

        return {"task_id": task_id}

    def _fetch_channel_entries(self, channel_url: str, limit: int = 1) -> List[Dict[str, Any]]:
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "playlistend": limit,
            "skip_download": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        entries = info.get("entries") or []
        result = []
        for entry in entries:
            video_id = entry.get("id")
            if not video_id:
                continue
            result.append(
                {
                    "video_id": video_id,
                    "title": entry.get("title") or "未命名视频",
                    "video_url": entry.get("url") if str(entry.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={video_id}",
                    "upload_date": entry.get("upload_date"),
                }
            )
        return result

    def _upsert_channel(self, channel_url: str) -> Dict[str, Any]:
        channels = self._load_subscriptions()
        for channel in channels:
            if channel.get("channel_url") == channel_url:
                return channel

        channel_info = self._fetch_channel_info(channel_url)
        channel = {
            "channel_url": channel_url,
            "channel_id": channel_info.get("channel_id"),
            "channel_title": channel_info.get("channel_title") or channel_url,
            "last_video_id": None,
            "last_checked_at": None,
            "history": [],
        }
        channels.append(channel)
        self._save_subscriptions(channels)
        return channel

    def _save_channel(self, updated: Dict[str, Any]) -> None:
        channels = self._load_subscriptions()
        for idx, channel in enumerate(channels):
            if channel.get("channel_url") == updated.get("channel_url"):
                channels[idx] = updated
                self._save_subscriptions(channels)
                return
        channels.append(updated)
        self._save_subscriptions(channels)

    def _fetch_channel_info(self, channel_url: str) -> Dict[str, Any]:
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(channel_url, download=False)
        return {
            "channel_id": info.get("channel_id") or info.get("id"),
            "channel_title": info.get("channel") or info.get("title"),
        }

    def _load_subscriptions(self) -> List[Dict[str, Any]]:
        if not SUBSCRIPTION_DATA_FILE.exists():
            return []
        with SUBSCRIPTION_DATA_FILE.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def _save_subscriptions(self, payload: List[Dict[str, Any]]) -> None:
        with SUBSCRIPTION_DATA_FILE.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)

    def _read_markdown(self, task_id: Optional[str]) -> Optional[str]:
        if not task_id:
            return None
        note_file = NOTE_OUTPUT_DIR / f"{task_id}.json"
        if not note_file.exists():
            return None
        with note_file.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload.get("markdown")

    def _merge_notes_markdown(
        self,
        notes: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
        channel_url: Optional[str],
    ) -> str:
        header = [
            "# 订阅视频笔记合并导出",
            "",
            f"- 时间范围: {start_date} ~ {end_date}",
            f"- 频道范围: {channel_url or '全部订阅频道'}",
            f"- 合并数量: {len(notes)}",
            "",
            "---",
            "",
        ]

        body: List[str] = []
        for idx, note in enumerate(notes, start=1):
            body.extend(
                [
                    f"## {idx}. {note['video_title']}",
                    f"- 频道: {note['channel_title']}",
                    f"- 上传日期: {note.get('upload_date')}",
                    f"- 链接: {note.get('video_url')}",
                    "",
                    note["markdown"],
                    "",
                    "---",
                    "",
                ]
            )
        return "\n".join(header + body)

    def _summarize_markdown(self, markdown: str, model_name: str, provider_id: str) -> str:
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError("未找到 provider")

        gpt = GPTFactory().from_config(
            ModelConfig(
                api_key=provider["api_key"],
                base_url=provider["base_url"],
                model_name=model_name,
                provider=provider["type"],
                name=provider["name"],
            )
        )

        prompt = (
            "请你对以下合并视频笔记进行二次提炼：\n"
            "1) 给出总览摘要；\n"
            "2) 提取跨视频重复出现的核心观点；\n"
            "3) 列出可执行行动项。\n\n"
            f"笔记内容如下：\n{markdown}"
        )
        return gpt.chat(prompt)

    def _parse_upload_date(self, upload_date: Optional[str]) -> Optional[datetime]:
        if not upload_date:
            return None
        try:
            return datetime.strptime(upload_date, "%Y%m%d")
        except ValueError:
            return None

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat() + "Z"
