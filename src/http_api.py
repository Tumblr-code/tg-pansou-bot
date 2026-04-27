"""
轻量 HTTP API 入口

提供给 webhook、站点页面或其他服务复用搜索能力。
"""
from __future__ import annotations

from json import JSONDecodeError
from typing import Any, Optional

from aiohttp import web
from structlog import get_logger

from config import settings
from pansou_client import pansou_client, CLOUD_TYPE_NAMES, CLOUD_TYPE_ICONS

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


async def _close_client(app: web.Application) -> None:
    await pansou_client.close()


def create_app() -> web.Application:
    app = web.Application(middlewares=[_cors_middleware])
    app.router.add_get("/", index_handler)
    app.router.add_get("/healthz", health_handler)
    app.router.add_get("/api/pansou/search", search_handler)
    app.router.add_post("/api/pansou/search", search_handler)
    app.router.add_options("/api/pansou/search", search_handler)
    app.on_cleanup.append(_close_client)
    return app
