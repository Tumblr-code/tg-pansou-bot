"""
Bot 配置优化 - 解决网络延迟问题
"""
from telegram.request import HTTPXRequest

def create_optimized_request():
    """创建优化的 HTTP 请求配置"""
    return HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=90.0,    # 连接超时
        read_timeout=120.0,      # 读取超时
        write_timeout=60.0,      # 写入超时
        pool_timeout=60.0,       # 连接池超时
    )
