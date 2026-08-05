from __future__ import annotations

from typing import Any

from wxpost_profile import feishu_delivery, hermes_hooks, navigation_tools


SCHEMAS = navigation_tools.SCHEMAS
CURRENT_SCHEMAS = navigation_tools.CURRENT_SCHEMAS
TOOLSET = navigation_tools.TOOLSET
CURRENT_TOOLSET = navigation_tools.CURRENT_TOOLSET


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", hermes_hooks.prepare_feishu_event)
    ctx.register_hook("pre_tool_call", hermes_hooks.guard_feishu_writes)
    ctx.register_hook("on_session_reset", hermes_hooks.retire_reset_feishu_session)
    for name, schema in SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=(
                feishu_delivery.show_material_library
                if name == "wxpost_show_material_library"
                else feishu_delivery.send_draft_preview_link
                if name == "wxpost_get_draft_preview"
                else feishu_delivery.send_web_editor_link
                if name == "wxpost_send_web_editor_link"
                else feishu_delivery.send_draft_preview_image
                if name == "wxpost_send_draft_preview_image"
                else navigation_tools.async_navigation_handler(name)
                if name == "wxpost_describe_material"
                else navigation_tools.navigation_handler(name)
            ),
            is_async=name
            in {
                "wxpost_show_material_library",
                "wxpost_describe_material",
                "wxpost_get_draft_preview",
                "wxpost_send_web_editor_link",
                "wxpost_send_draft_preview_image",
            },
            emoji="📝",
        )
    for name, schema in CURRENT_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset=CURRENT_TOOLSET,
            schema=schema,
            handler=navigation_tools.current_handler(name),
            emoji="📝",
        )
