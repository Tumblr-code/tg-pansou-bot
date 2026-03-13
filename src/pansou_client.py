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
from typing import Optional, List, Dict, Any
import httpx
from structlog import get_logger

from config import settings

logger = get_logger()

CLOUD_TYPE_NAMES = {
    "baidu": "百度网盘",
    "aliyun": "阿里云盘",
    "quark": "夸克网盘",
    "tianyi": "天翼云盘",
    "uc": "UC网盘",
    "mobile": "移动云盘",
    "115": "115网盘",
    "pikpak": "PikPak",
    "xunlei": "迅雷网盘",
    "123": "123网盘",
    "magnet": "磁力链接",
    "ed2k": "电驴链接",
    "others": "其他",
}

CLOUD_TYPE_ICONS = {
    "baidu": "🔴",
    "aliyun": "🔵",
    "quark": "🟠",
    "tianyi": "🟡",
    "uc": "🟣",
    "mobile": "🟢",
    "115": "⚫",
    "pikpak": "🩷",
    "xunlei": "🔷",
    "123": "🔶",
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
    
    async def search(
        self,
        keyword: str,
        channels: Optional[List[str]] = None,
        plugins: Optional[List[str]] = None,
        cloud_types: Optional[List[str]] = None,
        source_type: Optional[str] = None,
        filter_config: Optional[dict] = None,
        limit: int = 10,
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
        }
        
        if channels:
            payload["channels"] = channels
        if plugins:
            payload["plugins"] = plugins
        if cloud_types:
            payload["cloud_types"] = cloud_types
        if filter_config:
            payload["filter"] = filter_config
        
        last_error = None
        for attempt in range(max_retries):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload, timeout=45)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    logger.error("search_failed", code=data.get("code"), message=data.get("message"))
                    return {"error": data.get("message", "搜索失败")}
                
                result = data.get("data", {})
                
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
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = min(0.5 * (2 ** attempt), 5.0)
                    logger.warning("search_retry", keyword=keyword, attempt=attempt + 1, wait=wait_time, error=str(e))
                    await asyncio.sleep(wait_time)
                    continue
                else:
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
        
        return {"error": "搜索失败，请稍后重试"}
    
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
    
    async def health_check(self) -> bool:
        """检查 pansou 服务是否健康"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def _clean_text(self, text: str) -> str:
        """清理文本，移除可能导致格式问题的字符"""
        if not text:
            return ""
        text = str(text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
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
            return f"🔍 未找到与「{keyword}」相关的资源"
        
        lines = [
            f"🔍 搜索结果: {keyword}",
            f"📊 共找到 {total} 条结果",
            "",
            "👇 请选择网盘类型查看详细资源:"
        ]
        
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
            f"{icon} <b>{type_name}</b> - {keyword}",
            f"📊 共 {len(links)} 条结果 (第{page}/{total_pages}页)\n"
        ]
        
        for i, link in enumerate(page_links, start + 1):
            url = link.get("url", "")
            password = link.get("password", "")
            note = link.get("note", "")
            source = link.get("source", "")
            
            clean_note = self._clean_text(note) if note else "无标题"
            
            lines.append(f"{i}. {clean_note}")
            lines.append(f"   🔗 {url}")
            if password:
                lines.append(f"   🔑 密码: <code>{password}</code>")
            if source:
                lines.append(f"   📌 来源: {source}")
            lines.append("")  # 空行分隔
        
        lines.append("─────────────")
        lines.append("💡 提示: 点击链接可访问，长按可复制")
        
        return "\n".join(lines)
    
    def format_results(self, results: Dict[str, Any], keyword: str) -> str:
        """
        格式化所有搜索结果（备用，显示所有结果）
        """
        if "error" in results:
            return f"❌ 搜索失败: {results['error']}"
        
        merged_by_type = results.get("merged_by_type", {})
        total = results.get("total", 0)
        
        if not merged_by_type or total == 0:
            return f"🔍 未找到与「{keyword}」相关的资源"
        
        lines = [
            f"🔍 搜索结果: {keyword}",
            f"📊 共找到 {total} 条结果\n"
        ]
        
        for cloud_type, links in merged_by_type.items():
            if not links:
                continue
            
            type_name = CLOUD_TYPE_NAMES.get(cloud_type, cloud_type)
            lines.append(f"\n📁 {type_name} ({len(links)}个)")
            
            for i, link in enumerate(links[:5], 1):  # 限制显示数量
                url = link.get("url", "")
                password = link.get("password", "")
                note = link.get("note", "")
                source = link.get("source", "")
                
                clean_note = self._clean_text(note) if note else "无标题"
                
                lines.append(f"\n{i}. {clean_note}")
                lines.append(f"   🔗 {url}")
                if password:
                    lines.append(f"   🔑 密码: {password}")
                if source:
                    lines.append(f"   📌 来源: {source}")
        
        lines.append("\n─────────────")
        lines.append("💡 提示: 长按链接可复制，密码可手动复制")
        
        return "\n".join(lines)


# 全局客户端实例
pansou_client = PansouClient()
