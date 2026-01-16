#!/usr/bin/env python3
"""
OrderWise 比价工具 - 连接到 Sandbox 中的 MCP 服务器并调用 compare_prices 进行比价

使用方法:
    python compare_prices.py

或通过环境变量配置:
    export MCP_SERVER_URL=http://8703-{your_sandbox_id}.sandbox.ucloudai.com/mcp
    export MCP_PRODUCT_NAME=瑞幸咖啡
    python compare_prices.py
"""

import asyncio
import json
import os
import sys
from fastmcp import Client


async def compare_prices_example():
    """示例：调用 compare_prices 工具进行比价"""
    
    # MCP 服务器地址（sandbox 外部访问地址）
    # 格式: http://{port}-{sandbox_id}.sandbox.ucloudai.com/mcp
    mcp_server_url = os.getenv("MCP_SERVER_URL")
    if not mcp_server_url:
        print("错误: 请设置环境变量 MCP_SERVER_URL")
        print("例如: export MCP_SERVER_URL=http://8703-{your_sandbox_id}.sandbox.ucloudai.com/mcp")
        sys.exit(1)
    
    print("=" * 60)
    print("OrderWise MCP Client - 比价示例")
    print("=" * 60)
    print(f"MCP Server: {mcp_server_url}")
    print("=" * 60)
    
    # 连接到 MCP Server
    client = Client(mcp_server_url, timeout=600.0)
    
    async with client:
            print("\n已连接到 MCP 服务器\n")
            
            # 列出所有可用工具
            print("可用工具:")
            tools = await client.list_tools()
            for tool in tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # 获取输入
            product_name = os.getenv("MCP_PRODUCT_NAME")
            if not product_name:
                product_name = input("\n请输入商品名称: ").strip()
                if not product_name:
                    print("错误: 商品名称不能为空")
                    return
            
            seller_name = os.getenv("MCP_SELLER_NAME") or None
            if not seller_name:
                seller_input = input("请输入商家名称（可选，直接回车跳过）: ").strip()
                seller_name = seller_input if seller_input else None
            
            # 配置参数
            apps = ["美团", "京东外卖", "淘宝闪购"]
            max_steps = int(os.getenv("MCP_MAX_STEPS", "100"))
            
            tool_params = {
                "product_name": product_name,
                "seller_name": seller_name,
                "apps": apps,
                "max_steps": max_steps,
            }
            
            print(f"\n开始比价: {product_name}")
            if seller_name:
                print(f"   商家: {seller_name}")
            print(f"   平台: {', '.join(apps)}")
            print(f"   最大步数: {max_steps}")
            print("\n" + "=" * 60)
            
            session_id = None
            
            while True:
                if session_id:
                    # 继续任务：需要用户输入（处理登录/验证码等）
                    print("\n" + "=" * 60)
                    print("任务需要您的操作（登录/验证码等）")
                    print("=" * 60)
                    reply = input("请输入您的操作结果（例如：'已完成登录'、'已输入验证码'）: ").strip()
                    if not reply:
                        print("错误: 操作结果不能为空")
                        continue
                    
                    tool_params = {
                        "product_name": product_name,
                        "seller_name": seller_name,
                        "session_id": session_id,
                        "reply_from_client": reply,
                    }
                
                # 调用 compare_prices 工具
                print("\n调用 compare_prices...")
                result = await client.call_tool("compare_prices", tool_params)
                
                if not result.content:
                    print("错误: 服务器返回空结果")
                    return
                
                result_data = json.loads(result.content[0].text)
                
                if "error" in result_data:
                    print(f"\n错误: {result_data['error']}")
                    if "session_id" in result_data:
                        session_id = result_data["session_id"]
                        continue
                    return
                
                # 检查是否需要用户交互
                if result_data.get("stop_reason") == "INFO_ACTION_NEEDS_REPLY":
                    session_id = result_data.get("session_id")
                    message = result_data.get("message", "需要用户操作")
                    
                    print("\n" + "=" * 60)
                    print(f"{message}")
                    print(f"Session ID: {session_id}")
                    print("=" * 60)
                    
                    # 继续循环，等待用户输入
                    continue
                
                # 任务完成
                print("\n" + "=" * 60)
                print("比价结果:")
                print("=" * 60)
                print(json.dumps(result_data, indent=2, ensure_ascii=False))
                
                # 提取关键信息
                if "summary" in result_data and result_data["summary"].get("best_price"):
                    best = result_data["summary"]["best_price"]
                    print(f"\n最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
                
                break


if __name__ == "__main__":
    asyncio.run(compare_prices_example())

