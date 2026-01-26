#!/usr/bin/env python3
"""
OrderWise-Agent SDK 使用示例

演示如何使用 OrderWise-Agent 进行多平台外卖比价。
"""

import os
from orderwise_agent import compare_prices

# 配置模型服务（如果未在环境变量中设置）
os.environ.setdefault("ORDERWISE_MODEL_URL", "http://localhost:4244/v1")
os.environ.setdefault("ORDERWISE_MODEL_NAME", "autoglm-phone-9b")


def example_simple_compare():
    """示例 1: 简单比价"""
    print("=" * 50)
    print("示例 1: 简单比价")
    print("=" * 50)
    
    result = compare_prices("茉莉花香拿铁")
    
    if result.get("error"):
        print(f"错误: {result['error']}")
        return
    
    best = result["best_price"]
    print(f"\n比价完成！")
    print(f"最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
    
    print(f"\n详细结果:")
    for app, data in result["platform_results"].items():
        print(f"  {app}: ¥{data['total_fee']:.2f}")


def example_with_seller():
    """示例 2: 指定商家比价"""
    print("\n" + "=" * 50)
    print("示例 2: 指定商家比价")
    print("=" * 50)
    
    result = compare_prices(
        product_name="茉莉花香拿铁",
        seller_name="瑞幸",
        apps=["美团", "京东外卖", "淘宝闪购"]
    )
    
    if result.get("error"):
        print(f"错误: {result['error']}")
        return
    
    best = result["best_price"]
    print(f"\n比价完成！")
    print(f"最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
    
    print(f"\n详细结果:")
    for app, data in result["platform_results"].items():
        print(f"{app}:")
        print(f"  商品价格: ¥{data['price']:.2f}")
        print(f"  配送费: ¥{data['delivery_fee']:.2f}")
        print(f"  打包费: ¥{data['pack_fee']:.2f}")
        print(f"  总价: ¥{data['total_fee']:.2f}")


def example_custom_apps():
    """示例 3: 自定义平台列表"""
    print("\n" + "=" * 50)
    print("示例 3: 自定义平台列表")
    print("=" * 50)
    
    result = compare_prices(
        product_name="茉莉花香拿铁",
        apps=["美团", "京东外卖"]  # 只比较两个平台
    )
    
    if result.get("error"):
        print(f"错误: {result['error']}")
        return
    
    best = result["best_price"]
    print(f"\n比价完成！")
    print(f"最低价格: {best['app']} - ¥{best['total_fee']:.2f}")


def example_error_handling():
    """示例 4: 错误处理"""
    print("\n" + "=" * 50)
    print("示例 4: 错误处理")
    print("=" * 50)
    
    result = compare_prices("不存在的商品")
    
    if result.get("error"):
        print(f"错误: {result['error']}")
        print("这是正常的错误处理示例")
    else:
        best = result.get("best_price")
        if best:
            print(f"找到最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
        else:
            print("未找到价格信息")


if __name__ == "__main__":
    print("OrderWise-Agent SDK 使用示例\n")
    
    # 运行示例
    example_simple_compare()
    # example_with_seller()
    # example_custom_apps()
    # example_error_handling()
    
    print("\n" + "=" * 50)
    print("提示: 取消注释其他示例函数以查看更多用法")
    print("=" * 50)

