"""
Logging Configuration for Trailing Edge Trading Bot

Provides hybrid logging with console output (INFO) and file rotation (DEBUG).
Keeps print() statements for real-time monitoring while logging critical events.
Creates timestamped log files for each session.
"""

import logging
from datetime import datetime
from pathlib import Path


def setup_logging(
    log_dir: str = "logs", log_level: int = logging.DEBUG
) -> logging.Logger:
    """
    Configure logging with console and session-timestamped file handlers.

    Creates a new log file for each session with timestamp in filename:
    - trailingedge_YYYY-MM-DD_HH-MM-SS.log

    Also maintains a symlink/copy to latest.log for easy access.

    Args:
        log_dir: Directory for log files (default: 'logs')
        log_level: Base logging level (default: DEBUG)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger("trailingedge")
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (INFO level for important events only)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create timestamped log filename for this session
    session_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = Path(log_dir) / f"trailingedge_{session_timestamp}.log"

    # File handler with session timestamp (DEBUG level for everything)
    file_handler = logging.FileHandler(
        str(log_file),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Create a 'latest.log' symlink/copy for easy access
    latest_log = Path(log_dir) / "latest.log"
    try:
        # Try to create symlink (works on Unix and Windows with dev mode/admin)
        if latest_log.exists() or latest_log.is_symlink():
            latest_log.unlink()
        latest_log.symlink_to(log_file.name)
    except (OSError, NotImplementedError):
        # Fallback: just note it in the log (symlinks may not work on Windows)
        pass

    return logger


def get_logger() -> logging.Logger:
    """Get the trading bot logger instance."""
    return logging.getLogger("trailingedge")
