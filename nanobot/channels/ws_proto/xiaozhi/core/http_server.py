import asyncio
import traceback

from aiohttp import web
from loguru import logger

from nanobot.channels.ws_proto.xiaozhi.core.schema import XiaoZhiProtoConfig
from nanobot.utils.connect import parse_ip

from .api.ota_handler import OTAHandler

TAG = __name__


class SimpleHttpServer:
    def __init__(self, config: XiaoZhiProtoConfig, host: str, port: int):
        self.config = config
        self.host = host
        self.ota_handler = OTAHandler(config, port)

    async def start(self):
        try:
            read_config_from_api = self.config.read_config_from_api
            port = self.config.http_port
            app = web.Application()
            if not read_config_from_api:
                # 如果没有开启智控台，只是单模块运行，就需要再添加简单OTA接口，用于下发websocket接口
                app.add_routes(
                    [
                        web.get("/xiaozhi/ota/", self.ota_handler.handle_get),
                        web.post("/xiaozhi/ota/", self.ota_handler.handle_post),
                        web.options("/xiaozhi/ota/", self.ota_handler.handle_options),
                        # 下载接口，仅提供 data/bin/*.bin 下载
                        web.get(
                            "/xiaozhi/ota/download/{filename}",
                            self.ota_handler.handle_download,
                        ),
                        web.options(
                            "/xiaozhi/ota/download/{filename}",
                            self.ota_handler.handle_options,
                        ),
                    ]
                )
            # 运行服务
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, self.host, port)
            await site.start()
            logger.info(f"Xiaozhi HTTP Server: {parse_ip(self.host)}:{port}")
            # 保持服务运行
            while True:
                await asyncio.sleep(3600)  # 每隔 1 小时检查一次
        except Exception as e:
            logger.error(f"HTTP Server failed: {e}:\nInfo: {traceback.format_exc()}")
            raise
