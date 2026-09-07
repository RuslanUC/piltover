from __future__ import annotations
import logging

from loguru import logger


# https://stackoverflow.com/a/72735401
class InterceptHandler(logging.Handler):
    _instance: InterceptHandler | None = None

    @logger.catch(default=True)
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        import sys
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    @classmethod
    def redirect_to_loguru(cls, logger_name: str, level: int = logging.INFO) -> logging.Handler:
        if isinstance(cls._instance, cls):
            instance = cls._instance
        else:
            cls._instance = instance = cls()

        std_logger = logging.getLogger(logger_name)
        std_logger.setLevel(level)
        std_logger.addHandler(instance)

        return instance
