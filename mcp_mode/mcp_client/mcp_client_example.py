#!/usr/bin/env python3
"""Order Wise MCP Client 使用示例 - 支持交互式和脚本化模式（支持 部分takeover）

交互式模式:
    python mcp_mode/mcp_client/mcp_client_example.py

脚本化模式（通过环境变量）:
    export MCP_SERVER_URL=http://127.0.0.1:8703/mcp
    export MCP_PRODUCT_NAME=疯狂红茶拿铁
    export MCP_SELLER_NAME=瑞幸
    export MCP_APPS=美团,京东外卖,淘宝闪购
    export MCP_MAX_STEPS=100
    export MCP_MODEL_PROVIDER=local
    python mcp_mode/mcp_client/mcp_client_example.py
"""

import asyncio
import json
import os
import sys
from fastmcp import Client


async def _run_compare_prices(client):
    """执行比价逻辑（内部函数，不处理连接错误）"""
    # 列出所有可用工具
    tools = await client.list_tools()
    print("可用工具:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")
    
    # 从环境变量读取配置，支持脚本化使用
    apps_env = os.getenv("MCP_APPS", "美团,京东外卖,淘宝闪购")
    max_steps = int(os.getenv("MCP_MAX_STEPS", "100"))
    model_provider = os.getenv("MCP_MODEL_PROVIDER", "local")
    apps = [app.strip() for app in apps_env.split(",") if app.strip()] or ["美团", "京东外卖", "淘宝闪购"]
    
    # 获取输入（支持环境变量，用于脚本化）
    product_name = os.getenv("MCP_PRODUCT_NAME")
    if not product_name:
        product_name = input("\n请输入商品名称: ").strip()
        if not product_name:
            print("错误: 商品名称不能为空")
            return
    
    seller_name = os.getenv("MCP_SELLER_NAME")
    if seller_name is None:
        seller_input = input("请输入商家名称（可选，直接回车跳过）: ").strip()
        seller_name = seller_input if seller_input else None
    elif not seller_name:
        seller_name = None
    
    tool_params = {
        "product_name": product_name,
        "seller_name": seller_name,
        "apps": apps,
        "max_steps": max_steps,
        "model_provider": model_provider
    }
    
    session_id = None
    
    while True:
        if session_id:
            # 继续任务：需要用户输入
            print("\n" + "="*60)
            print("任务需要您的操作（登录/验证码等）")
            print("="*60)
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
        
        print("\n调用 compare_prices...")
        result = await client.call_tool("compare_prices", tool_params)
        result_data = json.loads(result.content[0].text)
        
        # 检查错误
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
            
            print("\n" + "="*60)
            print(f"{message}")
            print(f"Session ID: {session_id}")
            print("="*60)
            
            # 继续循环，等待用户输入
            continue
        
        # 任务完成
        print("\n" + "="*60)
        print("比价结果:")
        print("="*60)
        print(json.dumps(result_data, indent=2, ensure_ascii=False))
        
        # 提取关键信息
        if "summary" in result_data and result_data["summary"].get("best_price"):
            best = result_data["summary"]["best_price"]
            print(f"\n最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
        
        break


async def example_compare_prices():
    """示例：交互式比价（支持 takeover）"""
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8703/mcp")
    client = Client(mcp_server_url, timeout=300.0)
    
    # 连接错误会自然传播，在外层处理
    async with client:
        await _run_compare_prices(client)


if __name__ == "__main__":
    # 检查是否为脚本化模式（通过环境变量判断）
    script_mode = bool(os.getenv("MCP_PRODUCT_NAME"))
    
    if script_mode:
        print("=" * 60)
        print("Order Wise MCP Client - 脚本化模式")
        print("=" * 60)
        print(f"MCP Server: {os.getenv('MCP_SERVER_URL', 'http://127.0.0.1:8703/mcp')}")
        print(f"商品: {os.getenv('MCP_PRODUCT_NAME')}")
        if os.getenv("MCP_SELLER_NAME"):
            print(f"商家: {os.getenv('MCP_SELLER_NAME')}")
        print(f"平台: {os.getenv('MCP_APPS', '美团,京东外卖,淘宝闪购')}")
        print(f"最大步数: {os.getenv('MCP_MAX_STEPS', '100')}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("Order Wise MCP Client 示例 - 交互式模式")
        print("=" * 60)
        print("\n提示: 可通过环境变量进行脚本化使用:")
        print("  MCP_SERVER_URL=http://127.0.0.1:8703/mcp")
        print("  MCP_PRODUCT_NAME=商品名称")
        print("  MCP_SELLER_NAME=商家名称（可选）")
        print("  MCP_APPS=美团,京东外卖,淘宝闪购")
        print("  MCP_MAX_STEPS=100")
        print("  MCP_MODEL_PROVIDER=local")
        print("=" * 60)
    
    # 连接错误会自然传播，显示错误信息
    try:
        asyncio.run(example_compare_prices())
    except (RuntimeError, ConnectionError) as e:
        error_msg = str(e)
        if "failed to connect" in error_msg.lower() or "connection" in error_msg.lower():
            print(f"\n连接失败: {error_msg}")
            print(f"请检查 MCP Server 是否正在运行: {os.getenv('MCP_SERVER_URL', 'http://127.0.0.1:8703/mcp')}")
            sys.exit(1)
        raise
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)

