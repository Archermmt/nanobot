"""Network connection utility functions."""

import socket


def get_local_ip(host: str = None) -> str:
    """获取本地 IP 地址

    Args:
        host: 主机地址，如果为 "localhost" 则返回 "0.0.0.0"

    Returns:
        str: 本地 IP 地址
    """
    if host and host == "localhost":
        return "0.0.0.0"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to Google's DNS servers
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"
