"""
日志配置模块
"""
import sys
import structlog
from structlog.stdlib import LoggerFactory
from structlog.processors import TimeStamper, add_log_level, JSONRenderer
from src.config import settings


def setup_logging():
    """配置结构化日志"""
    
    # 配置标准库日志
    import logging
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )
    
    # 配置 structlog
    structlog.configure(
        processors=[
            add_log_level,
            TimeStamper(fmt="iso"),
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            JSONRenderer() if settings.log_level.upper() == "INFO" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """获取日志记录器"""
    return structlog.get_logger(name)
