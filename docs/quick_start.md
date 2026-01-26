# 安装 orderwise-agent
pip install orderwise-agent

# 安装 ADB（如果还没有）
brew install android-platform-tools  # macOS 或访问 https://developer.android.com/tools/releases/platform-tools

# 连接 Android 云手机
adb connect your-cloud-phone-ip:port
adb devices  # 验证连接

# 配置模型服务
# 方式一：使用智谱官方 API（推荐）
export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export PHONE_AGENT_MODEL="autoglm-phone"
export PHONE_AGENT_API_KEY="your-api-key"  # 在 [智谱平台](https://docs.bigmodel.cn/cn/api/introduction) 申请

# 方式二：使用自部署模型服务
export ORDERWISE_MODEL_URL="http://your-model-server:port/v1"  # 模型服务地址
export ORDERWISE_MODEL_NAME="autoglm-phone-9b"                 # 模型名称

# 运行orderwise-agent(mcp mode)
orderwise-agent mcp "茉莉花香拿铁" --seller "瑞幸" --apps 美团=云手机1-ip 京东外卖=云手机2-ip 淘宝闪购=云手机3-ip
