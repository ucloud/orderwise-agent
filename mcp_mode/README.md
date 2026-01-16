# OrderWise MCP (Model Context Protocol) 模块

本目录包含 OrderWise MCP Server 和 MCP Client 相关的代码和配置。

OrderWise MCP 是一个基于 Model Context Protocol 的比价服务，支持在多个外卖平台（美团、京东外卖、淘宝闪购）上并行搜索商品并比较价格。

## 目录结构

```
mcp_mode/
├── mcp_server/          # MCP Server 服务端代码
│   ├── __init__.py
│   ├── server_config.yaml      # MCP Server 配置文件
│   ├── app_device_mapping.json # 设备映射配置
│   ├── order_wise_mcp_server.py    # MCP Server 主程序
│   ├── order_wise_mcp_backend.py  # MCP Server 后端实现
│   └── session_manager.py      # 会话管理器
│
└── mcp_client/          # MCP Client 客户端代码和示例
    └── mcp_client_example.py    # MCP Client 使用示例
```

## 快速开始

### 启动 MCP Server

**标准启动**：
```bash
bash start-mcp-server.sh
```

**tmux 分列启动（推荐）**：
```bash
bash start-mcp-server-tmux.sh
```
在 tmux 中启动，按美团/京东外卖/淘宝闪购分3列显示日志，方便调试。

### 使用 MCP Client

**Python 示例**:
```bash
python mcp_mode/mcp_client/mcp_client_example.py
```

## 配置

主要配置文件：
- `mcp_mode/mcp_server/server_config.yaml` - MCP Server 主配置（服务器、Agent、MongoDB等）
- `env.sh` - 模型服务配置（与 Listener 模式统一，需 `source env.sh` 使其生效）
- `mcp_mode/mcp_server/app_device_mapping.json` - 设备映射配置（app1/app2/app3 → device_id）
