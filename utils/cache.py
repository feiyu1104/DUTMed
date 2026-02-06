"""
缓存工具模块 - 提供LRU缓存功能以减少重复API调用
"""
import hashlib
import time
from functools import wraps
from typing import Any, Callable, Optional
from collections import OrderedDict
import json


class LRUCache:
    """线程安全的LRU缓存实现"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        初始化LRU缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
    
    def _is_expired(self, key: str) -> bool:
        """检查缓存是否过期"""
        if key not in self.timestamps:
            return True
        return (time.time() - self.timestamps[key]) > self.ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的值，如果不存在或已过期则返回None
        """
        if key not in self.cache or self._is_expired(key):
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
            return None
        
        # 移动到末尾（最近使用）
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def set(self, key: str, value: Any):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 要缓存的值
        """
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # 删除最旧的条目
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]
        
        self.cache[key] = value
        self.timestamps[key] = time.time()
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.timestamps.clear()
    
    def size(self) -> int:
        """获取当前缓存大小"""
        return len(self.cache)
    
    def stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl": self.ttl
        }


def generate_cache_key(*args, **kwargs) -> str:
    """
    生成缓存键
    
    Args:
        *args: 位置参数
        **kwargs: 关键字参数
        
    Returns:
        缓存键的哈希值
    """
    # 将参数转换为可序列化的字符串
    key_parts = []
    
    for arg in args:
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        else:
            try:
                key_parts.append(json.dumps(arg, sort_keys=True))
            except (TypeError, ValueError):
                key_parts.append(str(arg))
    
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float, bool)):
            key_parts.append(f"{k}={v}")
        else:
            try:
                key_parts.append(f"{k}={json.dumps(v, sort_keys=True)}")
            except (TypeError, ValueError):
                key_parts.append(f"{k}={str(v)}")
    
    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


def cached(cache, key_func=None):
    """
    缓存装饰器
    
    Args:
        cache: LRUCache实例
        key_func: 可选的自定义键生成函数
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = generate_cache_key(func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 调用原函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache.set(cache_key, result)
            
            return result
        
        return wrapper
    return decorator


# 全局缓存实例
_embedding_cache = None
_llm_cache = None


def get_embedding_cache(max_size=1000, ttl=3600):
    """获取embedding缓存实例（单例）"""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = LRUCache(max_size=max_size, ttl=ttl)
    return _embedding_cache


def get_llm_cache(max_size=500, ttl=1800):
    """获取LLM缓存实例（单例）"""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LRUCache(max_size=max_size, ttl=ttl)
    return _llm_cache


def clear_all_caches():
    """清空所有缓存"""
    global _embedding_cache, _llm_cache
    if _embedding_cache:
        _embedding_cache.clear()
    if _llm_cache:
        _llm_cache.clear()
