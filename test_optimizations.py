"""
简单的集成测试 - 验证优化功能
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """测试配置模块"""
    print("测试配置模块...")
    os.environ['TESTING'] = 'true'
    
    from config import Config
    
    assert hasattr(Config, 'NEO4J_URI'), "Config应该有NEO4J_URI"
    assert hasattr(Config, 'CACHE_ENABLED'), "Config应该有CACHE_ENABLED"
    assert hasattr(Config, 'LLM_CACHE_TEMPERATURE_THRESHOLD'), "Config应该有LLM_CACHE_TEMPERATURE_THRESHOLD"
    assert Config.API_MAX_RETRIES == 3, "API_MAX_RETRIES应该是3"
    
    print("✅ 配置模块测试通过")


def test_cache():
    """测试缓存模块"""
    print("\n测试缓存模块...")
    from utils.cache import LRUCache, generate_cache_key
    
    cache = LRUCache(max_size=3, ttl=10)
    
    # 测试基本功能
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1", "应该能获取缓存值"
    
    # 测试None值
    cache.set("key2", None)
    assert cache.get("key2") is None, "应该能缓存None值"
    assert "key2" in cache.cache, "None值应该在缓存中"
    
    # 测试falsy值
    cache.set("key3", 0)
    assert cache.get("key3") == 0, "应该能缓存0"
    
    cache.set("key4", False)
    assert cache.get("key4") is False, "应该能缓存False"
    
    cache.set("key5", "")
    assert cache.get("key5") == "", "应该能缓存空字符串"
    
    # 测试LRU淘汰
    cache.clear()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    cache.set("d", 4)  # 应该淘汰 'a'
    
    assert cache.get("a") is None, "最旧的条目应该被淘汰"
    assert cache.get("d") == 4, "最新的条目应该存在"
    
    # 测试缓存键生成
    key1 = generate_cache_key("func", "arg1", "arg2")
    key2 = generate_cache_key("func", "arg1", "arg2")
    key3 = generate_cache_key("func", "arg2", "arg1")
    
    assert key1 == key2, "相同参数应该生成相同的键"
    assert key1 != key3, "不同参数应该生成不同的键"
    
    print("✅ 缓存模块测试通过")


def test_rate_limiter():
    """测试速率限制器"""
    print("\n测试速率限制器...")
    from utils.rate_limiter import RateLimiter
    import time
    
    limiter = RateLimiter(max_requests=3, window_seconds=1)
    
    # 测试正常情况
    assert limiter.is_allowed("user1") is True, "第1次请求应该允许"
    assert limiter.is_allowed("user1") is True, "第2次请求应该允许"
    assert limiter.is_allowed("user1") is True, "第3次请求应该允许"
    assert limiter.is_allowed("user1") is False, "第4次请求应该拒绝"
    
    # 测试不同用户
    assert limiter.is_allowed("user2") is True, "不同用户应该有独立的限制"
    
    # 测试窗口过期
    time.sleep(1.1)
    assert limiter.is_allowed("user1") is True, "窗口过期后应该允许"
    
    # 测试重置
    limiter.reset("user1")
    assert limiter.is_allowed("user1") is True, "重置后应该允许"
    
    print("✅ 速率限制器测试通过")


def test_logger():
    """测试日志模块"""
    print("\n测试日志模块...")
    from utils.logger import setup_logger, get_app_logger
    import logging
    
    # 测试基本日志设置
    logger = setup_logger("test", level=logging.INFO)
    assert logger.name == "test", "Logger名称应该正确"
    assert logger.level == logging.INFO, "Logger级别应该正确"
    
    # 测试应用日志
    app_logger = get_app_logger("TestApp")
    assert app_logger.name == "TestApp", "应用Logger名称应该正确"
    
    print("✅ 日志模块测试通过")


def test_imports():
    """测试主要模块导入"""
    print("\n测试模块导入...")
    os.environ['TESTING'] = 'true'
    
    try:
        import config
        print("  ✓ config模块")
    except Exception as e:
        print(f"  ✗ config模块导入失败: {e}")
        return False
    
    try:
        from utils import cache
        print("  ✓ cache模块")
    except Exception as e:
        print(f"  ✗ cache模块导入失败: {e}")
        return False
    
    try:
        from utils import rate_limiter
        print("  ✓ rate_limiter模块")
    except Exception as e:
        print(f"  ✗ rate_limiter模块导入失败: {e}")
        return False
    
    try:
        from utils import logger
        print("  ✓ logger模块")
    except Exception as e:
        print(f"  ✗ logger模块导入失败: {e}")
        return False
    
    print("✅ 模块导入测试通过")
    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始运行集成测试...")
    print("=" * 60)
    
    try:
        test_imports()
        test_config()
        test_cache()
        test_rate_limiter()
        test_logger()
        
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
