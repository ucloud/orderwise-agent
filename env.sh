#!/bin/bash
# 统一模型服务配置

# ============================================
# 方式一：智谱官方 API
# ============================================
# export PHONE_AGENT_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
# export PHONE_AGENT_MODEL="autoglm-phone"
# export PHONE_AGENT_API_KEY="your-api-key"
# export PHONE_AGENT_MAX_STEPS="100"

# ============================================
# 方式二：本地部署 vLLM
# ============================================
# 本地部署：使用 localhost
# export PHONE_AGENT_BASE_URL="http://localhost:4244/v1"
# 远程服务器：使用服务器 IP（替换为实际 IP）
# export PHONE_AGENT_BASE_URL="http://YOUR_SERVER_IP:4244/v1"
# export PHONE_AGENT_MODEL="autoglm-phone-9b"
# export PHONE_AGENT_API_KEY="EMPTY"  # vLLM 使用 "EMPTY"
# export PHONE_AGENT_MAX_STEPS="100"
