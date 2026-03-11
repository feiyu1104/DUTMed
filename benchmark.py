"""
性能基准测试 - 比较优化前后的性能
"""
import time
import sys
import os
from typing import Callable

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['TESTING'] = 'true'

from utils.cache import LRUCache, generate_cache_key


def benchmark_function(func: Callable, iterations: int = 1000, *args, **kwargs):
    """
    测试函数性能
    
    Args:
        func: 要测试的函数
        iterations: 迭代次数
        *args, **kwargs: 函数参数
        
    Returns:
        平均执行时间（秒）
    """
    start_time = time.time()
    for _ in range(iterations):
        func(*args, **kwargs)
    end_time = time.time()
    
    total_time = end_time - start_time
    avg_time = total_time / iterations
    
    return avg_time, total_time


def simulate_api_call(text: str) -> str:
    """模拟API调用（带延迟）"""
    time.sleep(0.001)  # 模拟1ms的网络延迟
    return f"Result for: {text}"


def test_with_cache(cache: LRUCache, text: str) -> str:
    """使用缓存的API调用"""
    cache_key = generate_cache_key("api", text)
    cached_result = cache.get(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    result = simulate_api_call(text)
    cache.set(cache_key, result)
    return result


def test_without_cache(text: str) -> str:
    """不使用缓存的API调用"""
    return simulate_api_call(text)


def run_cache_benchmark():
    """运行缓存性能测试"""
    print("=" * 70)
    print("缓存性能基准测试")
    print("=" * 70)
    
    # 测试数据
    test_queries = [
        "肺炎的症状是什么",
        "糖尿病如何治疗",
        "高血压吃什么药",
        "肺炎的症状是什么",  # 重复
        "糖尿病如何治疗",    # 重复
        "感冒怎么办",
        "肺炎的症状是什么",  # 重复
    ]
    
    # 测试不使用缓存
    print("\n1. 不使用缓存:")
    print("-" * 70)
    start_time = time.time()
    for query in test_queries:
        test_without_cache(query)
    time_without_cache = time.time() - start_time
    print(f"   总时间: {time_without_cache:.4f} 秒")
    print(f"   平均每次: {time_without_cache / len(test_queries):.4f} 秒")
    
    # 测试使用缓存
    print("\n2. 使用缓存:")
    print("-" * 70)
    cache = LRUCache(max_size=100, ttl=3600)
    start_time = time.time()
    for query in test_queries:
        test_with_cache(cache, query)
    time_with_cache = time.time() - start_time
    print(f"   总时间: {time_with_cache:.4f} 秒")
    print(f"   平均每次: {time_with_cache / len(test_queries):.4f} 秒")
    print(f"   缓存命中: {len(test_queries) - len(set(test_queries))}/{len(test_queries)}")
    
    # 计算提升
    speedup = time_without_cache / time_with_cache
    improvement = ((time_without_cache - time_with_cache) / time_without_cache) * 100
    
    print("\n3. 性能对比:")
    print("-" * 70)
    print(f"   加速比: {speedup:.2f}x")
    print(f"   性能提升: {improvement:.1f}%")
    print(f"   时间节省: {(time_without_cache - time_with_cache):.4f} 秒")
    
    # 估算成本节省
    print("\n4. 成本估算（假设每次API调用 ¥0.001）:")
    print("-" * 70)
    calls_without_cache = len(test_queries)
    calls_with_cache = len(set(test_queries))  # 只计算唯一查询
    
    cost_without_cache = calls_without_cache * 0.001
    cost_with_cache = calls_with_cache * 0.001
    cost_saving = cost_without_cache - cost_with_cache
    
    print(f"   不使用缓存: {calls_without_cache} 次调用 = ¥{cost_without_cache:.4f}")
    print(f"   使用缓存: {calls_with_cache} 次调用 = ¥{cost_with_cache:.4f}")
    print(f"   成本节省: ¥{cost_saving:.4f} ({cost_saving/cost_without_cache*100:.1f}%)")
    
    # 月度估算
    monthly_queries = 10000  # 假设每月10000次查询
    duplicate_rate = 0.5     # 假设50%是重复查询
    
    monthly_cost_without = monthly_queries * 0.001
    monthly_cost_with = monthly_queries * (1 - duplicate_rate) * 0.001
    monthly_saving = monthly_cost_without - monthly_cost_with
    
    print(f"\n5. 月度成本估算（10000次查询，50%重复率）:")
    print("-" * 70)
    print(f"   不使用缓存: ¥{monthly_cost_without:.2f}/月")
    print(f"   使用缓存: ¥{monthly_cost_with:.2f}/月")
    print(f"   每月节省: ¥{monthly_saving:.2f} ({monthly_saving/monthly_cost_without*100:.0f}%)")


def run_cache_overhead_test():
    """测试缓存本身的开销"""
    print("\n\n" + "=" * 70)
    print("缓存开销测试")
    print("=" * 70)
    
    cache = LRUCache(max_size=1000, ttl=3600)
    iterations = 10000
    
    # 测试缓存设置操作
    print("\n1. 缓存设置操作:")
    print("-" * 70)
    avg_time, total_time = benchmark_function(
        cache.set,
        iterations,
        "test_key",
        "test_value"
    )
    print(f"   {iterations} 次设置操作")
    print(f"   总时间: {total_time:.4f} 秒")
    print(f"   平均时间: {avg_time * 1000:.4f} 毫秒")
    print(f"   每秒操作: {iterations / total_time:.0f} ops/sec")
    
    # 测试缓存获取操作
    print("\n2. 缓存获取操作:")
    print("-" * 70)
    cache.set("test_key", "test_value")
    avg_time, total_time = benchmark_function(
        cache.get,
        iterations,
        "test_key"
    )
    print(f"   {iterations} 次获取操作")
    print(f"   总时间: {total_time:.4f} 秒")
    print(f"   平均时间: {avg_time * 1000:.4f} 毫秒")
    print(f"   每秒操作: {iterations / total_time:.0f} ops/sec")
    
    # 测试缓存键生成
    print("\n3. 缓存键生成:")
    print("-" * 70)
    avg_time, total_time = benchmark_function(
        generate_cache_key,
        iterations,
        "function_name",
        "arg1",
        "arg2"
    )
    print(f"   {iterations} 次键生成")
    print(f"   总时间: {total_time:.4f} 秒")
    print(f"   平均时间: {avg_time * 1000:.4f} 毫秒")
    print(f"   每秒操作: {iterations / total_time:.0f} ops/sec")


def main():
    """运行所有基准测试"""
    print("\n" + "=" * 70)
    print("DUTMed 性能优化基准测试")
    print("=" * 70)
    print("\n注意：这是一个简化的基准测试，实际API调用会慢得多")
    print("      真实场景中的性能提升会更加显著\n")
    
    try:
        run_cache_benchmark()
        run_cache_overhead_test()
        
        print("\n\n" + "=" * 70)
        print("✅ 基准测试完成")
        print("=" * 70)
        print("\n总结：")
        print("  - 缓存可以显著减少重复API调用的时间和成本")
        print("  - 缓存本身的开销极小（微秒级）")
        print("  - 对于重复率高的场景，性能提升非常明显")
        print("  - 建议在生产环境中启用缓存以节省成本\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 基准测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
