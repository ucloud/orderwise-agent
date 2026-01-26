"""MCP 服务器 CLI 命令"""

import sys
from orderwise_agent.cli.utils import parse_apps_and_devices, print_result

def run_mcp_server(args):
    if args.once:
        if not args.product:
            print("错误: --once 模式下必须提供商品名称")
            sys.exit(1)
        
        if not args.apps:
            print("错误: --once 模式下必须通过 --apps 指定设备映射")
            sys.exit(1)
        
        from orderwise_agent import compare_prices
        
        try:
            apps_list, device_mapping = parse_apps_and_devices(args.apps)
        except ValueError as e:
            print(f"错误: {e}")
            sys.exit(1)
        
        result = compare_prices(
            product_name=args.product,
            seller_name=args.seller,
            apps=apps_list,
            max_steps=args.max_steps,
            device_mapping=device_mapping,
        )
        
        if not print_result(result):
            sys.exit(1)
    else:
        import uvicorn
        from mcp_mode.mcp_server.order_wise_mcp_server import mcp
        print(f"启动 MCP 服务器: http://{args.host}:{args.port}/mcp")
        uvicorn.run(mcp, host=args.host, port=args.port)

