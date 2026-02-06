"""
日志工具模块 - 提供结构化日志功能
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    设置结构化日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径（可选）
        level: 日志级别
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的备份文件数量
        
    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_app_logger(name: str = "DUTMed") -> logging.Logger:
    """获取应用日志记录器"""
    return setup_logger(
        name=name,
        log_file="logs/app.log",
        level=logging.INFO
    )


def get_api_logger(name: str = "DUTMed.API") -> logging.Logger:
    """获取API日志记录器"""
    return setup_logger(
        name=name,
        log_file="logs/api.log",
        level=logging.INFO
    )


def get_error_logger(name: str = "DUTMed.Error") -> logging.Logger:
    """获取错误日志记录器"""
    return setup_logger(
        name=name,
        log_file="logs/error.log",
        level=logging.ERROR
    )


if __name__ == "__main__":
    # 测试日志功能
    logger = get_app_logger("TestLogger")
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    print("日志已写入 logs/app.log")
