import logging
import sys
from datetime import datetime
from typing import Optional

def get_logger(
    name: str = __name__, 
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Create and configure a logger for console output.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string for log messages
    
    Returns:
        Configured logger instance
    """
    
    # Default format string
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding handlers multiple times
    if not logger.handlers:
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(format_string)
        console_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(console_handler)
    
    return logger

# Convenience function for quick logging
def log_info(message: str, logger_name: str = "Localoop"):
    """Quick info logging"""
    logger = get_logger(logger_name)
    logger.info(message)

def log_error(message: str, logger_name: str = "Localoop"):
    """Quick error logging"""
    logger = get_logger(logger_name)
    logger.error(message)

def log_warning(message: str, logger_name: str = "Localoop"):
    """Quick warning logging"""
    logger = get_logger(logger_name)
    logger.warning(message)

def log_debug(message: str, logger_name: str = "Localoop"):
    """Quick debug logging"""
    logger = get_logger(logger_name, level=logging.DEBUG)
    logger.debug(message)