# 克隆仓库
git clone https://github.com/ucloud/orderwise-agent.git
cd orderwise-agent

# 安装依赖
pip install -r requirements.txt

编辑 `env.sh` 文件配置模型服务
编辑 `examples/app_device_mapping.json` 文件配置外卖平台app和安卓云手机/物理手机设配的映射

# 启动交互式MCP体验模式
bash start-mcp-server-tmux.sh