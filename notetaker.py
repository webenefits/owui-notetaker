"""
title: Notetaker
description: Save chats to notes, optional metadata valves
author: @chriscstewart & copilot
version: 0.2.0
author_url: https://github.com/chriscstewart
required_open_webui_version: 0.8.0
licence: Unlicense
fork_of: https://openwebui.com/posts/save_to_notes_21bbd23d
icon_url: https://img.icons8.com/?size=100&id=5BLkzYuqO682&format=png&color=777777
"""

from pydantic import BaseModel, Field
from typing import List
from open_webui.models.users import Users
from open_webui.models.notes import Note
from open_webui.models.chats import Chat
from datetime import datetime
import time
import markdown
import re
import html
from open_webui.internal.db import get_db
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# NEWLINE CONSTANTS (TRIPLE‑QUOTED, NEVER ESCAPED)
# ---------------------------------------------------------
DIVIDER = """\n\n---\n\n"""
DOUBLE_NL = """\n\n"""
SINGLE_NL = """\n"""


# ---------------------------------------------------------
# CLEANING UTILITIES — STRIP ALL CHAIN‑OF‑THOUGHT FORMATS
# ---------------------------------------------------------
def clean_assistant_message(raw: str) -> str:
    if not raw:
        return ""

    # 1. Remove <details>...</details> blocks
    raw = re.sub(r"<details[\s\S]*?</details>", "", raw, flags=re.IGNORECASE)

    # 2. Remove <think>...</think> blocks
    raw = re.sub(r"<think[\s\S]*?</think>", "", raw, flags=re.IGNORECASE)

    # 3. Remove <assistant_thought>...</assistant_thought> blocks
    raw = re.sub(r"<assistant_thought[\s\S]*?</assistant_thought>", "", raw, flags=re.IGNORECASE)

    # 4. Remove <model_thinking>...</model_thinking> blocks
    raw = re.sub(r"<model_thinking[\s\S]*?</model_thinking>", "", raw, flags=re.IGNORECASE)

    # 5. Remove plain‑text "Thought for X seconds …" blocks
    raw = re.sub(
        r"Thought for .*?seconds[\s\S]*?(?=\n\S|\Z)",
        "",
        raw,
        flags=re.IGNORECASE
    )

    # 6. Remove "Reasoning:" or "Thinking:" paragraphs
    raw = re.sub(
        r"(Reasoning:|Thinking:)[\s\S]*?(?=\n\S|\Z)",
        "",
        raw,
        flags=re.IGNORECASE
    )

    # 7. Remove any HTML tags
    raw = re.sub(r"<[^>]+>", "", raw)

    # 8. Decode HTML entities
    raw = html.unescape(raw)

    return raw.strip()


# ---------------------------------------------------------
# TIMESTAMP
# ---------------------------------------------------------
def format_timestamp() -> str:
    return datetime.now(ZoneInfo("Australia/Melbourne")).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------
# RENDER ENTRY
# ---------------------------------------------------------
def render_entry(context: dict) -> str:
    ts = context.get("timestamp", "")
    assistant = context.get("assistant", "")
    user_text = context.get("user_text", "")
    user_name = context.get("user_name", "")
    model = context.get("model", "")

    include_user = context.get("include_user", False)
    include_model = context.get("include_model", True)
    include_timestamp = context.get("include_timestamp", True)
    include_prompt = context.get("include_prompt", False)

    header_lines = []

    if include_timestamp and ts:
        header_lines.append(f"**Created:** {ts}")

    if include_model and model:
        header_lines.append(f"**Model:** {model}")

    if include_user and user_name:
        header_lines.append(f"**User:** {user_name}")

    if include_prompt and user_text:
        header_lines.append(f"**Prompt:** {user_text}")

    header_block = SINGLE_NL.join(header_lines) + DIVIDER
    return header_block + assistant


# ---------------------------------------------------------
# ACTION CLASS
# ---------------------------------------------------------
class Action:
    class Valves(BaseModel):
        include_user: bool = False
        include_prompt: bool = False
        include_timestamp: bool = True
        include_model: bool = True
        include_tags_header: bool = True

        default_public: bool = False
        default_access_list: List[str] = Field(
            default_factory=list,
            description="Enter user IDs separated by commas"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def action(
        self,
        body: dict,
        __user__=None,
        __event_emitter__=None,
        __event_call__=None,
    ):
        try:
            conversation_id = body.get("chat_id") or body.get("id")
            if conversation_id is None:
                return

            # FIX: Users.get_user_by_id() is async since OpenWebUI migrated to async DB
            user_dict = __user__[0] if isinstance(__user__, tuple) else __user__
            user = await Users.get_user_by_id(user_dict["id"])
            user_id = user.id
            user_name = getattr(user, "name", "") or getattr(user, "username", "")

            # Messages
            messages = body.get("messages", [])
            raw_assistant = next(
                (m["content"] for m in reversed(messages) if m["role"] == "assistant"),
                ""
            )

            # Safety: some models return dicts
            if isinstance(raw_assistant, dict):
                raw_assistant = raw_assistant.get("content", "") or ""

            assistant_clean = clean_assistant_message(raw_assistant)

            raw_user_msg = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                ""
            )

            model_name = body.get("model", "")

            # FIX: fetch chat once and reuse for both tags and title
            with get_db() as db:
                chat = db.query(Chat).filter(Chat.id == conversation_id).first()

            chat_tags = []
            chat_name = "Note"
            if chat:
                if isinstance(chat.meta, dict) and "tags" in chat.meta:
                    chat_tags = chat.meta.get("tags") or []
                elif hasattr(chat, "tags"):
                    chat_tags = chat.tags or []
                if chat.title:
                    chat_name = chat.title

            if self.valves.include_tags_header:
                tag_header_md = (
                    f"**Tags:** {', '.join(chat_tags)}"
                    if chat_tags
                    else "**Tags:** (none)"
                )
            else:
                tag_header_md = ""

            timestamp_str = format_timestamp() if self.valves.include_timestamp else ""

            entry_md = render_entry({
                "timestamp": timestamp_str,
                "assistant": assistant_clean,
                "user_text": raw_user_msg,
                "user_name": user_name,
                "model": model_name,
                "include_user": self.valves.include_user,
                "include_model": self.valves.include_model,
                "include_timestamp": self.valves.include_timestamp,
                "include_prompt": self.valves.include_prompt,
            })

            # Save note
            with get_db() as db:
                existing_note = (
                    db.query(Note)
                    .filter(
                        Note.user_id == user_id,
                        func.json_extract(Note.meta, "$.conversation_id") == conversation_id,
                    )
                    .first()
                )

                timestamp_ns = int(time.time() * 1_000_000_000)

                if existing_note:
                    current_md = existing_note.data.get("content", {}).get("md", "")

                    if tag_header_md and not current_md.startswith("**Tags:**"):
                        current_md = f"{tag_header_md}{DOUBLE_NL}{current_md}"

                    updated_md = (
                        f"{current_md}{DIVIDER}{entry_md}"
                        if current_md.strip()
                        else entry_md
                    )

                    updated_html = markdown.markdown(
                        updated_md,
                        extensions=["tables", "fenced_code", "nl2br"]
                    )

                    existing_note.data = {
                        "content": {
                            "md": updated_md,
                            "html": updated_html,
                            "json": None
                        }
                    }
                    flag_modified(existing_note, "data")

                    meta = existing_note.meta or {}
                    meta["conversation_id"] = conversation_id
                    meta["tags"] = chat_tags
                    existing_note.meta = meta
                    flag_modified(existing_note, "meta")

                    existing_note.updated_at = timestamp_ns
                    existing_note.title = existing_note.title + " "

                    db.commit()

                else:
                    md_with_header = (
                        f"{tag_header_md}{DOUBLE_NL}{entry_md}"
                        if tag_header_md
                        else entry_md
                    )

                    html_content = markdown.markdown(
                        md_with_header,
                        extensions=["tables", "fenced_code", "nl2br"]
                    )

                    new_note = Note(
                        id=conversation_id,
                        user_id=user_id,
                        title=f"{chat_name} - {datetime.now(ZoneInfo('America/Vancouver')).strftime('%Y-%m-%d %H:%M:%S')}",
                        data={
                            "content": {
                                "md": md_with_header,
                                "html": html_content,
                                "json": None
                            }
                        },
                        meta={
                            "conversation_id": conversation_id,
                            "tags": chat_tags,
                        },
                        created_at=timestamp_ns,
                        updated_at=timestamp_ns,
                    )

                    if hasattr(new_note, "is_public"):
                        new_note.is_public = self.valves.default_public
                    if hasattr(new_note, "access_control"):
                        new_note.access_control = self.valves.default_access_list

                    db.add(new_note)
                    db.commit()

            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": "Note updated", "done": True}
                })

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Notetaker error: {e}", "done": True}
                })
