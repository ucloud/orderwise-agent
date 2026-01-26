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

* **[2026-01-23]** 📦 **PyPI Package Released**: OrderWise-Agent is now available on PyPI! Install it quickly with `pip install orderwise-agent`.
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

### Demo 1 - MCP Mode Invocation

Call the `compare_prices` tool function via MCP protocol to achieve standardized price comparison interface.

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_mode_demo.gif" height="400" alt="MCP Mode Demo"/>
      <br/>MCP Call: compare_prices(product_name="茉莉花香拿铁", apps=["Meituan", "JD Waimai", "Taobao Instant Buy"])
      <br/>Start: bash start-mcp-server-tmux.sh (recommended) or bash start-mcp-server.sh
    </td>
  </tr>
</table>

### Demo 2 - Official Experience - Listener Mode

Leverage the parallel execution engine to execute price comparison tasks on three platforms simultaneously, significantly reducing execution time.

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/official_listener_mode_demo.gif" height="400" alt="Official Listener Mode Demo"/>
      <br/>Official Listener Mode Demo
    </td>
  </tr>
</table>

**Usage Instructions**:
- **Page Reference**: <u>**Xiaomi**</u> (Search Entry Page) | <u>**Xiaoxuan**</u> (PhoneAgent Execution Page); Users can enter any food delivery product they want to compare prices for in the search box. At any time, users can click **"我来操作"** (I'll handle it) to interrupt the search. Once the operation is completed, the Agent will automatically resume execution.
- **Account Login**: On the **Xiaoxuan** page, follow the logo hints to sign in to your personal accounts on JD Waimai, Taobao Instant Buy, and Meituan.
- **Address Configuration**: Please configure the delivery address on each platform on the **Xiaoxuan** page before use, otherwise it may result in no search results.
- **Seller name is optional**: For products available from multiple sellers (e.g., "Orange Peel Latte"), it's recommended to include the seller name (e.g., "Manner Orange Peel Latte") to ensure accurate price comparison; for unique products ("归云南" - default belongs to "CHAGEE"), it's not required.


## Quick Start (MCP Mode - For Personal Usage)

**Step 1: Python Package Installation**
```bash
pip install orderwise-agent
```

> **Note**: Use hyphen `orderwise-agent` for installation, but use underscore `import orderwise_agent` for import. 

**Step 2: Connect Cloud Phones**
```bash
# Install ADB (if not already installed)
brew install android-platform-tools  # macOS
# Or visit https://developer.android.com/tools/releases/platform-tools

# Connect Android cloud phone
adb connect your-cloud-phone-ip:port
adb devices  # Verify connection
```

**Step 3: Configure Model Service**

**Option 1: Use Zhipu Official API (Recommended)**
```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"  # Apply at [Zhipu Platform](https://docs.bigmodel.cn/cn/api/introduction)
```

**Option 2: Use Self-Deployed Model Service**
```bash
export ORDERWISE_MODEL_URL="http://your-model-server:port/v1"  # Model service address
export ORDERWISE_MODEL_NAME="autoglm-phone-9b"                 # Model name
```

**Step 4: Run**
```bash
orderwise-agent mcp "茉莉花香拿铁" --seller "瑞幸" --apps 美团=云手机1-ip 京东外卖=云手机2-ip 淘宝闪购=云手机3-ip
```

---

## Listener Mode - For Production Environment

> **Note**: If you have already completed steps 2-3 of [Quick Start (MCP Mode)](#quick-start-mcp-mode---for-personal-usage) (connecting cloud phones and configuring model service), you can continue configuring Listener mode based on that. Mainly need to configure MongoDB and device mapping additionally.

### 1. Installation

**Install from Source**

```bash
git clone https://github.com/ucloud/orderwise-agent.git
cd orderwise-agent
pip install -r requirements.txt  # Or use uv: uv pip install -r requirements.txt (uv needs to be installed first)
pip install -e .  # Or use uv: uv pip install -e . (uv needs to be installed first)
```

### 2. Configure Devices

> **Note**: If you have already completed step 2 of [Quick Start (MCP Mode)](#quick-start-mcp-mode---for-personal-usage) (connecting cloud phones), you can skip the device connection step and directly configure device mapping. If devices are not connected yet, please refer to step 2 of Quick Start.

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


### 3. Model Configuration

> **Note**: If you have already completed step 3 of [Quick Start (MCP Mode)](#quick-start-mcp-mode---for-personal-usage) (configuring model service), you can skip the model service configuration and only need to configure MongoDB additionally.

**Local vLLM Deployment** (If choosing self-deployed model service, refer to [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)):

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


**MongoDB Configuration** (Required):
```bash
export MONGODB_CONNECTION_STRING="mongodb://user:password@host:port/?replicaSet=rs0"
```

### 4. Run Agent

#### Listener Mode (Production)

```bash
bash start-listener.sh
```

**Features**: Continuous running, high concurrency, task queue persistence (MongoDB), asynchronous Takeover

---

## Sandbox Deployment (MCP Mode - Cloud Environment)

Deploy MCP server on UCloud Sandbox, no local environment required:

```bash
# Install Sandbox SDK
pip install ucloud_sandbox

cd sandbox
python build_template.py      # Build Template and create Sandbox
python configure_sandbox.py   # Configure devices and model service
python compare_prices.py      # Use price comparison tool
```

**Benefits**: MCP server runs in cloud sandbox, configure external device and model service connections via `configure_sandbox.py`, no need to run server locally, deploy in seconds, cloud-based execution without consuming local resources, pay-as-you-go pricing.

Detailed documentation: See [sandbox/README.md](sandbox/README.md)

---

## Two Mode Call Flows

### MCP Mode (Personal Usage)

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_workflow.png" alt="MCP Mode Architecture Diagram" style="max-width: 100%; height: auto;"/>
      <br/>MCP Mode Architecture Workflow
    </td>
  </tr>
</table>

**Tool Function**: `compare_prices` - Multi-platform price comparison tool (see [Demo 1](#demo-1---mcp-mode-invocation))

**Takeover**: Agent → Throw Exception → Return session_id → User Reply → Resume Execution

### Listener Mode (Production)

```
Business System → MongoDB(tasks) → MongoDBListener → on_new_task → ParallelExecutor
  ↓                                                              ↓
MongoDB(results) ← Async Write ← Meituan/JD/Taobao Agent (Parallel Execution)
```

**Takeover**: Agent → MongoDB(takeover) → Polling Wait → User Reply → Continue Execution

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

> **Note**: If you have already completed steps 1-3 of [Quick Start (MCP Mode)](#quick-start-mcp-mode---for-personal-usage) (installation, connecting cloud phones, configuring model service), the `base_url` and `model` in the yaml configuration will be automatically read from environment variables, no modification needed.

Edit `benchmark/configs/framework_configs/orderwise.yaml`:

```yaml
base_url: "http://localhost:4244/v1"  # Use 4244 for local deployment, customize port for remote server (if environment variables are not set)
model: "autoglm-phone-9b"  # If environment variables are not set
apps_config_path: "examples/apps_config.json"
app_device_mapping_path: "examples/app_device_mapping.json"
```

**Run Benchmark Evaluation**:

```bash
cd benchmark
python runner.py          # Interactive mode
python runner.py --batch  # Batch execution
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
