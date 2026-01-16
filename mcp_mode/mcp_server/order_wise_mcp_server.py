"""Order Wise MCP Server - Price comparison tool for food delivery platforms."""

import asyncio
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from typing import Annotated, Dict, List, Optional
from pydantic import Field

from mcp_mode.mcp_server.order_wise_mcp_backend import compare_prices_backend, load_mcp_config

# Note: Task cancellation is limited because run_parallel_tasks uses multiprocessing.Process
# These processes are independent and cannot be cancelled from the parent process
# When client disconnects, the processes will continue running until completion


mcp = FastMCP(
    name="Order-Wise-MCP",
    instructions="""
    Order Wise MCP Server provides tools to compare prices across multiple food delivery platforms.
    Use compare_prices to search for products and compare prices on Meituan, JD Waimai, and Taobao Shangou.
    """
)


@mcp.custom_route(path="/", methods=["GET"])
async def health_check(request):
    """Health check endpoint for root path."""
    return JSONResponse({
        "status": "ok",
        "service": "Order-Wise-MCP",
        "endpoint": "/mcp"
    })




@mcp.tool
async def compare_prices(
    product_name: Annotated[str, Field(description="Product name to search, e.g., '瑞幸咖啡'")],
    seller_name: Annotated[Optional[str], Field(description="Optional seller name, e.g., '瑞幸咖啡'")] = None,
    apps: Annotated[Optional[List[str]], Field(description="List of platforms to compare. If not provided, uses default_apps from server_config.yaml")] = None,
    max_steps: Annotated[Optional[int], Field(description="Maximum steps per platform. If not provided, uses value from server_config.yaml")] = None,
    task_id: Annotated[Optional[str], Field(description="Optional task ID. If not provided, will be auto-generated.")] = None,
    user_id: Annotated[Optional[str], Field(description="Optional user ID. If not provided, uses default 'mcp_user'.")] = None,
    model_provider: Annotated[Optional[str], Field(description="Model provider name from model_config.yaml. If not provided, uses default_provider from server_config.yaml")] = None,
    device_mapping: Annotated[Optional[Dict[str, str]], Field(description="Device mapping dictionary, e.g., {'app1': 'device_id_1', 'app2': 'device_id_2'}. If not provided, uses app_device_mapping.json.")] = None,
    session_id: Annotated[Optional[str], Field(description="Session ID to continue a previously interrupted task (when takeover was triggered). Must provide reply_from_client if using this.")] = None,
    reply_from_client: Annotated[Optional[str], Field(description="Reply from client to continue a task after takeover. Must provide session_id if using this.")] = None,
) -> dict:
    """
    Compare prices across multiple food delivery platforms.
    
    This tool searches for a product on multiple platforms (Meituan, JD Waimai, Taobao Shangou)
    in parallel and returns structured price comparison results.
    
    **Sync Mode (MCP)**: Uses synchronous takeover mode. When agent encounters login/verification,
    it immediately returns with session_id. Use session_id and reply_from_client to continue.
    
    Args:
        product_name: Product name to search (required)
        seller_name: Optional seller name to narrow down search
        apps: List of platforms to compare. If not provided, uses default_apps from server_config.yaml
        max_steps: Maximum steps per platform execution. If not provided, uses default_max_steps from server_config.yaml
        task_id: Optional task ID. If not provided, will be auto-generated.
        user_id: Optional user ID. If not provided, uses default 'mcp_user'.
        model_provider: Model provider name from model_config.yaml. If not provided, uses default_provider from server_config.yaml
        device_mapping: Device mapping dictionary, e.g., {'app1': 'device_id_1', 'app2': 'device_id_2'}.
            If not provided, uses app_device_mapping.json.
        session_id: Session ID to continue a previously interrupted task (when takeover was triggered).
            Must provide reply_from_client if using this.
        reply_from_client: Reply from client to continue a task after takeover.
            Must provide session_id if using this.
    
    Returns:
        Dictionary containing:
        - product_name: Product name searched
        - seller_name: Seller name (if provided)
        - task_id: Task ID
        - platforms: List of platform results with price information
        - summary: Summary statistics including best price
        
        If takeover is triggered (sync mode):
        - session_id: Session ID for continuing the task
        - stop_reason: "INFO_ACTION_NEEDS_REPLY"
        - message: Message from agent requesting intervention
    
    Note:
        MCP mode uses synchronous takeover: when agent encounters login/verification screens,
        it immediately returns with session_id. To continue, call this tool again with the
        same parameters plus session_id and reply_from_client.
    """
    # Load configuration to get defaults
    config = load_mcp_config()
    
    # Generate task_id if not provided
    import uuid
    if not task_id:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
    
    # Run task in executor to avoid blocking
    loop = asyncio.get_event_loop()
    try:
        # Run in thread pool to avoid blocking the event loop
        result = await loop.run_in_executor(
            None,
            lambda: compare_prices_backend(
                product_name=product_name,
                seller_name=seller_name,
                apps=apps or config["search"]["default_apps"],
                max_steps=max_steps,
                task_id=task_id,
                user_id=user_id,
                model_provider=model_provider or config["model"]["default_provider"],
                mongodb_connection_string=None,  # MCP mode: always None for sync mode
                device_mapping=device_mapping,
                session_id=session_id,
                reply_from_client=reply_from_client,
            )
        )
        return result
    except asyncio.CancelledError:
        # Client disconnected
        print(f"[MCP警告] 客户端断开连接，任务 {task_id} 将继续在后台运行（使用 multiprocessing.Process）")
        # Note: run_parallel_tasks uses multiprocessing.Process which cannot be cancelled
        # The processes will continue running until completion
        raise


if __name__ == "__main__":
    # Load configuration from server_config.yaml
    config = load_mcp_config()
    server_config = config["server"]
    
    host = server_config["host"]
    port = server_config["port"]
    
    print(f"[MCP Server] 启动服务器: {host}:{port}")
    print(f"[MCP Server] 配置文件: mcp_mode/mcp_server/server_config.yaml")
    
    # Listen on configured host and port
    mcp.run(transport="http", host=host, port=port)

