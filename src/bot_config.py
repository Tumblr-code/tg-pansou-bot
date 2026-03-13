"""
Bot 配置优化 - 解决网络延迟问题
"""
from telegram.request import HTTPXRequest

import httpx

def create_optimized_request():
    """创建优化的 HTTP 请求配置（单例模式复用连接池）"""
    return HTTPXRequest(
        connection_pool_size=32,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
