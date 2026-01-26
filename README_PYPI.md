# OrderWise-Agent

**Make Every Penny Count.**

基于 AutoGLM 的智能外卖比价 Agent，专注于多平台并行比价和结构化价格提取。

## 核心功能

- ✅ **并行执行**：多设备/多app同时执行，执行时间取最大值而非累加
- ✅ **价格提取**：结构化提取商品单价、配送费、打包费、总价
- ✅ **MCP 模式**：跨平台工具集成、标准化工具调用接口
- ✅ **设备管理**：云手机健康监控、自动重连
- ✅ **主动接管**：用户可以在任意时间中断搜索，Agent 会自动恢复执行

## 性能提升

相比 Baseline (AutoGLM)，性能提升：
- **平均执行时间**：提升 56.90%
- **任务成功率**：提升 25.00%
- **价格提取准确率**：提升 25.00%

## 快速开始

### 1. 安装

```bash
pip install orderwise-agent
```

### 2. 连接云手机

```bash
# 安装 ADB（如果还没有）
brew install android-platform-tools  # macOS
# 或访问 https://developer.android.com/tools/releases/platform-tools

# 连接 Android 云手机
adb connect your-cloud-phone-ip:port
adb devices  # 验证连接
```

### 3. 配置模型服务

**方式一：使用智谱官方 API（推荐）**
```bash
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"  # 在 [智谱平台](https://docs.bigmodel.cn/cn/api/introduction) 申请
```

**方式二：使用自部署模型服务**
```bash
export ORDERWISE_MODEL_URL="http://your-model-server:port/v1"  # 模型服务地址
export ORDERWISE_MODEL_NAME="autoglm-phone-9b"                 # 模型名称
```

### 4. 运行

```bash
orderwise-agent mcp "茉莉花香拿铁" --seller "瑞幸" --apps 美团=云手机1-ip 京东外卖=云手机2-ip 淘宝闪购=云手机3-ip
```

## 支持的应用

- **美团** (Android App)
- **京东外卖** (Android App)
- **淘宝闪购** (H5 网页)

## 更多信息

- 📖 [完整文档](https://github.com/ucloud/orderwise-agent)
- 🌐 [官方网站](https://ucloud.github.io/orderwise)
- 💬 [加入讨论群](https://github.com/ucloud/orderwise-agent/blob/main/docs/WECHAT.md)

## 许可证

Apache-2.0

