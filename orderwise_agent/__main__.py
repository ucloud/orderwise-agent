"""CLI entry point for OrderWise-Agent"""

import sys
import argparse
from orderwise_agent import __version__

def main():
    parser = argparse.ArgumentParser(
        prog="orderwise-agent",
        description="OrderWise-Agent - 智能外卖比价 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  orderwise-agent mcp "茉莉花香拿铁" --apps 美团=device1-id 京东外卖=device2-id 淘宝闪购=device3-id
  orderwise-agent mcp "茉莉花香拿铁" --seller "瑞幸" --apps 美团=device1-id 京东外卖=device2-id
  orderwise-agent mcp "茉莉花香拿铁" --apps 美团=device1-id 淘宝闪购=device3-id
  orderwise-agent mcp-server --once "茉莉花香拿铁" --apps 美团=device1-id 京东外卖=device2-id
  orderwise-agent mcp-server
        """
    )
    parser.add_argument("--version", action="version", version=f"orderwise-agent {__version__}")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令", metavar="COMMAND")
    
    # mcp 子命令
    mcp_compare_parser = subparsers.add_parser("mcp", help="多平台外卖比价（MCP模式）")
    mcp_compare_parser.add_argument("product", help="商品名称")
    mcp_compare_parser.add_argument("--seller", help="商家名称（可选）")
    mcp_compare_parser.add_argument("--apps", nargs="+", required=True, help="比价平台和设备映射（必需），格式：--apps 美团=device1-id 京东外卖=device2-id")
    mcp_compare_parser.add_argument("--max-steps", type=int, default=100, help="最大执行步数")
    
    # mcp-server 子命令
    mcp_parser = subparsers.add_parser("mcp-server", help="启动 MCP 服务器")
    mcp_parser.add_argument("--port", type=int, default=8703, help="服务器端口")
    mcp_parser.add_argument("--host", default="0.0.0.0", help="服务器地址")
    mcp_parser.add_argument("--once", action="store_true", help="一次性执行比价任务（不启动服务器）")
    mcp_parser.add_argument("product", nargs="?", help="商品名称（--once 模式下必需）")
    mcp_parser.add_argument("--seller", help="商家名称（可选）")
    mcp_parser.add_argument("--apps", nargs="+", help="比价平台和设备映射（--once 模式下必需），格式：--apps 美团=device1-id 京东外卖=device2-id")
    mcp_parser.add_argument("--max-steps", type=int, default=100, help="最大执行步数")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "mcp":
        from orderwise_agent.cli.mcp import run_mcp
        run_mcp(args)
    elif args.command == "mcp-server":
        from orderwise_agent.cli.mcp_server import run_mcp_server
        run_mcp_server(args)

if __name__ == "__main__":
    main()

