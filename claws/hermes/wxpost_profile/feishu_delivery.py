from __future__ import annotations

import asyncio
import json
import math
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from gateway.session_context import get_session_env
from wxpost_controller.core import InvalidRequest, WorkspaceError, error_response
from wxpost_controller.feishu_navigation import FeishuNavigation

from .navigation_tools import feishu_context


def delivery_context() -> tuple[str, str | None]:
    chat_id = get_session_env("HERMES_SESSION_CHAT_ID")
    if not chat_id:
        raise RuntimeError("the current Feishu conversation has no chat ID")
    return chat_id, get_session_env("HERMES_SESSION_THREAD_ID") or None


def feishu_delivery() -> tuple[Any, Any]:
    from gateway.config import Platform, load_gateway_config
    from gateway.platform_registry import platform_registry
    from hermes_cli.plugins import discover_plugins

    discover_plugins()
    entry = platform_registry.get("feishu")
    if entry is None or entry.standalone_sender_fn is None:
        raise RuntimeError("Feishu delivery is unavailable")
    platform_config = load_gateway_config().platforms.get(Platform.FEISHU)
    if platform_config is None:
        raise RuntimeError("Feishu delivery is not configured")
    return entry.standalone_sender_fn, platform_config


async def send_draft_preview_link(args: dict[str, Any], **_kwargs: Any) -> str:
    scope_key, _message_id, _user_id, _user_name = feishu_context()
    chat_id, thread_id = delivery_context()
    preview = FeishuNavigation().create_draft_preview_link(
        scope_key,
        draft_version=(
            int(args["draft_version"])
            if args.get("draft_version") is not None
            else None
        ),
    )
    sender, platform_config = feishu_delivery()
    delivered = await sender(
        platform_config,
        chat_id,
        (
            f"Draft v{preview['draftVersion']}：\n"
            f"[临时预览]({preview['previewUrl']}) · "
            f"[登录后继续编辑]({preview['editorUrl']})\n"
            "提醒：网页登录后的 Draft Assistant 使用独立的 Web session，"
            "不会继承当前飞书对话；两边仍操作同一个 workspace 和 Draft。"
        ),
        thread_id=thread_id,
    )
    if isinstance(delivered, dict) and delivered.get("error"):
        raise RuntimeError(str(delivered["error"]))
    return json.dumps(
        {
            "workspaceId": preview["workspaceId"],
            "draftVersion": preview["draftVersion"],
            "sent": True,
            "delivered": ["temporaryPreview", "draftEditor"],
        },
        ensure_ascii=False,
    )


async def send_web_editor_link(args: dict[str, Any], **_kwargs: Any) -> str:
    scope_key, _message_id, _user_id, _user_name = feishu_context()
    chat_id, thread_id = delivery_context()
    raw_target = args.get("target")
    if raw_target not in {"materials", "draft"}:
        raise InvalidRequest("target must be materials or draft")
    target: Literal["materials", "draft"] = raw_target
    link = FeishuNavigation().get_web_editor_link(scope_key, target=target)
    if target == "materials":
        message = f"[在网页编辑素材]({link['url']})"
    else:
        message = (
            f"[在网页编辑 Draft]({link['url']})\n"
            "提醒：网页登录后的 Draft Assistant 使用独立的 Web session，"
            "不会继承当前飞书对话；两边仍操作同一个 workspace 和 Draft。"
        )
    sender, platform_config = feishu_delivery()
    delivered = await sender(
        platform_config,
        chat_id,
        message,
        thread_id=thread_id,
    )
    if isinstance(delivered, dict) and delivered.get("error"):
        raise RuntimeError(str(delivered["error"]))
    return json.dumps(
        {
            "workspaceId": link["workspaceId"],
            "target": target,
            "sent": True,
        },
        ensure_ascii=False,
    )


def material_caption(material: dict[str, Any]) -> str:
    states = ["Candidate" if material["candidate"] else "Imported"]
    if material["imported"]:
        states.append("Included" if material["included"] else "Excluded")
    if material["usedInDraft"]:
        states.append("In Draft")
    if material["usedAsCover"]:
        states.append("Cover")
    description = material.get("description") or "No description"
    return "\n".join(
        [
            f"{material['id']} · {' · '.join(states)}",
            material["filename"],
            f"Description: {description}",
        ]
    )


async def show_material_library(_args: dict[str, Any], **_kwargs: Any) -> str:
    try:
        scope_key, _message_id, _user_id, _user_name = feishu_context()
        chat_id, thread_id = delivery_context()
        result = FeishuNavigation().get_material_library(scope_key)
        report = result["report"]
        report_by_id = {item["id"]: item for item in report["materials"]}
        sender, platform_config = feishu_delivery()

        with tempfile.TemporaryDirectory(prefix="wxpost-feishu-materials-") as temp:
            temporary = Path(temp)
            for index, media in enumerate(result["media"]):
                source_id = media["source"]["id"]
                material = report_by_id[source_id]
                suffix = Path(media["filename"]).suffix
                if not suffix:
                    suffix = mimetypes.guess_extension(media["mimeType"]) or ".bin"
                item_directory = temporary / f"{index:03d}-{source_id}"
                item_directory.mkdir()
                filename = Path(media["filename"]).name
                media_path = item_directory / (filename or f"{source_id}{suffix}")
                media_path.write_bytes(media["data"])
                delivered = await sender(
                    platform_config,
                    chat_id,
                    material_caption(material),
                    media_files=[(str(media_path), False)],
                    thread_id=thread_id,
                )
                if isinstance(delivered, dict) and delivered.get("error"):
                    if material["kind"] != "video":
                        raise RuntimeError(str(delivered["error"]))
                    fallback_path = item_directory / f"{media_path.name}.bin"
                    fallback_path.write_bytes(media["data"])
                    delivered = await sender(
                        platform_config,
                        chat_id,
                        material_caption(material)
                        + "\nNative video preview was unavailable; the original file is attached.",
                        media_files=[(str(fallback_path), False)],
                        thread_id=thread_id,
                    )
                    if isinstance(delivered, dict) and delivered.get("error"):
                        raise RuntimeError(str(delivered["error"]))

        return json.dumps(
            {
                "workspaceId": result["workspaceId"],
                "displayed": report["counts"]["total"],
                "candidates": report["counts"]["candidates"],
                "imported": report["counts"]["imported"],
            },
            ensure_ascii=False,
        )
    except WorkspaceError as exc:
        raise RuntimeError(json.dumps(error_response(exc), ensure_ascii=False)) from exc


def browser_preview_url(preview_url: str) -> str:
    override = os.environ.get("WXPOST_PREVIEW_BROWSER_BASE_URL", "").rstrip("/")
    if not override:
        return preview_url
    source = urlsplit(preview_url)
    target = urlsplit(override)
    if not target.scheme or not target.netloc:
        raise RuntimeError("WXPOST_PREVIEW_BROWSER_BASE_URL must be an absolute URL")
    return urlunsplit((target.scheme, target.netloc, source.path, source.query, ""))


async def run_browser(*args: str, timeout: int = 120) -> str:
    executable = os.environ.get(
        "WXPOST_AGENT_BROWSER_BIN",
        "/opt/hermes/node_modules/.bin/agent-browser",
    )
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError("Draft preview rendering timed out") from None
    if process.returncode != 0:
        detail = (stderr or stdout).decode(errors="replace").strip()
        raise RuntimeError(detail or "Draft preview rendering failed")
    return stdout.decode(errors="replace").strip()


def resolve_chromium_path() -> str:
    override = os.environ.get("WXPOST_CHROMIUM_PATH")
    if override:
        return override

    browser_root = Path(
        os.environ.get(
            "WXPOST_PLAYWRIGHT_BROWSERS_PATH",
            "/opt/hermes/.playwright",
        )
    )
    candidates = sorted(
        (
            *browser_root.glob(
                "chromium_headless_shell-*/"
                "chrome-headless-shell-linux64/chrome-headless-shell"
            ),
            *browser_root.glob("chromium_headless_shell-*/chrome-linux/headless_shell"),
        ),
        reverse=True,
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError(
        "Draft preview rendering requires an installed Chromium headless shell; "
        "set WXPOST_CHROMIUM_PATH when it is outside Hermes' Playwright cache"
    )


async def capture_full_page(preview_url: str, destination: Path) -> None:
    session = f"wxpost-preview-{uuid4().hex}"
    browser_path = resolve_chromium_path()
    try:
        await run_browser(
            "--session",
            session,
            "--executable-path",
            browser_path,
            "open",
            browser_preview_url(preview_url),
        )
        await run_browser("--session", session, "set", "viewport", "390", "844")
        await run_browser("--session", session, "wait", "--load", "networkidle")
        await run_browser(
            "--session",
            session,
            "eval",
            """(() => {
              const style = document.createElement("style");
              style.dataset.wxpostPreviewCapture = "true";
              style.textContent =
                "html { scrollbar-width: none !important; } " +
                "html::-webkit-scrollbar { display: none !important; }";
              document.head.appendChild(style);
            })()""",
        )
        box_payload = await run_browser(
            "--session",
            session,
            "--json",
            "get",
            "box",
            '[data-testid="wxpost-article"]',
        )
        await run_browser(
            "--session",
            session,
            "screenshot",
            "--full",
            str(destination),
        )
        try:
            box = json.loads(box_payload)["data"]
            left = math.ceil(float(box["x"]))
            top = math.ceil(float(box["y"]))
            right = math.floor(float(box["x"]) + float(box["width"]))
            bottom = math.floor(float(box["y"]) + float(box["height"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Draft preview returned an invalid article boundary"
            ) from exc
        from PIL import Image

        with Image.open(destination) as page:
            page.crop((left, top, right, bottom)).save(destination, format="PNG")
    finally:
        try:
            await run_browser("--session", session, "close", timeout=15)
        except RuntimeError:
            pass


def compress_preview_image(source: Path, destination: Path) -> None:
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGB")
        if image.width > 1000:
            height = round(image.height * 1000 / image.width)
            image = image.resize((1000, height), Image.Resampling.LANCZOS)
        image.save(destination, format="JPEG", quality=84, optimize=True)


async def send_draft_preview_image(args: dict[str, Any], **_kwargs: Any) -> str:
    scope_key, _message_id, _user_id, _user_name = feishu_context()
    chat_id, thread_id = delivery_context()
    preview = FeishuNavigation().create_draft_preview_link(
        scope_key,
        draft_version=(
            int(args["draft_version"])
            if args.get("draft_version") is not None
            else None
        ),
    )
    sender, platform_config = feishu_delivery()

    with tempfile.TemporaryDirectory(prefix="wxpost-draft-preview-") as temp:
        directory = Path(temp)
        screenshot = directory / "draft.png"
        compressed = directory / f"draft-v{preview['draftVersion']}.jpg"
        await capture_full_page(preview["previewUrl"], screenshot)
        await asyncio.to_thread(compress_preview_image, screenshot, compressed)
        delivered = await sender(
            platform_config,
            chat_id,
            f"Draft v{preview['draftVersion']} · Full-page preview",
            media_files=[(str(compressed), False)],
            thread_id=thread_id,
        )
        if isinstance(delivered, dict) and delivered.get("error"):
            raise RuntimeError(str(delivered["error"]))

    return json.dumps(
        {
            "workspaceId": preview["workspaceId"],
            "draftVersion": preview["draftVersion"],
            "sent": True,
        },
        ensure_ascii=False,
    )
