import sys
from pathlib import Path

from .config import IMAGE_VERSION, VERSION, settings
from .log import LOG_PATH, setup_logger
from .search_provider import SEARCH_CONFIG

TMDB_API = "32b19d6a05b512190a056fa4e747cbbc"
DATA_PATH = "sqlite:///data/data.db"
LEGACY_DATA_PATH = Path("data/data.json")
VERSION_PATH = Path("config/version.info")
POSTERS_PATH = Path("data/posters")

PLATFORM = "Windows" if sys.platform == "win32" else "Unix"


def resolve_webui_port() -> int:
    """解析 WebUI 监听端口：AB_WEBUI_PORT 环境变量优先于配置文件。

    配置文件里的 webui_port 只在首次引导时从环境变量取样（上游行为），
    已有部署改环境变量原本不生效；容器场景用户期望 env 每次都管用，
    故监听端口以环境变量为最高优先级，且不回写配置（避免粘住）。
    """
    import os

    env = os.getenv("AB_WEBUI_PORT")
    if env:
        try:
            return int(env)
        except ValueError:
            import logging

            logging.getLogger(__name__).warning(
                "Invalid AB_WEBUI_PORT %r; falling back to config port", env
            )
    return settings.program.webui_port
