"""
Pansou API 客户端 - 优化版
- 单例模式复用 HTTP 客户端
- 连接池优化
- 指数退避重试机制
"""
import asyncio
import html
import re
import time
from collections import OrderedDict
from typing import Optional, List, Dict, Any
import httpx
from structlog import get_logger

from config import settings

logger = get_logger()

CLOUD_TYPE_NAMES = {
    "baidu": "百度网盘",
    "aliyun": "阿里云盘",
    "quark": "夸克网盘",
    "guangya": "光鸭云盘",
    "tianyi": "天翼云盘",
    "uc": "UC网盘",
    "mobile": "移动云盘",
    "115": "115网盘",
    "pikpak": "PikPak",
    "xunlei": "迅雷网盘",
    "123": "123网盘",
    "weiyun": "腾讯微云",
    "lanzou": "蓝奏云",
    "jianguoyun": "坚果云",
    "magnet": "磁力链接",
    "ed2k": "电驴链接",
    "others": "其他",
}

CLOUD_TYPE_ALIASES = {
    "ali": "aliyun",
    "alipan": "aliyun",
    "aliyundrive": "aliyun",
    "aliyunpan": "aliyun",
    "123pan": "123",
    "123yunpan": "123",
    "caiyun": "mobile",
    "139": "mobile",
    "189": "tianyi",
    "tianyiyun": "tianyi",
    "onedrive115": "115",
    "115pan": "115",
    "weiyunpan": "weiyun",
    "lanzous": "lanzou",
    "lanzouyun": "lanzou",
    "lanzoui": "lanzou",
    "jianguo": "jianguoyun",
    "other": "others",
    "unknown": "others",
    "detail": "others",
}

CLOUD_TYPE_ICONS = {
    "baidu": "🔴",
    "aliyun": "🔵",
    "quark": "🟠",
    "guangya": "🟤",
    "tianyi": "🟡",
    "uc": "🟣",
    "mobile": "🟢",
    "115": "⚫",
    "pikpak": "🩷",
    "xunlei": "🔷",
    "123": "🔶",
    "weiyun": "☁️",
    "lanzou": "🧊",
    "jianguoyun": "🥜",
    "magnet": "🧲",
    "ed2k": "📎",
    "others": "📁",
}


class PansouClient:
    """Pansou API 客户端 - 单例模式，复用连接池"""
    
    _instance = None
    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self.base_url = settings.pansou_api_url.rstrip('/')
        self.timeout = settings.search_timeout
        self.headers = {}
        self.result_cache_ttl = 30
        self.result_cache_size = 128
        self.health_cache_ttl = 10
        self.service_info_cache_ttl = 30
        self._result_cache: OrderedDict[str, tuple[float, Dict[str, Any]]] = OrderedDict()
        self._inflight_searches: Dict[str, asyncio.Task] = {}
        self._health_cache_value: Optional[bool] = None
        self._health_cache_expires_at = 0.0
        self._health_check_task: Optional[asyncio.Task] = None
        self._service_info_cache_value: Optional[Dict[str, Any]] = None
        self._service_info_cache_expires_at = 0.0
        self._service_info_task: Optional[asyncio.Task] = None
        if settings.pansou_api_token:
            self.headers["Authorization"] = f"Bearer {settings.pansou_api_token}"
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（单例模式）"""
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    proxy = None
                    proxies = settings.get_proxies()
                    if proxies:
                        proxy = proxies.get('https://') or proxies.get('http://')
                    
                    timeout = httpx.Timeout(
                        connect=5.0,
                        read=30.0,
                        write=10.0,
                        pool=5.0
                    )
                    
                    limits = httpx.Limits(
                        max_keepalive_connections=20,
                        max_connections=50,
                        keepalive_expiry=60.0
                    )
                    
                    self._client = httpx.AsyncClient(
                        timeout=timeout,
                        proxy=proxy,
                        headers=self.headers,
                        limits=limits,
                        http2=True
                    )
        return self._client
    
    async def close(self):
        """关闭客户端连接"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _normalize_list(self, values: Optional[List[str]]) -> tuple[str, ...]:
        """标准化列表参数，提升缓存命中率。"""
        if not values:
            return ()
        return tuple(sorted(str(value).strip() for value in values if str(value).strip()))

    def _normalize_filter(self, filter_config: Optional[dict]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """标准化过滤配置，提升缓存命中率。"""
        if not filter_config:
            return (), ()
        include = self._normalize_list(filter_config.get("include"))
        exclude = self._normalize_list(filter_config.get("exclude"))
        return include, exclude

    @staticmethod
    def _normalize_cloud_type(cloud_type: Any) -> str:
        """归一化上游插件返回的网盘类型，避免同类网盘分散或被筛选漏掉。"""
        text = str(cloud_type or "").strip().lower()
        if not text:
            return "others"
        return CLOUD_TYPE_ALIASES.get(text, text)

    @staticmethod
    def _first_non_empty(data: Dict[str, Any], keys: List[str], default: str = "") -> str:
        """按候选字段顺序提取首个非空字符串值。"""
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return default

    def _normalize_link_item(self, item: Any, cloud_type: Optional[str] = None) -> Dict[str, str]:
        """将不同上游插件/版本的返回字段统一为固定结构。"""
        if not isinstance(item, dict):
            return {
                "url": self._clean_text(item),
                "password": "",
                "note": "",
                "source": "",
                "cloud_type": cloud_type or "others",
            }

        normalized_cloud_type = self._first_non_empty(
            item,
            ["cloud_type", "type", "drive", "pan_type"],
            default=cloud_type or "others",
        )
        return {
            "url": self._first_non_empty(item, ["url", "link", "share_url", "href"]),
            "password": self._first_non_empty(item, ["password", "pwd", "passcode", "extract_code"]),
            "note": self._first_non_empty(item, ["note", "title", "name", "text", "filename"]),
            "source": self._first_non_empty(item, ["source", "channel", "plugin", "from"]),
            "cloud_type": self._normalize_cloud_type(normalized_cloud_type),
        }

    def _normalize_merged_by_type(self, data: Any) -> Dict[str, List[Dict[str, str]]]:
        """兼容不同上游返回结构，归一化为 merged_by_type。"""
        normalized: Dict[str, List[Dict[str, str]]] = {}

        if isinstance(data, dict):
            items = data.items()
        elif isinstance(data, list):
            return self._group_result_items(data)
        else:
            items = []

        for cloud_type, links in items:
            if not isinstance(links, list):
                continue

            normalized_cloud_type = self._normalize_cloud_type(cloud_type)
            normalized_links = []
            for link in links:
                normalized_link = self._normalize_link_item(link, cloud_type=normalized_cloud_type)
                if normalized_link["url"]:
                    normalized_links.append(normalized_link)

            if normalized_links:
                normalized.setdefault(normalized_cloud_type, []).extend(normalized_links)

        return normalized

    def _group_result_items(self, items: Any) -> Dict[str, List[Dict[str, str]]]:
        """兼容直接返回 items/results 数组，以及 results[].links 嵌套结构。"""
        grouped: Dict[str, List[Dict[str, str]]] = {}
        if not isinstance(items, list):
            return grouped

        for item in items:
            if isinstance(item, dict) and isinstance(item.get("links"), list):
                source = item.get("source") or item.get("channel") or item.get("plugin") or ""
                title = item.get("title") or item.get("name") or item.get("content") or ""
                for link in item["links"]:
                    normalized = self._normalize_link_item(link)
                    if not normalized["url"]:
                        continue
                    if not normalized["note"]:
                        normalized["note"] = self._clean_text(title)
                    if not normalized["source"]:
                        normalized["source"] = self._clean_text(source)
                    cloud_type = self._normalize_cloud_type(normalized.get("cloud_type"))
                    normalized["cloud_type"] = cloud_type
                    grouped.setdefault(cloud_type, []).append(normalized)
                continue

            normalized = self._normalize_link_item(item)
            if not normalized["url"]:
                continue
            cloud_type = self._normalize_cloud_type(normalized.get("cloud_type"))
            normalized["cloud_type"] = cloud_type
            grouped.setdefault(cloud_type, []).append(normalized)

        return grouped

    def _normalize_search_result(self, raw_data: Any) -> Dict[str, Any]:
        """兼容不同 pansou 版本的响应包装和字段命名。"""
        if isinstance(raw_data, dict) and raw_data.get("code") not in (None, 0):
            logger.error(
                "search_failed",
                code=raw_data.get("code"),
                message=raw_data.get("message"),
            )
            return {"error": raw_data.get("message", "搜索失败")}

        payload = raw_data.get("data") if isinstance(raw_data, dict) and "data" in raw_data else raw_data
        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            payload = {"items": payload if isinstance(payload, list) else []}

        merged_by_type = self._normalize_merged_by_type(payload.get("merged_by_type"))
        if not merged_by_type:
            merged_by_type = self._normalize_merged_by_type(payload.get("results"))
        if not merged_by_type:
            merged_by_type = self._group_result_items(payload.get("items"))
        if not merged_by_type:
            merged_by_type = self._group_result_items(payload.get("results"))

        total = payload.get("total")
        if total is None:
            total = payload.get("count")
        if total is None:
            total = sum(len(links) for links in merged_by_type.values())

        try:
            total = int(total or 0)
        except (TypeError, ValueError):
            total = sum(len(links) for links in merged_by_type.values())

        return {
            **payload,
            "merged_by_type": merged_by_type,
            "total": total,
        }

    def _make_search_cache_key(
        self,
        keyword: str,
        channels: Optional[List[str]],
        plugins: Optional[List[str]],
        cloud_types: Optional[List[str]],
        source_type: Optional[str],
        filter_config: Optional[dict],
        limit: int,
        force_refresh: bool
    ) -> str:
        """生成搜索缓存键。"""
        include, exclude = self._normalize_filter(filter_config)
        key = (
            keyword.strip(),
            self._normalize_list(channels),
            self._normalize_list(plugins),
            self._normalize_list(cloud_types),
            source_type or "all",
            include,
            exclude,
            limit,
            force_refresh,
        )
        return repr(key)

    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """获取缓存结果。"""
        cached = self._result_cache.get(cache_key)
        if not cached:
            return None

        expires_at, result = cached
        now = time.monotonic()
        if now >= expires_at:
            self._result_cache.pop(cache_key, None)
            return None

        self._result_cache.move_to_end(cache_key)
        return result

    def _store_cached_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """写入缓存结果。"""
        self._result_cache[cache_key] = (time.monotonic() + self.result_cache_ttl, result)
        self._result_cache.move_to_end(cache_key)

        while len(self._result_cache) > self.result_cache_size:
            self._result_cache.popitem(last=False)

    async def _execute_search_request(
        self,
        url: str,
        payload: Dict[str, Any],
        keyword: str,
        filter_config: Optional[dict],
        max_retries: int
    ) -> Dict[str, Any]:
        """执行真实搜索请求。"""
        for attempt in range(max_retries):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                result = self._normalize_search_result(data)
                if "error" in result:
                    return result

                if filter_config and result.get("merged_by_type"):
                    result["merged_by_type"] = self._apply_filter(
                        result["merged_by_type"],
                        filter_config
                    )
                    result["total"] = sum(
                        len(links) for links in result["merged_by_type"].values()
                    )

                return result

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                if attempt < max_retries - 1:
                    wait_time = min(0.5 * (2 ** attempt), 5.0)
                    logger.warning("search_retry", keyword=keyword, attempt=attempt + 1, wait=wait_time, error=str(e))
                    await asyncio.sleep(wait_time)
                    continue

                logger.error("search_failed_after_retries", keyword=keyword, error=str(e))
                if isinstance(e, httpx.TimeoutException):
                    return {"error": "搜索超时，请稍后重试"}
                return {"error": "网络连接失败，请稍后重试"}
            except httpx.HTTPStatusError as e:
                logger.error("search_http_error", status=e.response.status_code, detail=str(e))
                return {"error": f"搜索服务错误: HTTP {e.response.status_code}"}
            except Exception as e:
                logger.error("search_exception", error=str(e))
                return {"error": f"搜索出错: {str(e)}"}

    async def search(
        self,
        keyword: str,
        channels: Optional[List[str]] = None,
        plugins: Optional[List[str]] = None,
        cloud_types: Optional[List[str]] = None,
        source_type: Optional[str] = None,
        filter_config: Optional[dict] = None,
        limit: int = 10,
        force_refresh: bool = False,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        搜索网盘资源（指数退避重试）
        """
        url = f"{self.base_url}/api/search"
        
        payload = {
            "kw": keyword,
            "res": "merge",
            "src": source_type or "all",
            "limit": limit,
        }
        
        if channels:
            payload["channels"] = channels
        if plugins:
            payload["plugins"] = plugins
        if cloud_types:
            payload["cloud_types"] = cloud_types
        if force_refresh:
            payload["refresh"] = True
        if filter_config:
            payload["filter"] = filter_config
        
        cache_key = self._make_search_cache_key(
            keyword=keyword,
            channels=channels,
            plugins=plugins,
            cloud_types=cloud_types,
            source_type=source_type,
            filter_config=filter_config,
            limit=limit,
            force_refresh=force_refresh,
        )

        if not force_refresh:
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                logger.debug("search_cache_hit", keyword=keyword)
                return cached_result

        inflight_task = self._inflight_searches.get(cache_key)
        if inflight_task:
            logger.debug("search_join_inflight", keyword=keyword)
            return await inflight_task

        task = asyncio.create_task(
            self._execute_search_request(
                url=url,
                payload=payload,
                keyword=keyword,
                filter_config=filter_config,
                max_retries=max_retries,
            )
        )
        self._inflight_searches[cache_key] = task

        try:
            result = await task
            if "error" not in result:
                self._store_cached_result(cache_key, result)
            return result
        finally:
            self._inflight_searches.pop(cache_key, None)
    
    def _apply_filter(
        self, 
        merged_by_type: Dict[str, List[dict]], 
        filter_config: dict
    ) -> Dict[str, List[dict]]:
        """应用过滤配置到结果"""
        include_list = filter_config.get("include", [])
        exclude_list = filter_config.get("exclude", [])
        
        if not include_list and not exclude_list:
            return merged_by_type
        
        filtered = {}
        for cloud_type, links in merged_by_type.items():
            filtered_links = []
            for link in links:
                note = link.get("note", "")
                url = link.get("url", "")
                text = f"{note} {url}".lower()
                
                # 检查排除词
                if exclude_list:
                    should_exclude = any(
                        excl.lower() in text for excl in exclude_list
                    )
                    if should_exclude:
                        continue
                
                # 检查包含词
                if include_list:
                    should_include = any(
                        incl.lower() in text for incl in include_list
                    )
                    if not should_include:
                        continue
                
                filtered_links.append(link)
            
            if filtered_links:
                filtered[cloud_type] = filtered_links
        
        return filtered
    
    def clear_runtime_cache(self) -> None:
        """清理搜索和健康检查缓存。"""
        self._result_cache.clear()
        self._health_cache_value = None
        self._health_cache_expires_at = 0.0
        self._service_info_cache_value = None
        self._service_info_cache_expires_at = 0.0

    async def get_service_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        """获取 pansou 健康状态、插件和频道信息。"""
        now = time.monotonic()
        if (
            not force_refresh
            and self._service_info_cache_value is not None
            and now < self._service_info_cache_expires_at
        ):
            return self._service_info_cache_value

        if self._service_info_task:
            return await self._service_info_task

        async def _run_service_info() -> Dict[str, Any]:
            client = await self._get_client()
            try:
                response = await client.get(f"{self.base_url}/api/health", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        data["healthy"] = True
                        return data
            except Exception as exc:
                logger.warning("service_info_failed", error=str(exc))

            for url in (f"{self.base_url}/healthz",):
                for method in ("HEAD", "GET"):
                    try:
                        response = await client.request(method, url, timeout=5)
                        if response.status_code == 200:
                            return {"healthy": True, "status": "ok"}
                    except Exception:
                        continue

            return {"healthy": False, "status": "unavailable"}

        self._service_info_task = asyncio.create_task(_run_service_info())
        try:
            result = await self._service_info_task
            self._service_info_cache_value = result
            self._service_info_cache_expires_at = time.monotonic() + self.service_info_cache_ttl
            healthy = bool(result.get("healthy"))
            self._health_cache_value = healthy
            self._health_cache_expires_at = time.monotonic() + self.health_cache_ttl
            return result
        finally:
            self._service_info_task = None

    async def health_check(self, force_refresh: bool = False) -> bool:
        """检查 pansou 服务是否健康"""
        now = time.monotonic()
        if not force_refresh and self._health_cache_value is not None and now < self._health_cache_expires_at:
            return self._health_cache_value

        if self._health_check_task:
            return await self._health_check_task

        async def _run_health_check() -> bool:
            info = await self.get_service_info(force_refresh=force_refresh)
            return bool(info.get("healthy"))

        self._health_check_task = asyncio.create_task(_run_health_check())
        try:
            result = await self._health_check_task
            self._health_cache_value = result
            self._health_cache_expires_at = time.monotonic() + self.health_cache_ttl
            return result
        finally:
            self._health_check_task = None
    
    def _clean_text(self, text: str) -> str:
        """清理文本，移除可能导致格式问题的字符"""
        if not text:
            return ""
        text = str(text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _escape_html(self, text: Any) -> str:
        """转义 HTML 输出，避免 Telegram HTML 解析报错或被注入。"""
        return html.escape(self._clean_text(text))

    def _format_link_html(self, url: Any, label: str = "打开链接") -> str:
        """把长链接压缩为 Telegram HTML 可点击链接。"""
        clean_url = self._clean_text(url)
        if not clean_url:
            return ""
        escaped_url = html.escape(clean_url, quote=True)
        return f'<a href="{escaped_url}">{self._escape_html(label)}</a>'

    def _format_type_summary(self, merged_by_type: Dict[str, List[Dict[str, str]]], limit: int = 8) -> List[str]:
        """生成网盘类型数量摘要。"""
        items = [
            (cloud_type, len(links))
            for cloud_type, links in merged_by_type.items()
            if links
        ]
        items.sort(key=lambda item: item[1], reverse=True)
        lines = []
        for cloud_type, count in items[:limit]:
            icon = CLOUD_TYPE_ICONS.get(cloud_type, "📁")
            name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
            lines.append(f"{icon} {self._escape_html(name)}: {count}")
        if len(items) > limit:
            lines.append(f"📁 其他类型: {len(items) - limit}")
        return lines
    
    def get_type_buttons(self, results: Dict[str, Any]) -> List[List[Dict]]:
        """
        生成网盘类型按钮配置
        
        Returns:
            按钮配置列表，每个元素是 [text, callback_data]
        """
        merged_by_type = results.get("merged_by_type", {})
        if not merged_by_type:
            return []
        
        buttons = []
        for cloud_type, links in merged_by_type.items():
            if not links:
                continue
            
            icon = CLOUD_TYPE_ICONS.get(cloud_type, "📁")
            name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
            count = len(links)
            
            buttons.append({
                "text": f"{icon} {name} ({count})",
                "type": cloud_type,
                "count": count
            })
        
        # 按数量排序
        buttons.sort(key=lambda x: x["count"], reverse=True)
        return buttons
    
    def format_overview(self, results: Dict[str, Any], keyword: str) -> str:
        """
        格式化搜索结果概览
        
        Args:
            results: API 返回的结果
            keyword: 搜索关键词
        
        Returns:
            概览文本
        """
        if "error" in results:
            return f"❌ 搜索失败: {results['error']}"
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if not merged_by_type or total == 0:
            return f"🔍 未找到与「{self._escape_html(keyword)}」相关的资源"

        lines = [
            f"🔍 搜索结果: {self._escape_html(keyword)}",
            f"📊 共找到 {total} 条结果",
        ]

        summary_lines = self._format_type_summary(merged_by_type)
        if summary_lines:
            lines.extend(["", *summary_lines])

        lines.extend([
            "",
            "👇 请选择网盘类型查看详细资源:"
        ])
        
        return "\n".join(lines)
    
    def format_type_results(
        self, 
        results: Dict[str, Any], 
        keyword: str, 
        cloud_type: str,
        page: int = 1,
        per_page: int = 5
    ) -> str:
        """
        格式化指定网盘类型的结果
        
        Args:
            results: API 返回的结果
            keyword: 搜索关键词
            cloud_type: 网盘类型
            page: 页码
            per_page: 每页数量
        
        Returns:
            格式化后的消息文本
        """
        if "error" in results:
            return f"❌ 搜索失败: {results['error']}"
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if cloud_type not in merged_by_type or not merged_by_type[cloud_type]:
            return f"🔍 该类型下暂无资源"
        
        links = merged_by_type[cloud_type]
        type_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
        icon = CLOUD_TYPE_ICONS.get(cloud_type, "📁")
        
        # 分页
        total_pages = (len(links) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        page_links = links[start:end]
        
        lines = [
            f"{icon} <b>{self._escape_html(type_name)}</b> - {self._escape_html(keyword)}",
            f"📊 共 {len(links)} 条结果 (第{page}/{total_pages}页)\n"
        ]
        
        for i, link in enumerate(page_links, start + 1):
            url = link.get("url", "")
            password = link.get("password", "")
            note = link.get("note", "")
            source = link.get("source", "")
            
            clean_note = self._escape_html(note) if note else "无标题"
            clean_link = self._format_link_html(url)
            clean_source = self._escape_html(source) if source else ""
            clean_password = self._escape_html(password) if password else ""

            lines.append(f"{i}. {clean_note}")
            if clean_link:
                lines.append(f"   🔗 {clean_link}")
            if clean_password:
                lines.append(f"   🔑 密码: <code>{clean_password}</code>")
            if clean_source:
                lines.append(f"   📌 来源: {clean_source}")
            lines.append("")  # 空行分隔
        
        lines.append("─────────────")
        lines.append("💡 提示: 点击“打开链接”访问资源，密码可长按复制")
        
        return "\n".join(lines)
    
    def format_results(self, results: Dict[str, Any], keyword: str, per_type_limit: int = 5) -> str:
        """
        格式化所有搜索结果（备用，显示所有结果）
        """
        if "error" in results:
            return f"❌ 搜索失败: {results['error']}"
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if not merged_by_type or total == 0:
            return f"🔍 未找到与「{self._escape_html(keyword)}」相关的资源"

        lines = [
            f"🔍 搜索结果: {self._escape_html(keyword)}",
            f"📊 共找到 {total} 条结果\n"
        ]
        
        for cloud_type, links in merged_by_type.items():
            if not links:
                continue
            
            type_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
            lines.append(f"\n📁 {type_name} ({len(links)}个)")
            
            for i, link in enumerate(links[:per_type_limit], 1):
                url = link.get("url", "")
                password = link.get("password", "")
                note = link.get("note", "")
                source = link.get("source", "")
                
                clean_note = self._escape_html(note) if note else "无标题"
                clean_link = self._format_link_html(url)
                clean_source = self._escape_html(source) if source else ""
                clean_password = self._escape_html(password) if password else ""

                lines.append(f"\n{i}. {clean_note}")
                if clean_link:
                    lines.append(f"   🔗 {clean_link}")
                if clean_password:
                    lines.append(f"   🔑 密码: <code>{clean_password}</code>")
                if clean_source:
                    lines.append(f"   📌 来源: {clean_source}")
        
        lines.append("\n─────────────")
        lines.append("💡 提示: 长按链接可复制，密码可手动复制")
        
        return "\n".join(lines)


# 全局客户端实例
pansou_client = PansouClient()
