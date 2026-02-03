"""
Logging configuration for Universal Library

Provides consistent logging setup across the application.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


class LoggingConfig:
    """
    Logging configuration manager

    Provides static methods for setting up and getting loggers.
    """

    _initialized = False

    @staticmethod
    def setup_logging(
        log_dir: Path = None,
        level: int = logging.INFO,
        log_to_file: bool = True,
        log_to_console: bool = True
    ) -> logging.Logger:
        """
        Configure application logging

        Args:
            log_dir: Directory for log files
            level: Logging level (default INFO)
            log_to_file: Enable file logging
            log_to_console: Enable console logging

        Returns:
            Root logger for the application
        """
        # Get root logger for the package
        logger = logging.getLogger('universal_library')
        logger.setLevel(level)

        # Clear existing handlers to avoid duplicates
        logger.handlers.clear()

        # Format
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # File handler
        if log_to_file and log_dir:
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"

                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                # If file logging fails, just log to console
                logger.warning(f"Could not set up file logging: {e}")

        LoggingConfig._initialized = True
        return logger

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Get a logger for a specific module

        Args:
            name: Module name (typically __name__)

        Returns:
            Logger instance
        """
        return logging.getLogger(name)


__all__ = ['LoggingConfig']
