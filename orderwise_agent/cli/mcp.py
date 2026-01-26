"""MCP 模式比价 CLI 命令"""

import sys
from orderwise_agent import compare_prices
from orderwise_agent.cli.utils import parse_apps_and_devices, print_result

def run_mcp(args):
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

