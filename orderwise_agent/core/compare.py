"""最简单的比价函数"""

import os
import importlib.resources
from typing import Optional, List, Dict, Any
from pathlib import Path

APP_NAME_MAPPING = {"美团": "app1", "京东外卖": "app2", "淘宝闪购": "app3"}
APP_TYPE_MAP = {"美团": "mt", "京东外卖": "jd", "淘宝闪购": "tb"}

def compare_prices(
    product_name: str,
    seller_name: Optional[str] = None,
    apps: Optional[List[str]] = None,
    max_steps: int = 100,
    device_mapping: Optional[Dict[str, str]] = None,
    apps_config: Optional[Dict[str, Dict[str, Any]]] = None,
    **kwargs
) -> Dict:
    """
    多平台外卖比价 - 最简单的使用方式
    
    Args:
        product_name: 商品名称
        seller_name: 商家名称（可选）
        apps: 平台列表（默认: ["美团", "京东外卖", "淘宝闪购"]）
        max_steps: 最大执行步数（默认: 100）
        device_mapping: 设备映射字典，例如 {"app1": "device_id_1", "app2": "device_id_2"}（可选）
        apps_config: 应用配置字典（可选，默认使用内置配置）
    
    Returns:
        比价结果字典，包含 best_price 和 platform_results
    """
    # 延迟导入避免循环依赖
    from phone_agent.model import ModelConfig
    from phone_agent.agent import AgentConfig
    from phone_agent.utils.parallel_executor import (
        build_tasks_from_configs,
        load_devices_config,
        load_apps_config,
        run_parallel_tasks,
    )
    from phone_agent.utils.price_extractor import extract_price_from_message
    
    # 自动加载配置
    model_config = ModelConfig(
        base_url=os.getenv("ORDERWISE_MODEL_URL", os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:4244/v1")),
        model_name=os.getenv("ORDERWISE_MODEL_NAME", os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b")),
        api_key=os.getenv("ORDERWISE_API_KEY", os.getenv("PHONE_AGENT_API_KEY", "EMPTY")),
    )
    
    if apps is None:
        apps = ["美团", "京东外卖", "淘宝闪购"]
    
    def _find_config_file(filename: str) -> Optional[Path]:
        project_root = Path(__file__).parent.parent.parent
        project_path = project_root / "examples" / filename
        if project_path.exists():
            return project_path
        
        try:
            with importlib.resources.path("examples", filename) as p:
                if p.exists():
                    return p
        except Exception:
            try:
                from importlib.resources import files, as_file
                resource = files("examples").joinpath(filename)
                if hasattr(resource, "read_bytes"):
                    with as_file(resource) as path:
                        if path.exists():
                            return path
                elif hasattr(resource, "_path"):
                    path = Path(str(resource))
                    if path.exists():
                        return path
            except Exception:
                pass
        
        return None
    
    if apps_config is None:
        apps_config_path = _find_config_file("apps_config.json")
        apps_config = load_apps_config(str(apps_config_path) if apps_config_path else None)
    
    if device_mapping is None:
        return {
            "error": "必须通过 --apps 参数指定设备映射，格式：--apps 平台名=device-id",
            "best_price": None,
            "platform_results": {},
        }
    
    filtered_apps_config = {
        APP_NAME_MAPPING[name]: apps_config[APP_NAME_MAPPING[name]]
        for name in apps
        if APP_NAME_MAPPING.get(name) and APP_NAME_MAPPING[name] in apps_config
    }
    
    app_to_device_mapping = {
        APP_TYPE_MAP[name]: device_mapping[APP_NAME_MAPPING[name]]
        for name in apps
        if (APP_NAME_MAPPING.get(name) and 
            APP_NAME_MAPPING[name] in filtered_apps_config and 
            APP_NAME_MAPPING[name] in device_mapping and
            APP_TYPE_MAP.get(name))
    }
    
    tasks = build_tasks_from_configs(
        apps_config=filtered_apps_config,
        task_template=f"搜索{product_name}",
        product_name=product_name,
        seller_name=seller_name,
        app_to_device_mapping=app_to_device_mapping if app_to_device_mapping else None,
    )
    
    if not tasks:
        return {
            "error": "没有可用的设备或应用配置",
            "best_price": None,
            "platform_results": {},
        }
    
    # 执行并行任务
    keyword = f"{seller_name} {product_name}" if seller_name else product_name
    results = run_parallel_tasks(
        tasks=tasks,
        model_config=model_config,
        agent_config=AgentConfig(max_steps=max_steps),
        task_id=f"task-{product_name}",
        user_id="orderwise_user",
        keyword=keyword,
        mongodb_connection_string=None,
        device_manager=None,
    )
    
    # 提取价格信息
    platform_results = {}
    for result in results:
        price_data = extract_price_from_message(result.result, app_name=result.app_name)
        if price_data:
            platform_results[result.app_name] = {
                "price": price_data.get("price", 0),
                "delivery_fee": price_data.get("delivery_fee", 0),
                "pack_fee": price_data.get("pack_fee", 0),
                "total_fee": price_data.get("total_fee", 0),
            }
    
    # 计算最低价格
    best_price = None
    if platform_results:
        best_app, best_data = min(platform_results.items(), key=lambda x: x[1]["total_fee"])
        best_price = {"app": best_app, **best_data}
    
    return {
        "best_price": best_price,
        "platform_results": platform_results,
    }

