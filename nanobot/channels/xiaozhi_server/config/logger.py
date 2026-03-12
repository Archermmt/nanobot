"""Logger adapter for xiaozhi_server compatibility."""

import logging

# 创建全局 logger 实例
_logger = None


def setup_logging():
    """设置并返回日志记录器"""
    global _logger

    if _logger is None:
        # 使用 nanobot 的日志系统
        _logger = logging.getLogger("xiaozhi_server")
        _logger.setLevel(logging.INFO)

        # 如果还没有 handler，添加一个控制台 handler
        if not _logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] - %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            _logger.addHandler(handler)

    return _logger
