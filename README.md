<div align="center">

<img src="docs/orderwise_logo.jpg" alt="OrderWise-Agent" width="150">

# OrderWise-Agent
<p align="center">
<b>Make Every Penny Count.</b>
</p>

基于 AutoGLM 的智能外卖比价agent，专注于多平台并行比价和结构化价格提取。

[English](README_en.md) | 简体中文

<br/>
  <a href="docs/WECHAT.md" target="_blank">
    <strong>欢迎加入讨论交流群</strong>
  </a>

</div>

## 📰 News

* **[2026-01-15]** 🌐 **官方网站上线**：我们的官方网站现已上线，访问 [网站](https://ucloud.github.io/orderwise/index.html) 了解更多信息。

### 核心功能

- ✅ **并行执行**：多设备/多app同时执行，执行时间取最大值而非累加
- ✅ **设备管理**：云手机健康监控、自动重连
- ✅ **价格提取**：结构化提取商品单价、配送费、打包费、总价
- ✅ **主动接管**：用户可以在任意时间中断搜索，待操作完成后，Agent 会自动恢复执行
- ✅ **MongoDB 集成**：任务队列管理、结果存储、设备映射、异步写入
- ✅ **MCP 模式**：跨平台工具集成、标准化工具调用接口、会话管理
- ✅ **Benchmark 框架**：性能评估和优化效果验证

## 性能指标

AutoGLM 是智谱AI推出的全球首个产品化手机智能体（Mobile-Use Agent），具备出色的视觉理解、任务规划和错误恢复能力。我们选择 [AutoGLM](https://github.com/zai-org/Open-AutoGLM) 作为基础框架，在此基础上针对外卖比价场景进行了深度定制和优化，包括并行执行引擎、结构化价格提取、设备管理等核心功能。在相同硬件和模型服务环境下的 Benchmark 测试中（5个任务），优化后的系统性能表现如下：

| 指标 | Baseline(AutoGLM) | OrderWise-Agent | 提升 |
|------|------------------|----------------|------|
| **平均执行时间** | 151.38s | 65.25s | **56.90%** ⬆️ |
| **任务成功率** | 80.00% (4/5) | 100.00% (5/5) | **25.00%** ⬆️ |
| **价格提取准确率** | 80.00% | 100.00% | **25.00%** ⬆️ |

## 真实世界演示

### 使用指南

**页面说明**：<u>**小觅**</u>（搜索入口页面）| <u>**小选**</u>（PhoneAgent执行页面）

用户可以在搜索框输入任意想要比价的外卖商品。

用户可以在任意时间点击**我来操作**中断搜索，待操作完成后，Agent 会自动恢复执行。

**注意**：
1. **账号登录**: 在**小选**页面根据Logo的提示登录京东外卖、淘宝闪购和美团的个人账号

2. **地址配置**：使用前请先在**小选**页面配置各外卖平台的配送地址，否则可能导致搜索无结果。

3. **商家名称可选**：多个商家都有的商品（如"橘皮拿铁"）建议包含商家名称（如"Manner橘皮拿铁"）以确保比价准确；独有商品（"归云南"默认属于"霸王茶姬"）无需提供。

### Demo 1 - 官方体验版 - Listener 模式

利用并行执行引擎，同时在三个平台执行比价任务，大幅缩短执行时间。

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/official_listener_mode_demo.gif" height="400" alt="官方Listener模式演示"/>
      <br/>官方Listener模式演示
    </td>
  </tr>
</table>

### Demo 2 - MCP 模式调用

通过 MCP 协议调用 `compare_prices` 工具函数，实现标准化的比价接口。

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_mode_demo.gif" height="400" alt="MCP 模式演示"/>
      <br/>MCP 调用: compare_prices(product_name="茉莉花香拿铁", apps=["美团", "京东外卖", "淘宝闪购"])
    </td>
  </tr>
</table>


## 快速开始

### 1. 运行环境搭建

```bash
git clone https://github.com/ucloud/orderwise-agent.git
cd orderwise-agent
pip install -r requirements.txt  # 或使用 uv: uv pip install -r requirements.txt (需先安装uv)
pip install -e .  # 或使用 uv: uv pip install -e . (需先安装uv)
```

### 2. 配置设备

#### 2.1 连接 Android 设备

**安装 ADB 工具**：
```bash
# macOS
brew install android-platform-tools

# Linux / Windows
# 手动下载：https://developer.android.com/tools/releases/platform-tools
```

**连接设备**（根据你的设备类型选择）：

- **Android 云手机**（推荐）：
```bash
adb connect your-cloud-phone-ip:port
```

- **物理 Android 设备**：
```bash
# 1. 用数据线连接手机
# 2. 手机上点击「允许 USB 调试」
```

**验证连接**（所有设备类型）：
```bash
adb devices
```

#### 2.2 模式特定配置

根据你使用的模式，配置对应的设备映射：

**Listener 模式（生产环境）**

设备映射主要从 MongoDB 的 `device_mapping` collection 读取。

系统检查设备列表：编辑 `phone_agent/config/listener_devices.py`：

```python
LISTENER_DEVICES = [
    "your-cloud-phone-ip:port-1",
    "your-cloud-phone-ip:port-2",
    "your-cloud-phone-ip:port-3",
    # ... 添加更多 Android 云手机
    # 注意：Android 云手机/物理手机数量应为需要比较的 app 的个数的倍数（例如：3个平台需要3的倍数）
]
```

**MCP 模式 / Benchmark 模式**

编辑 `examples/app_device_mapping.json`：

```json
{
  "app1": "your-cloud-phone-ip:port",  # 用于美团的 Android 云手机
  "app2": "your-cloud-phone-ip:port",  # 用于京东外卖的 Android 云手机
  "app3": "your-cloud-phone-ip:port"    # 用于淘宝闪购的 Android 云手机
}
```

### 3. 模型配置

#### 3.1 Listener 模式配置

**Listener 模式**使用 `env.sh` 文件配置模型服务（需 `source env.sh` 使其生效）：

**MongoDB 配置**（必需）：
```bash
export MONGODB_CONNECTION_STRING="mongodb://user:password@host:port/?replicaSet=rs0"
```

**模型服务配置**：

**方式一：智谱官方 API**
```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"  # 在 [智谱平台](https://docs.bigmodel.cn/cn/api/introduction) 申请
export PHONE_AGENT_MAX_STEPS="100"
```

**方式二：本地部署 vLLM**（参考 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)）

1. **启动 vLLM 服务**（配置端口）：
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
  --port 4244  # ← 配置服务端口（本地用 4244，远程服务器可自定义）
```

2. **配置 Agent 连接**（编辑 `env.sh`）：
```bash
# 本地部署：使用 localhost
export PHONE_AGENT_BASE_URL="http://localhost:4244/v1"

# 远程服务器：使用服务器 IP
# export PHONE_AGENT_BASE_URL="http://your-server-ip:4244/v1"

export PHONE_AGENT_MODEL="autoglm-phone-9b"
export PHONE_AGENT_MAX_STEPS="100"
```

#### 3.2 MCP 模式配置

**MCP 模式**使用 `env.sh` 文件配置模型服务（与 Listener 模式统一，需 `source env.sh` 使其生效）：

```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"
export PHONE_AGENT_MAX_STEPS="100"
```

**注意**：
- MCP 模式和 Listener 模式使用相同的 `env.sh` 配置，统一管理

### 4. 运行Agent

#### Listener 模式（生产环境）

```bash
bash start-listener.sh
```

**特点**：持续运行、高并发、任务队列持久化（MongoDB）、异步接管(Takeover)

#### MCP 模式（个人体验）

**本地部署**：

**标准启动**：
```bash
bash start-mcp-server.sh
```

**tmux 分列启动 (推荐)**：
```bash
bash start-mcp-server-tmux.sh
```
在 tmux 中启动，按美团/京东外卖/淘宝闪购分3列显示日志，方便调试。

**Sandbox 部署**（云端环境）：

在 UCloud Sandbox 上部署 MCP 服务器，无需本地环境：

```bash
# 安装 Sandbox SDK（如果使用 Sandbox 部署）
pip install ucloud_sandbox

cd sandbox
python build_template.py      # 构建 Template 并创建 Sandbox
python configure_sandbox.py   # 配置设备和模型服务
python compare_prices.py      # 使用比价工具
```

**优势**：MCP 服务器在云端 sandbox 中运行，通过 `configure_sandbox.py` 配置外部设备与模型服务连接，无需本地运行服务器，几秒钟快速部署，云端运行不占用本地资源，按需计费成本可控。

详细文档：参见 [sandbox/README.md](sandbox/README.md)

**特点**：轻量级、无需 MongoDB、同步调用、即时响应

**工具函数**：MCP 模式提供 `compare_prices` 工具函数，支持通过 MCP 协议调用进行多平台比价。

**使用 MCP Client**：

```bash
python mcp_mode/mcp_client/mcp_client_example.py
```

#### Benchmark 评估

```bash
cd benchmark
python runner.py          # 交互模式
python runner.py --batch  # 批量执行
```

## 两种模式调用流程

### Listener 模式（生产环境）

```
业务系统 → MongoDB(tasks) → MongoDBListener → on_new_task → ParallelExecutor
  ↓                                                              ↓
MongoDB(results) ← 异步写入 ← 美团/京东/淘宝 Agent (并行执行)
```

**接管(Takeover)**：Agent → MongoDB(takeover) → 轮询等待 → 用户回复 → 继续执行

### MCP 模式（个人体验）

<table align="center">
  <tr>
    <td align="center">
      <img src="docs/mcp_workflow.png" alt="MCP 模式架构图" style="max-width: 100%; height: auto;"/>
      <br/>MCP 模式架构流程图
    </td>
  </tr>
</table>

**工具函数**：`compare_prices` - 多平台比价工具，支持参数：
- `product_name`（必需）：商品名称
- `seller_name`（可选）：商家名称
- `apps`（可选）：平台列表，默认全部
- `max_steps`（可选）：最大执行步数
- `session_id` / `reply_from_client`（可选）：用于继续被中断的任务

**接管(Takeover)**：Agent → 抛出异常 → 返回 session_id → 用户回复 → 恢复执行

## 目录结构

```
orderwise-agent/
├── phone_agent/              # 核心 Agent 实现
│   ├── agent.py             # PhoneAgent 主类
│   ├── config/              # 配置文件
│   │   └── prompts_zh.py    # ⭐ OrderWise 系统提示词（外卖比价规则）
│   └── utils/               # 工具模块
│       ├── parallel_executor.py    # ⭐ OrderWise 并行执行引擎
│       ├── price_extractor.py      # ⭐ OrderWise 价格提取器
│       ├── device_manager.py       # ⭐ OrderWise 设备管理器
│       ├── mongodb_writer.py       # ⭐ OrderWise MongoDB 写入
│       ├── mongodb_listener.py     # ⭐ OrderWise MongoDB 监听
│       └── orderwise_logger.py     # ⭐ OrderWise 日志管理
├── benchmark/               # ⭐ OrderWise Benchmark 框架
├── mcp_mode/               # ⭐ OrderWise MCP 模式支持
├── sandbox/                 # ⭐ OrderWise Sandbox 部署工具
├── examples/               # 示例和配置
│   ├── apps_config.json    # ⭐ OrderWise App 指令模板配置（app独有的任务指令模板）
│   └── app_device_mapping.json # ⭐ OrderWise 设备映射配置（app1/app2/app3 → device_id）
├── main.py                 # 主入口
├── env.sh                  # ⭐ OrderWise 模型服务环境变量配置
├── start-listener.sh       # ⭐ OrderWise 启动 listener 模式
├── start-mcp-server.sh     # ⭐ OrderWise 启动 MCP 服务
└── start-mcp-server-tmux.sh # ⭐ OrderWise 启动 MCP 服务（tmux 分列）
```

### Benchmark 配置

编辑 `benchmark/configs/framework_configs/orderwise.yaml`：

```yaml
base_url: "http://localhost:4244/v1"  # 本地部署使用 4244，远程服务器可自定义端口
model: "autoglm-phone-9b"
apps_config_path: "examples/apps_config.json"
app_device_mapping_path: "examples/app_device_mapping.json"
```

### 支持的应用

| 应用 | 包名 | 版本 | 类型 |
|------|------|------|------|
| **美团** | `com.sankuai.meituan` | 12.49.202 | Android App |
| **京东外卖** | `com.jd.waimai` | 15.2.80 | Android App |
| **淘宝闪购** | - | - | H5 网页 ([https://m.tb.cn/](https://m.tb.cn/)) |

## 开发指南

### 添加新的 App 支持

1. 在 `examples/apps_config.json` 中添加配置
2. 在 `phone_agent/utils/parallel_executor.py` 中添加 app 类型映射
3. 更新 `phone_agent/utils/price_extractor.py` 的价格提取逻辑（如需要）

### 扩展 Benchmark

1. 在 `benchmark/tasks/` 中添加任务定义
2. 在 `benchmark/core/metrics.py` 中添加新的指标计算
3. 更新 `benchmark/configs/benchmark_config.yaml`

## 参考资源

| 文档 | 说明 |
|------|------|
| [benchmark/README.md](benchmark/README.md) | Benchmark 框架详细文档（配置、任务设计、评估指标） |
| [mcp_mode/README.md](mcp_mode/README.md) | MCP 模式详细文档（配置、使用示例） |
| [sandbox/README.md](sandbox/README.md) | Sandbox 部署文档（UCloud Sandbox 云端部署） |

## 许可证

本项目基于 [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 项目，遵循相同的许可证。

## 引用

如果您发现 OrderWise-Agent 对您的研究有帮助，请考虑引用我们的工作：

```bibtex
@misc{orderwise_agent_2026,
  title={OrderWise-Agent: An Intelligent Multi-Platform Food Delivery Price Comparison Agent},
  author={OrderWise Team},
  year={2026},
  url={https://github.com/ucloud/orderwise-agent}
}
```

## 联系我们

如有问题或需要支持，欢迎加入[微信交流群](docs/WECHAT.md)或通过以下方式联系我们：

Email: [orderwise.agent@gmail.com](mailto:orderwise.agent@gmail.com)
