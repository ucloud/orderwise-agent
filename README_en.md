<div align="center">

<img src="docs/orderwise_logo.jpg" alt="OrderWise-Agent" width="150">

# OrderWise-Agent

<p align="center">
<b>Make Every Penny Count.</b>
</p>

An intelligent food delivery price comparison agent based on AutoGLM, focusing on multi-platform parallel price comparison and structured price extraction.


English | [简体中文](README.md)

<br/>
  <a href="docs/WECHAT.md" target="_blank">
    <strong>Join our WeChat Discussion Group</strong>
  </a>

</div>

## 📰 News

* **[2026-01-15]** 🌐 **Official Website Live**: Our official [website](https://ucloud.github.io/orderwise/index.html) is now live!

### Core Features

- ✅ **Parallel Execution**: Multiple devices/apps execute simultaneously, execution time is the maximum rather than cumulative
- ✅ **Device Management**: Cloud phone health monitoring, automatic reconnection
- ✅ **Price Extraction**: Structured extraction of item price, delivery fee, packaging fee, and total price
- ✅ **Active Takeover**: Users can interrupt the search at any time. Once the operation is completed, the Agent will automatically resume execution
- ✅ **MongoDB Integration**: Task queue management, result storage, device mapping, asynchronous writes
- ✅ **MCP Mode**: Cross-platform tool integration, standardized tool calling interface, synchronous/asynchronous Takeover, session management
- ✅ **Benchmark Framework**: Performance evaluation and optimization effectiveness verification

## Performance Metrics

AutoGLM is the world's first productized mobile agent (Mobile-Use Agent) launched by Zhipu AI, with excellent visual understanding, task planning, and error recovery capabilities. We chose [AutoGLM](https://github.com/zai-org/Open-AutoGLM) as the foundation framework and conducted deep customization and optimization for the food delivery price comparison scenario, including core features such as parallel execution engine, structured price extraction, and device management. In benchmark tests under the same hardware and model service environment (5 tasks), the optimized system performance is as follows:

| Metric | Baseline(AutoGLM) | OrderWise-Agent | Improvement |
|--------|------------------|----------------|-------------|
| **Avg Execution Time** | 151.38s | 65.25s | **56.90%** ⬆️ |
| **Success Rate** | 80.00% (4/5) | 100.00% (5/5) | **25.00%** ⬆️ |
| **Price Extraction Accuracy** | 80.00% | 100.00% | **25.00%** ⬆️ |

## Real-World Demos

## Usage Tips

**Page Reference**: Xiaomi (Search Entry Page) | Xiaoxuan (PhoneAgent Execution Page)

Users can enter any food delivery product they want to compare prices for in the search box. At any time, users can click "我来操作" (I'll handle it) to interrupt the search. Once the operation is completed, the Agent will automatically resume execution.

**Notes**:

1. **Address Configuration**: Please configure the delivery address on each platform on the **Xiaoxuan** page before use, otherwise it may result in no search results.

2. **Seller name is optional**: For products available from multiple sellers (e.g., "Orange Peel Latte"), it's recommended to include the seller name (e.g., "Manner Orange Peel Latte") to ensure accurate price comparison; for unique products ("归云南" - default belongs to "CHAGEE"), it's not required.

### Demo 1 - Official Experience - Listener Mode

Leverage the parallel execution engine to execute price comparison tasks on three platforms simultaneously, significantly reducing execution time.

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/official_listener_mode_demo.gif" height="400" alt="Official Listener Mode Demo"/>
      <br/>Official Listener Mode Demo
    </td>
  </tr>
</table>

### Demo 2 - MCP Mode Invocation

Call the `compare_prices` tool function via MCP protocol to achieve standardized price comparison interface.

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_mode_demo.gif" height="400" alt="MCP Mode Demo"/>
      <br/>MCP Call: compare_prices(product_name="茉莉花香拿铁", apps=["Meituan", "JD Waimai", "Taobao Instant Buy"])
    </td>
  </tr>
</table>


## Quick Start

### 1. Environment Setup

```bash
git clone https://github.com/ucloud/orderwise-agent.git
cd orderwise-agent
pip install -r requirements.txt  # Or use uv: uv pip install -r requirements.txt (uv needs to be installed first)
pip install -e .  # Or use uv: uv pip install -e . (uv needs to be installed first)
```

### 2. Configure Devices

#### 2.1 Connect Android Devices

**Install ADB tools**:
```bash
# macOS
brew install android-platform-tools

# Linux / Windows
# Manual download: https://developer.android.com/tools/releases/platform-tools
```

**Connect devices** (choose based on your device type):

- **Android Cloud Phone** (Recommended):
```bash
adb connect your-cloud-phone-ip:port
```

- **Physical Android Device**:
```bash
# 1. Connect phone via USB cable
# 2. Tap "Allow USB debugging" on phone
```

**Verify connection** (for all device types):
```bash
adb devices
```

#### 2.2 Mode-Specific Configuration

Configure device mapping based on the mode you use:

**Listener Mode (Production)**

Device mapping is primarily read from MongoDB's `device_mapping` collection.

System check device list: Edit `phone_agent/config/listener_devices.py`:

```python
LISTENER_DEVICES = [
    "your-cloud-phone-ip:port-1",
    "your-cloud-phone-ip:port-2",
    "your-cloud-phone-ip:port-3",
    # ... add more Android cloud phones
    # Note: The number of Android cloud phones/physical phones should be a multiple of the number of apps to compare (e.g., 3 platforms require a multiple of 3)
]
```

**MCP Mode / Benchmark Mode**

Edit `examples/app_device_mapping.json`:

```json
{
  "app1": "your-cloud-phone-ip:port",  # Android cloud phone for Meituan
  "app2": "your-cloud-phone-ip:port",  # Android cloud phone for JD Waimai
  "app3": "your-cloud-phone-ip:port"    # Android cloud phone for Taobao Instant Buy
}
```

### 3. Model Configuration

#### 3.1 Listener Mode Configuration

**Listener Mode** uses the `env.sh` file to configure the model service (run `source env.sh` to take effect):

**MongoDB Configuration** (Required):
```bash
export MONGODB_CONNECTION_STRING="mongodb://user:password@host:port/?replicaSet=rs0"
```

**Model Service Configuration**:

**Option 1: Zhipu Official API**
```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"  # Apply at [Zhipu Platform](https://docs.bigmodel.cn/cn/api/introduction)
export PHONE_AGENT_MAX_STEPS="100"
```

**Option 2: Local vLLM Deployment** (Refer to [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM))

1. **Start vLLM Service** (configure port):
```bash
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b \
  --allowed-local-media-path / \
  --mm-encoder-tp-mode data \
  --mm_processor_cache_type shm \
  --mm_processor_kwargs "{\"max_pixels\":5000000}" \
  --max-model-len 25480 \
  --chat-template-content-format string \
  --limit-mm-per-prompt "{\"image\":10}" \
  --model zai-org/AutoGLM-Phone-9B \
  --port 4244  # ← Configure service port (use 4244 for local, customize for remote server)
```

2. **Configure Agent Connection** (edit `env.sh`):
```bash
# Local deployment: use localhost
export PHONE_AGENT_BASE_URL="http://localhost:4244/v1"

# Remote server: use server IP
# export PHONE_AGENT_BASE_URL="http://your-server-ip:4244/v1"

export PHONE_AGENT_MODEL="autoglm-phone-9b"
export PHONE_AGENT_MAX_STEPS="100"
```

#### 3.2 MCP Mode Configuration

**MCP Mode** uses the `env.sh` file to configure the model service (unified with Listener Mode, run `source env.sh` to take effect):

```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"
export PHONE_AGENT_MAX_STEPS="100"
```

**Note**:
- MCP Mode and Listener Mode use the same `env.sh` configuration for unified management

### 4. Run Agent

#### Listener Mode (Production)

```bash
bash start-listener.sh
```

**Features**: Continuous running, high concurrency, task queue persistence (MongoDB), asynchronous Takeover

#### MCP Mode (Personal Experience)

**Local Deployment**:

**Standard Start**:
```bash
bash start-mcp-server.sh
```

**tmux Split Start (Recommended)**:
```bash
bash start-mcp-server-tmux.sh
```
Start in tmux, display logs in 3 columns by Meituan/JD Waimai/Taobao Instant Buy for easy debugging.

**Sandbox Deployment** (Cloud Environment):

Deploy MCP server on UCloud Sandbox, no local environment required:

```bash
# Install Sandbox SDK (if using Sandbox deployment)
pip install ucloud_sandbox

cd sandbox
python build_template.py      # Build Template and create Sandbox
python configure_sandbox.py   # Configure devices and model service
python compare_prices.py      # Use price comparison tool
```

**Benefits**: MCP server runs in cloud sandbox, configure external device and model service connections via `configure_sandbox.py`, no need to run server locally, deploy in seconds, cloud-based execution without consuming local resources, pay-as-you-go pricing.

Detailed documentation: See [sandbox/README.md](sandbox/README.md)

**Features**: Lightweight, no MongoDB required, synchronous calls, instant response

**Tool Function**: MCP mode provides the `compare_prices` tool function, supporting multi-platform price comparison via MCP protocol.

**Using MCP Client**:

```bash
python mcp_mode/mcp_client/mcp_client_example.py
```

#### Benchmark Evaluation

```bash
cd benchmark
python runner.py          # Interactive mode
python runner.py --batch  # Batch execution
```

## Two Mode Call Flows

### Listener Mode (Production)

```
Business System → MongoDB(tasks) → MongoDBListener → on_new_task → ParallelExecutor
  ↓                                                              ↓
MongoDB(results) ← Async Write ← Meituan/JD/Taobao Agent (Parallel Execution)
```

**Takeover**: Agent → MongoDB(takeover) → Polling Wait → User Reply → Continue Execution

### MCP Mode (Personal Experience)

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_workflow.png" alt="MCP Mode Architecture Diagram" style="max-width: 100%; height: auto;"/>
      <br/>MCP Mode Architecture Workflow
    </td>
  </tr>
</table>

**Tool Function**: `compare_prices` - Multi-platform price comparison tool, supports parameters:
- `product_name` (required): Product name
- `seller_name` (optional): Seller name
- `apps` (optional): Platform list, defaults to all
- `max_steps` (optional): Maximum execution steps
- `session_id` / `reply_from_client` (optional): For continuing interrupted tasks

**Takeover**: Agent → Throw Exception → Return session_id → User Reply → Resume Execution

## Directory Structure

```
orderwise-agent/
├── phone_agent/              # Core Agent implementation
│   ├── agent.py             # PhoneAgent main class
│   ├── config/              # Configuration files
│   │   └── prompts_zh.py    # ⭐ OrderWise system prompts (food delivery price comparison rules)
│   └── utils/               # Utility modules
│       ├── parallel_executor.py    # ⭐ OrderWise parallel execution engine
│       ├── price_extractor.py      # ⭐ OrderWise price extractor
│       ├── device_manager.py       # ⭐ OrderWise device manager
│       ├── mongodb_writer.py       # ⭐ OrderWise MongoDB writer
│       ├── mongodb_listener.py     # ⭐ OrderWise MongoDB listener
│       └── orderwise_logger.py     # ⭐ OrderWise log management
├── benchmark/               # ⭐ OrderWise Benchmark framework
├── mcp_mode/               # ⭐ OrderWise MCP mode support
├── sandbox/                 # ⭐ OrderWise Sandbox deployment tools
├── examples/               # Examples and configurations
│   ├── apps_config.json    # ⭐ OrderWise App instruction template config (app-specific task instruction templates)
│   └── app_device_mapping.json # ⭐ OrderWise device mapping config (app1/app2/app3 → device_id)
├── main.py                 # Main entry
├── env.sh                  # ⭐ OrderWise model service environment variable config
├── start-listener.sh       # ⭐ OrderWise start listener mode
├── start-mcp-server.sh     # ⭐ OrderWise start MCP service
└── start-mcp-server-tmux.sh # ⭐ OrderWise start MCP service (tmux split)
```

### Benchmark Configuration

Edit `benchmark/configs/framework_configs/orderwise.yaml`:

```yaml
base_url: "http://localhost:4244/v1"  # Use 4244 for local deployment, customize port for remote server
model: "autoglm-phone-9b"
apps_config_path: "examples/apps_config.json"
app_device_mapping_path: "examples/app_device_mapping.json"
```

### Supported Applications

| Application | Package Name | Version | Type |
|-------------|--------------|---------|------|
| **Meituan** | `com.sankuai.meituan` | 12.49.202 | Android App |
| **JD Waimai** | `com.jd.waimai` | 15.2.80 | Android App |
| **Taobao Instant Buy** | - | - | H5 Webpage ([https://m.tb.cn/](https://m.tb.cn/)) |

## Development Guide

### Adding New App Support

1. Add configuration in `examples/apps_config.json`
2. Add app type mapping in `phone_agent/utils/parallel_executor.py`
3. Update price extraction logic in `phone_agent/utils/price_extractor.py` (if needed)

### Extending Benchmark

1. Add task definitions in `benchmark/tasks/`
2. Add new metric calculations in `benchmark/core/metrics.py`
3. Update `benchmark/configs/benchmark_config.yaml`

## Reference Resources

| Document | Description |
|----------|-------------|
| [benchmark/README.md](benchmark/README.md) | Benchmark framework documentation (configuration, task design, evaluation metrics) |
| [mcp_mode/README.md](mcp_mode/README.md) | MCP mode documentation (configuration, usage examples) |
| [sandbox/README.md](sandbox/README.md) | Sandbox deployment documentation (UCloud Sandbox cloud deployment) |

## License

This project is based on [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) and follows the same license.

## Citation

If you find OrderWise-Agent helpful for your research, please consider citing our work:

```bibtex
@misc{orderwise_agent_2026,
  title={OrderWise-Agent: An Intelligent Multi-Platform Food Delivery Price Comparison Agent},
  author={OrderWise Team},
  year={2026},
  url={https://github.com/ucloud/orderwise-agent}
}
```

## Contact

For questions and support, please join our [WeChat discussion group](docs/WECHAT.md) or contact us:

Email: [orderwise.agent@gmail.com](mailto:orderwise.agent@gmail.com)
