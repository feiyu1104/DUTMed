"""
速率限制模块 - 防止API滥用
"""
import time
from collections import defaultdict
from threading import Lock
from typing import Optional


class RateLimiter:
    """简单的基于时间窗口的速率限制器"""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        """
        初始化速率限制器
        
        Args:
            max_requests: 时间窗口内的最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self.lock = Lock()
    
    def is_allowed(self, key: str) -> bool:
        """
        检查是否允许请求
        
        Args:
            key: 请求的唯一标识（如IP地址）
            
        Returns:
            True如果允许请求，False如果超过限制
        """
        with self.lock:
            current_time = time.time()
            
            # 清理过期的请求记录
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < self.window_seconds
            ]
            
            # 检查是否超过限制
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            # 记录新请求
            self.requests[key].append(current_time)
            return True
    
    def get_remaining(self, key: str) -> int:
        """获取剩余可用请求数"""
        with self.lock:
            current_time = time.time()
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < self.window_seconds
            ]
            return max(0, self.max_requests - len(self.requests[key]))
    
    def reset(self, key: str):
        """重置某个key的限制"""
        with self.lock:
            if key in self.requests:
                del self.requests[key]
    
    def clear(self):
        """清空所有限制记录"""
        with self.lock:
            self.requests.clear()


# 全局速率限制器实例
_global_rate_limiter = None


def get_rate_limiter(max_requests: int = 60, window_seconds: int = 60) -> RateLimiter:
    """获取全局速率限制器实例（单例）"""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(max_requests, window_seconds)
    return _global_rate_limiter


def rate_limit_decorator(limiter: RateLimiter, key_func=None):
    """
    速率限制装饰器（用于Flask路由）
    
    Args:
        limiter: RateLimiter实例
        key_func: 可选的键生成函数，默认使用客户端IP
    """
    def decorator(f):
        def wrapped(*args, **kwargs):
            from flask import request, jsonify
            
            # 生成限制键
            if key_func:
                key = key_func()
            else:
                key = request.remote_addr or 'unknown'
            
            # 检查速率限制
            if not limiter.is_allowed(key):
                return jsonify({
                    "error": "Rate limit exceeded. Please try again later.",
                    "code": 429
                }), 429
            
            return f(*args, **kwargs)
        
        wrapped.__name__ = f.__name__
        return wrapped
    return decorator


if __name__ == "__main__":
    # 测试速率限制器
    limiter = RateLimiter(max_requests=3, window_seconds=2)
    
    print("测试速率限制器（最多3次/2秒）...")
    
    # 测试正常情况
    for i in range(3):
        if limiter.is_allowed("test_user"):
            print(f"请求 {i+1}: 允许")
        else:
            print(f"请求 {i+1}: 拒绝")
    
    # 第4次应该被拒绝
    if limiter.is_allowed("test_user"):
        print("请求 4: 允许")
    else:
        print("请求 4: 拒绝（超过限制）")
    
    # 等待2秒后应该可以再次请求
    print("\n等待2秒...")
    time.sleep(2.1)
    
    if limiter.is_allowed("test_user"):
        print("等待后的请求: 允许")
    else:
        print("等待后的请求: 拒绝")
