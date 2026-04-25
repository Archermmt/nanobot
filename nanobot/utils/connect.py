"""Network connection utility functions."""

import socket


def get_local_ip() -> str:
    """Get local IP address

    Returns:
        str: Local IP address
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to Google's DNS servers
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def parse_ip(ip: str):
    """Parse IP address

    Args:
        ip: IP address

    Returns:
        str: Parsed IP address
    """

    if ip not in ("localhost", "127.0.0.1", "0.0.0.0"):
        return ip
    return get_local_ip()
