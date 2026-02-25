"""
Bot 配置模块
"""
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""
    
    # Telegram Bot 配置
    tg_bot_token: str = Field(..., description="Telegram Bot Token")
    
    # Pansou API 配置
    pansou_api_url: str = Field(default="http://localhost:8888", description="Pansou API 地址")
    pansou_api_token: Optional[str] = Field(default=None, description="Pansou API 认证 Token")
    
    # 代理配置
    http_proxy: Optional[str] = Field(default=None, description="HTTP 代理")
    https_proxy: Optional[str] = Field(default=None, description="HTTPS 代理")
    
    # 搜索配置
    default_result_limit: int = Field(default=10, ge=1, le=50, description="默认结果限制")
    max_result_limit: int = Field(default=20, ge=1, le=100, description="最大结果限制")
    search_timeout: int = Field(default=30, ge=5, le=60, description="搜索超时时间(秒)")
    
    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    
    # 速率限制
    rate_limit_per_minute: int = Field(default=10, ge=1, description="每分钟速率限制")
    
    # 默认搜索频道（可选）
    default_channels: Optional[str] = Field(default=None, description="默认搜索频道，逗号分隔")
    
    # 默认启用的插件（可选）
    default_plugins: Optional[str] = Field(default=None, description="默认启用插件，逗号分隔")
    
    # 管理员配置
    admin_ids: Optional[str] = Field(default=None, description="管理员ID列表，逗号分隔")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_proxies(self) -> Optional[dict]:
        """获取代理配置"""
        proxies = {}
        if self.http_proxy:
            proxies['http://'] = self.http_proxy
        if self.https_proxy:
            proxies['https://'] = self.https_proxy
        return proxies if proxies else None
    
    def get_default_channels(self) -> Optional[List[str]]:
        """获取默认频道列表"""
        if self.default_channels:
            return [c.strip() for c in self.default_channels.split(',') if c.strip()]
        return None
    
    def get_default_plugins(self) -> Optional[List[str]]:
        """获取默认插件列表"""
        if self.default_plugins:
            return [p.strip() for p in self.default_plugins.split(',') if p.strip()]
        return None
    
    def get_admin_ids(self) -> List[int]:
        """获取管理员ID列表"""
        if self.admin_ids:
            return [int(id_str.strip()) for id_str in self.admin_ids.split(',') if id_str.strip()]
        return []
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否为管理员"""
        admins = self.get_admin_ids()
        return len(admins) == 0 or user_id in admins  # 未设置管理员时所有人都是管理员


# 全局配置实例
settings = Settings()
