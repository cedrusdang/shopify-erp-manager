"""Logging configuration for Shopify ERP application."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime


WORK_LOGGER_NAME = "shopify_erp.worklog"


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    Configure application-wide logging to file and console.
    
    Args:
        log_dir: Directory where log files will be stored.
        
    Returns:
        Configured logger instance.
    """
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("shopify_erp")
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    simple_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler (all levels - DEBUG and above)
    log_file = log_path / f"shopify_erp_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,  # Keep 10 backup files
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Error file handler (errors only)
    error_log_file = log_path / f"shopify_erp_errors_{datetime.now().strftime('%Y%m%d')}.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)

    # Dedicated work-log handler for user-facing workflow/activity tracing.
    work_logger = logging.getLogger(WORK_LOGGER_NAME)
    work_logger.setLevel(logging.INFO)
    work_logger.handlers.clear()
    work_logger.propagate = False
    work_log_file = log_path / f"shopify_erp_work_{datetime.now().strftime('%Y%m%d')}.log"
    work_handler = logging.handlers.RotatingFileHandler(
        work_log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    work_handler.setLevel(logging.INFO)
    work_handler.setFormatter(detailed_formatter)
    work_logger.addHandler(work_handler)
    
    # Console handler (WARNING and above only)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    logger.info("=" * 80)
    logger.info("Shopify ERP Application Started")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Error log: {error_log_file}")
    work_logger.info("=" * 80)
    work_logger.info("Work Log Started")
    work_logger.info(f"Work log file: {work_log_file}")
    work_logger.info("=" * 80)
    logger.info("=" * 80)
    
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get or create a logger instance."""
    if name:
        return logging.getLogger(f"shopify_erp.{name}")
    return logging.getLogger("shopify_erp")


def get_work_logger() -> logging.Logger:
    """Get the dedicated work logger."""
    return logging.getLogger(WORK_LOGGER_NAME)


def log_work_event(message: str) -> None:
    """Write a user-facing workflow event to the dedicated work log."""
    text = str(message or "").strip()
    if not text:
        return
    get_work_logger().info(text)
