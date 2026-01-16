# OrderWise MCP 在 UCloud Sandbox 上部署和使用

本目录提供 OrderWise-Agent 的 Sandbox Template，用于在 UCloud Sandbox 上快速部署 OrderWise MCP 服务器。

## 前置要求

- UCloud Sandbox 账号和 API Key（访问 [UCloud Sandbox](https://sandbox.ucloudai.com)）
- 至少 3 台 Android 云手机（已开启 ADB 调试）
- 已部署的模型服务（vLLM 或智谱 API）
- Python 3.10+ 和 `fastmcp`（仅本地 Client 端需要）

## 快速开始

### 1. 获取 API Key

1. 访问 [UCloud Sandbox](https://sandbox.ucloudai.com) 注册账号
2. 在控制台获取 API Key
3. 设置环境变量：

```bash
export AGENTBOX_API_KEY=your_api_key
```

### 2. 安装依赖

```bash
pip install ucloud_sandbox
```

### 3. 构建 OrderWise Sandbox Template 并部署

使用 `build_template.py` 构建 OrderWise 专用的 Sandbox Template：

```bash
python build_template.py
```

脚本会自动构建 `orderwise_sandbox` Template、创建 Sandbox 并复制项目文件。

### 4. 配置 Sandbox

```bash
# 使用智谱 API（推荐使用环境变量）
export ZHIPU_API_KEY=your-zhipu-api-key
python configure_sandbox.py \
  --sandbox-id <your_sandbox_id> \
  --devices <ip1:port> <ip2:port> <ip3:port> \
  --adbkey ~/.android/adbkey

# 使用本地 vLLM
python configure_sandbox.py \
  --sandbox-id <your_sandbox_id> \
  --devices <ip1:port> <ip2:port> <ip3:port> \
  --model-provider local \
  --model-api-base "http://your-model-server:4244/v1" \
  --model-name "autoglm-phone-9b" \
  --adbkey ~/.android/adbkey
```

## 使用比价工具

### 服务器地址

MCP 服务器地址格式：`http://{port}-{sandbox_id}.sandbox.ucloudai.com/mcp`

例如：`http://8703-{your_sandbox_id}.sandbox.ucloudai.com/mcp`

### 使用示例

```bash
# 交互式使用
python compare_prices.py

# 或通过环境变量配置
export MCP_SERVER_URL=http://8703-{your_sandbox_id}.sandbox.ucloudai.com/mcp
export MCP_PRODUCT_NAME=瑞幸生椰拿铁
python compare_prices.py
```

### 在代码中使用

```python
import asyncio
import json
from fastmcp import Client

async def compare_prices():
    client = Client("http://8703-{your_sandbox_id}.sandbox.ucloudai.com/mcp", timeout=600.0)
    async with client:
        result = await client.call_tool("compare_prices", {
            "product_name": "生椰拿铁",
            "seller_name": "瑞幸",  # 可选
            "apps": ["美团", "京东外卖", "淘宝闪购"],  # 可选
            "max_steps": 100  # 可选
        })
        result_data = json.loads(result.content[0].text)
        print(json.dumps(result_data, indent=2, ensure_ascii=False))

asyncio.run(compare_prices())
```

### 工具参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `product_name` | string | 是 | 商品名称 |
| `seller_name` | string | 否 | 商家名称 |
| `apps` | list[string] | 否 | 平台列表（默认：全部） |
| `max_steps` | int | 否 | 最大执行步数（默认：100） |
| `session_id` | string | 否 | 会话 ID（用于继续任务） |
| `reply_from_client` | string | 否 | 客户端回复（用于继续任务） |

### 处理用户交互

当 Agent 需要用户操作（如登录、验证码）时，会返回：

```json
{
  "stop_reason": "INFO_ACTION_NEEDS_REPLY",
  "session_id": "session_xxx",
  "message": "需要用户登录"
}
```

继续任务时，使用相同的参数加上 `session_id` 和 `reply_from_client`。

## Sandbox 管理

### 动态调整存活时间

Sandbox 默认存活时间为 20 分钟，可通过 `set_timeout` 动态延长：

```python
from ucloud_sandbox import Sandbox

sandbox = Sandbox.get(sandbox_id="your_sandbox_id")
sandbox.set_timeout(3600)  # 延长到 60 分钟（从当前时间点重新计算）
```

**注意**：每次调用 `set_timeout` 时，剩余寿命将从当前时间点开始重新计算。

## 查看日志和状态

```bash
python view_logs.py <sandbox_id> [--startup|--tail|--check]  # 查看项目日志/启动日志/实时跟踪/检查状态
```

## 故障排查

- **连接失败**: 检查服务器地址、Sandbox 状态和网络连接
- **工具调用超时**: 增加 `timeout` 参数，检查服务器日志
- **ADB 连接失败**: `adb kill-server && adb start-server`
- **MCP 服务器无法启动**: 查看启动日志 `/tmp/mcp_server.log`

## 参考

- [UCloud Sandbox Python SDK](https://github.com/ucloud/ucloud-sandbox-sdk-python)
- [OrderWise 项目](https://github.com/ucloud/orderwise-agent)
- [OrderWise MCP文档](https://github.com/ucloud/orderwise-agent/mcp_mode)
- [FastMCP 文档](https://gofastmcp.com)
