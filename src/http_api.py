"""
轻量 HTTP API 入口

提供给 webhook、企业微信客服适配层或其他服务复用搜索能力。
"""
from __future__ import annotations

import asyncio
from json import JSONDecodeError
from typing import Any, Optional

from aiohttp import web
from structlog import get_logger

from config import settings
from pansou_client import pansou_client, CLOUD_TYPE_NAMES, CLOUD_TYPE_ICONS
from wecom_service import wecom_client

logger = get_logger()


def _json_response(payload: dict[str, Any], status: int = 200) -> web.Response:
    """统一 JSON 响应并补充基础 CORS 头。"""
    response = web.json_response(payload, status=status)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-API-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_string_list(value: Any) -> Optional[list[str]]:
    if value is None or value == "":
        return None

    if isinstance(value, list):
        normalized = [_normalize_string(item) for item in value]
    else:
        normalized = [_normalize_string(item) for item in str(value).split(",")]

    cleaned = [item for item in normalized if item]
    return cleaned or None


def _normalize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return settings.default_result_limit

    return max(1, min(limit, settings.max_result_limit))


def _extract_filter_config(data: dict[str, Any]) -> Optional[dict[str, list[str]]]:
    raw_filter = data.get("filter")
    include = None
    exclude = None

    if isinstance(raw_filter, dict):
        include = _normalize_string_list(raw_filter.get("include"))
        exclude = _normalize_string_list(raw_filter.get("exclude"))

    include = include or _normalize_string_list(data.get("include"))
    exclude = exclude or _normalize_string_list(data.get("exclude"))

    if not include and not exclude:
        return None

    return {
        "include": include or [],
        "exclude": exclude or [],
    }


def _flatten_results(
    results: dict[str, Any],
    item_limit: Optional[int] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    merged_by_type = results.get("merged_by_type", {})
    for cloud_type, links in merged_by_type.items():
        cloud_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
        icon = CLOUD_TYPE_ICONS.get(cloud_type, "📁")
        count = len(links)

        summary.append(
            {
                "cloud_type": cloud_type,
                "cloud_name": cloud_name,
                "icon": icon,
                "count": count,
            }
        )

        for link in links:
            if item_limit is not None and len(items) >= item_limit:
                continue

            items.append(
                {
                    "cloud_type": cloud_type,
                    "cloud_name": cloud_name,
                    "icon": icon,
                    "note": _normalize_string(link.get("note")),
                    "url": _normalize_string(link.get("url")),
                    "password": _normalize_string(link.get("password")),
                    "source": _normalize_string(link.get("source")),
                }
            )

    return summary, items


def _is_authorized(request: web.Request) -> bool:
    expected_token = settings.http_api_token
    if not expected_token:
        return not settings.require_http_api_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip() == expected_token

    token = request.headers.get("X-API-Token", "").strip()
    return token == expected_token


async def _read_request_data(request: web.Request) -> dict[str, Any]:
    if request.method == "GET":
        return dict(request.query)

    if request.method == "OPTIONS":
        return {}

    if request.content_type.startswith("application/json"):
        try:
            data = await request.json()
        except JSONDecodeError as exc:
            raise web.HTTPBadRequest(text="JSON 格式错误") from exc

        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="请求体必须是 JSON 对象")
        return data

    if request.can_read_body:
        post_data = await request.post()
        return dict(post_data)

    return {}


@web.middleware
async def _cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return _json_response({"ok": True})
    return await handler(request)


async def index_handler(_: web.Request) -> web.Response:
    return _json_response(
        {
            "ok": True,
            "service": "tg-pansou-bot-http-api",
            "search_endpoint": "/api/pansou/search",
            "health_endpoint": "/healthz",
        }
    )


async def health_handler(_: web.Request) -> web.Response:
    upstream_ok = await pansou_client.health_check()
    status = 200 if upstream_ok else 503
    return _json_response(
        {
            "ok": upstream_ok,
            "service": "tg-pansou-bot-http-api",
            "upstream": {
                "pansou_api": upstream_ok,
                "url": settings.pansou_api_url,
            },
            "wecom": {
                "api_configured": wecom_client.has_api_credentials(),
                "callback_configured": wecom_client.has_callback_credentials(),
            },
        },
        status=status,
    )


async def search_handler(request: web.Request) -> web.Response:
    if not _is_authorized(request):
        return _json_response({"ok": False, "error": "unauthorized"}, status=401)

    data = await _read_request_data(request)
    keyword = _normalize_string(data.get("kw") or data.get("keyword") or data.get("q"))
    if not keyword:
        return _json_response({"ok": False, "error": "keyword is required"}, status=400)

    limit = _normalize_limit(data.get("limit"))
    channels = _normalize_string_list(data.get("channels"))
    plugins = _normalize_string_list(data.get("plugins"))
    cloud_types = _normalize_string_list(data.get("cloud_types"))
    source_type = _normalize_string(data.get("src") or data.get("source_type")) or None
    filter_config = _extract_filter_config(data)

    logger.info(
        "http_api_search",
        keyword=keyword,
        limit=limit,
        channels=channels,
        plugins=plugins,
        cloud_types=cloud_types,
        source_type=source_type,
        remote=request.remote,
    )

    results = await pansou_client.search(
        keyword=keyword,
        channels=channels,
        plugins=plugins,
        cloud_types=cloud_types,
        source_type=source_type,
        filter_config=filter_config,
        limit=limit,
    )

    if "error" in results:
        return _json_response(
            {
                "ok": False,
                "keyword": keyword,
                "error": results["error"],
            },
            status=502,
        )

    summary, items = _flatten_results(results, item_limit=limit)
    return _json_response(
        {
            "ok": True,
            "keyword": keyword,
            "limit": limit,
            "total": results.get("total", 0),
            "returned_items": len(items),
            "summary": summary,
            "items": items,
        }
    )


def _track_background_task(app: web.Application, coro) -> None:
    task = asyncio.create_task(coro)
    tasks: set[asyncio.Task] = app["background_tasks"]
    tasks.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        tasks.discard(done_task)
        if done_task.cancelled():
            return

        exc = done_task.exception()
        if exc:
            logger.exception("http_api_background_task_failed", error=str(exc))

    task.add_done_callback(_on_done)


async def wecom_accounts_handler(request: web.Request) -> web.Response:
    if not _is_authorized(request):
        return _json_response({"ok": False, "error": "unauthorized"}, status=401)

    if not wecom_client.has_api_credentials():
        return _json_response({"ok": False, "error": "wecom api not configured"}, status=503)

    try:
        accounts = await wecom_client.list_accounts()
    except Exception as exc:
        logger.exception("wecom_accounts_failed", error=str(exc))
        return _json_response({"ok": False, "error": str(exc)}, status=502)

    return _json_response(
        {
            "ok": True,
            "default_open_kfid": settings.wecom_open_kfid,
            "count": len(accounts),
            "accounts": accounts,
        }
    )


async def wecom_callback_handler(request: web.Request) -> web.Response:
    if request.method == "GET":
        if not wecom_client.has_callback_credentials():
            return web.Response(status=503, text="wecom callback not configured", content_type="text/plain")

        try:
            plaintext = wecom_client.verify_and_decrypt_echostr(
                msg_signature=_normalize_string(request.query.get("msg_signature")),
                timestamp=_normalize_string(request.query.get("timestamp")),
                nonce=_normalize_string(request.query.get("nonce")),
                echostr=_normalize_string(request.query.get("echostr")),
            )
        except Exception as exc:
            logger.exception("wecom_callback_verify_failed", error=str(exc))
            return web.Response(status=400, text="invalid callback request", content_type="text/plain")

        return web.Response(text=plaintext, content_type="text/plain")

    if not wecom_client.has_callback_credentials():
        return web.Response(status=503, text="wecom callback not configured", content_type="text/plain")

    try:
        body_text = await request.text()
        envelope = wecom_client.parse_callback_envelope(body_text)
        callback_payload = wecom_client.verify_and_decrypt_callback(
            msg_signature=_normalize_string(request.query.get("msg_signature")),
            timestamp=_normalize_string(request.query.get("timestamp")),
            nonce=_normalize_string(request.query.get("nonce")),
            encrypted=_normalize_string(envelope.get("Encrypt")),
        )
    except Exception as exc:
        logger.exception("wecom_callback_decrypt_failed", error=str(exc))
        return web.Response(status=400, text="invalid callback request", content_type="text/plain")

    _track_background_task(request.app, wecom_client.handle_callback(callback_payload))
    return web.Response(text="success", content_type="text/plain")


async def _close_client(app: web.Application) -> None:
    tasks = list(app["background_tasks"]) if "background_tasks" in app else []
    for task in tasks:
        task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    await wecom_client.close()
    await pansou_client.close()


def create_app() -> web.Application:
    app = web.Application(middlewares=[_cors_middleware])
    app["background_tasks"] = set()
    app.router.add_get("/", index_handler)
    app.router.add_get("/healthz", health_handler)
    app.router.add_get("/api/pansou/search", search_handler)
    app.router.add_post("/api/pansou/search", search_handler)
    app.router.add_options("/api/pansou/search", search_handler)
    app.router.add_get("/api/wecom/accounts", wecom_accounts_handler)
    app.router.add_get("/wecom/callback", wecom_callback_handler)
    app.router.add_post("/wecom/callback", wecom_callback_handler)
    app.on_cleanup.append(_close_client)
    return app
