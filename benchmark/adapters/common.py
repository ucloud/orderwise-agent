"""适配器公共工具函数"""
from typing import Dict, Any, Optional
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig
from benchmark.core.task_definition import TaskDefinition


def create_model_config(config: Dict[str, Any]) -> ModelConfig:
    """创建模型配置"""
    return ModelConfig(
        base_url=config.get("base_url", "http://localhost:8000/v1"),
        model_name=config.get("model", "autoglm-phone-9b"),
        api_key=config.get("api_key"),
        lang=config.get("lang", "zh"),
    )


def create_agent_config(config: Dict[str, Any], device_id: Optional[str] = None) -> AgentConfig:
    """创建代理配置"""
    return AgentConfig(
        max_steps=config.get("max_steps", 100),
        device_id=device_id or config.get("device_id"),
        verbose=config.get("verbose", False),
        lang=config.get("lang", "zh"),
    )


def build_app_task_description(app_name: str, task: TaskDefinition) -> str:
    """构建应用任务描述"""
    apps = task.expected_result.apps or []
    product = task.expected_result.product or ""
    seller = task.metadata.get("seller") if task.metadata else None
    
    if len(apps) > 1:
        seller_part = f"（商家：{seller}）" if seller else ""
        return f"在{app_name}中搜索'{product}'{seller_part}并查看价格（包括商品价格、配送费、打包费、总价）"
    elif "比较" in task.task:
        return f"在{app_name}中{task.task}"
    else:
        return f"在{app_name}中搜索'{product}'并查看价格"


def format_app_result(app_name: str, result: str, execution_time: float) -> Dict[str, Any]:
    """格式化应用执行结果"""
    return {
        "app": app_name,
        "result": result,
        "execution_time": execution_time,
        "success": result is not None and result != ""
    }

