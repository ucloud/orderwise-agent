"""Backend implementation for Order Wise MCP Server."""

import importlib.util
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.utils.device_manager import DeviceManager
from phone_agent.utils.parallel_executor import (
    build_tasks_from_configs,
    load_devices_config,
    load_apps_config,
    run_parallel_tasks,
)
from phone_agent.utils.price_extractor import extract_price_from_message
from mcp_mode.mcp_server.session_manager import get_session_manager, TaskState

# Track pre-checked devices across MCP server lifetime
_prechecked_devices = set()
_precheck_lock = threading.Lock()

# Cache DeviceManager instances by MongoDB connection string
_device_manager_cache: Dict[str, DeviceManager] = {}
_device_manager_cache_lock = threading.Lock()

# Import check_system_requirements from main.py
# Support both development and installed package modes
_project_root = Path(__file__).parent.parent.parent
_paths_to_try = [
    str(_project_root),
    os.getenv("PYTHONPATH", ""),
]
for path in _paths_to_try:
    if path and path not in sys.path:
        sys.path.insert(0, path)

# Use importlib to check if module exists before importing
_spec = importlib.util.find_spec("main")
if _spec and _spec.loader:
    from main import check_system_requirements
else:
    def check_system_requirements(device_ids=None):
        return True

# MCP 配置缓存
_mcp_config_cache: Optional[Dict[str, Any]] = None
_mcp_config_lock = threading.Lock()


def _convert_devices_config_to_app_to_device(
    devices_config: Dict[str, str],
    mcp_config: Dict[str, Any]
) -> Dict[str, str]:
    """
    Convert devices_config to app_to_device mapping format.
    
    Args:
        devices_config: Device mapping in format:
            - {"app1": "device_id", ...} (from app_device_mapping.json)
            - {"美团": "device_id", ...} (from device_mapping parameter)
        mcp_config: MCP configuration dictionary
    
    Returns:
        Mapping in format {"mt": "device_id", "jd": "device_id", "tb": "device_id"}
    """
    if not devices_config:
        return {}
    
    app_name_mapping = mcp_config["search"]["app_name_mapping"]
    app_type_mapping = {"美团": "mt", "京东外卖": "jd", "淘宝闪购": "tb"}
    
    # Build app_key -> app_type mapping
    app_key_to_type = {
        app_key: app_type_mapping[app_name]
        for app_name, app_key in app_name_mapping.items()
        if app_name in app_type_mapping
    }
    
    app_to_device = {}
    for key, device_id in devices_config.items():
        # Case 1: key is app name (e.g., "美团", "京东外卖")
        if key in app_type_mapping:
            app_to_device[app_type_mapping[key]] = device_id
        # Case 2: key is app key (e.g., "app1", "app2", "app3")
        elif key in app_key_to_type:
            app_to_device[app_key_to_type[key]] = device_id
    
    return app_to_device


def _precheck_devices(device_ids: List[str]) -> None:
    """Pre-check devices on first use."""
    with _precheck_lock:
        device_ids_to_check = [
            device_id for device_id in device_ids
            if device_id not in _prechecked_devices
        ]
        _prechecked_devices.update(device_ids_to_check)
    
    if device_ids_to_check:
        print(f"[MCP设备预检] 首次使用设备，进行预检: {device_ids_to_check}")
        if not check_system_requirements(device_ids=device_ids_to_check):
            print(f"[MCP警告] 设备预检失败，但继续执行任务")


def load_mcp_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load MCP server configuration from YAML file.
    
    Args:
        config_path: Path to server_config.yaml (default: mcp_mode/mcp_server/server_config.yaml)
    
    Returns:
        Dictionary containing all MCP configuration
    """
    global _mcp_config_cache
    
    if _mcp_config_cache is not None:
        return _mcp_config_cache
    
    if config_path is None:
        config_path = Path(__file__).parent / "server_config.yaml"
    else:
        config_path = Path(config_path)
    
    default_config = {
        "server": {
            "host": "0.0.0.0",
            "port": 8703,
        },
        "paths": {
            "app_device_mapping": "mcp_mode/mcp_server/app_device_mapping.json",
            "apps_config": "examples/apps_config.json",
        },
        "agent": {
            "max_steps": 30,
            "verbose": False,
            "lang": "zh",
            "enable_screenshot_cache": True,
            "screenshot_cache_max_age": 300.0,
        },
        "mongodb": {
            "connection_string": None,
        },
        "model": {
            "default_provider": "local",
        },
        "search": {
            "default_apps": ["美团", "京东外卖", "淘宝闪购"],
            "app_name_mapping": {
                "美团": "app1",
                "京东外卖": "app2",
                "淘宝闪购": "app3",
            },
            "default_max_steps": 30,
        },
        "conda": {
            "environment": "waimai",
        },
    }
    
    if not config_path.exists():
        print(f"[MCP配置] 配置文件不存在: {config_path}，使用默认配置")
        with _mcp_config_lock:
            _mcp_config_cache = default_config
        return default_config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 合并默认配置和用户配置
        merged_config = default_config.copy()
        if config:
            for key, value in config.items():
                if isinstance(value, dict) and isinstance(merged_config.get(key), dict):
                    merged_config[key].update(value)
                else:
                    merged_config[key] = value
        
        if "paths" in merged_config:
            project_root = Path(__file__).parent.parent.parent
            for path_key in ["devices_config", "apps_config"]:
                if path_key in merged_config["paths"]:
                    path_value = merged_config["paths"][path_key]
                    if not os.path.isabs(path_value):
                        merged_config["paths"][path_key] = str(project_root / path_value)
        
        with _mcp_config_lock:
            _mcp_config_cache = merged_config
        
        print(f"[MCP配置] 已加载配置文件: {config_path}")
        return merged_config
    
    except Exception as e:
        print(f"[MCP配置] 加载配置文件失败: {e}，使用默认配置")
        with _mcp_config_lock:
            _mcp_config_cache = default_config
        return default_config


def load_model_config(
    model_provider: str = "local",
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load model configuration from environment variables (env.sh).
    
    Args:
        model_provider: Model provider name (deprecated, kept for compatibility)
        config_path: Deprecated, kept for compatibility
    
    Returns:
        Dictionary with api_base, api_key, and model_name
    """
    default_model_config = {
        "api_base": "http://localhost:4244/v1",
        "api_key": "EMPTY",
        "model_name": "autoglm-phone-9b",
    }
    
    # 从环境变量读取（与 env.sh 统一）
    env_base_url = os.getenv("PHONE_AGENT_BASE_URL")
    env_api_key = os.getenv("PHONE_AGENT_API_KEY")
    env_model_name = os.getenv("PHONE_AGENT_MODEL")
    
    # 如果设置了 BASE_URL 和 MODEL，就使用环境变量（API_KEY 可选，vLLM 可以使用 "EMPTY"）
    if env_base_url and env_model_name:
        return {
            "api_base": env_base_url,
            "api_key": env_api_key or "EMPTY",  # vLLM 可以使用 "EMPTY"
            "model_name": env_model_name,
        }
    
    return default_model_config


def compare_prices_backend(
    product_name: str,
    seller_name: Optional[str] = None,
    apps: Optional[List[str]] = None,
    max_steps: Optional[int] = None,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
    app_device_mapping_path: Optional[str] = None,
    apps_config_path: Optional[str] = None,
    model_provider: Optional[str] = None,
    model_config_path: Optional[str] = None,
    model_base_url: Optional[str] = None,
    model_name: Optional[str] = None,
    model_api_key: Optional[str] = None,
    mongodb_connection_string: Optional[str] = None,
    mcp_config_path: Optional[str] = None,
    device_mapping: Optional[Dict[str, str]] = None,
    session_id: Optional[str] = None,
    reply_from_client: Optional[str] = None,
) -> Dict:
    """
    Backend implementation for price comparison.
    
    **MCP Mode (Sync)**: Uses synchronous takeover mode. No MongoDB dependency.
    When takeover is triggered, immediately returns with session_id.
    
    Args:
        product_name: Product name to search
        seller_name: Optional seller name
        apps: List of apps to compare (default: ["美团", "京东外卖", "淘宝闪购"])
        max_steps: Max steps per platform (if None, uses config file default)
        task_id: Optional task ID (auto-generated if not provided)
        user_id: Optional user ID (defaults to "mcp_user" if not provided)
        app_device_mapping_path: Path to app device mapping config (if None, uses config file)
        apps_config_path: Path to apps config (if None, uses config file)
        model_provider: Model provider name (e.g., "local", "remote") - if None, uses config file default
        model_base_url: Model API base URL (overrides env.sh if provided)
        model_name: Model name (overrides config file if provided)
        model_api_key: Model API key (overrides config file if provided)
        mongodb_connection_string: DEPRECATED - MCP mode always uses sync mode (ignored)
        mcp_config_path: Path to MCP server_config.yaml (if None, uses default: mcp_mode/mcp_server/server_config.yaml)
        device_mapping: Device mapping dictionary, e.g., {'app1': 'device_id_1', 'app2': 'device_id_2'}.
            If not provided, uses app_device_mapping.json.
        session_id: Session ID to continue a previously interrupted task (when takeover was triggered).
            Must provide reply_from_client if using this.
        reply_from_client: Reply from client to continue a task after takeover.
            Must provide session_id if using this.
    
    Returns:
        Comparison result dictionary. If takeover is triggered:
        - session_id: Session ID for continuing the task
        - stop_reason: "INFO_ACTION_NEEDS_REPLY"
        - message: Message from agent requesting intervention
    """
    session_manager = get_session_manager()
    continue_task = False
    restored_state = None
    
    if session_id:
        if not reply_from_client:
            return {
                "error": "reply_from_client is required when session_id is provided",
                "session_id": session_id,
            }
        
        restored_state = session_manager.get(session_id)
        if not restored_state:
            return {
                "error": f"Session not found or expired: {session_id}",
                "session_id": session_id,
            }
        
        print(f"[MCP] 发送用户回复到等待中的进程: session_id={session_id}, reply={reply_from_client}")
        
        if session_manager.send_reply(session_id, reply_from_client):
            print(f"[MCP] 已发送回复，worker 进程将继续执行...")
            return {
                "product_name": restored_state.keyword.split()[-1] if restored_state.keyword else "未知商品",
                "seller_name": restored_state.keyword.split()[0] if " " in restored_state.keyword else None,
                "task_id": restored_state.task_id,
                "session_id": session_id,
                "status": "reply_sent",
                "message": f"已发送回复，worker 进程将继续执行。任务完成后会返回最终结果。",
            }
        else:
            return {
                "error": f"无法发送回复到 session {session_id}（进程可能已结束）",
                "session_id": session_id,
            }
    
    # Load MCP configuration
    mcp_config = load_mcp_config(mcp_config_path)
    
    # Use config file values if parameters are not provided
    app_device_mapping_path = app_device_mapping_path or mcp_config["paths"]["app_device_mapping"]
    apps_config_path = apps_config_path or mcp_config["paths"]["apps_config"]
    model_provider = model_provider or mcp_config["model"]["default_provider"]
    max_steps = max_steps or mcp_config["agent"]["max_steps"]
    
    # MCP mode: Always use sync mode (no MongoDB)
    # Force mongodb_connection_string to None for MCP mode to trigger sync mode
    mongodb_connection_string = None
    
    if not task_id:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
    if not user_id:
        user_id = "mcp_user"  # Default user_id for MCP mode
    
    # Load app_device_mapping: priority: device_mapping parameter > app_device_mapping.json file
    devices_config = {}
    if device_mapping:
        # Use device_mapping parameter (highest priority)
        devices_config = device_mapping
        print(f"[MCP] 使用参数传入的设备映射: {len(devices_config)} 个设备")
    else:
        devices_config = load_devices_config(app_device_mapping_path)
        print(f"[MCP] 从配置文件读取设备映射: {len(devices_config)} 个设备")
    
    apps_config = load_apps_config(apps_config_path)
    
    if apps:
        filtered_apps_config = {}
        # 从配置文件读取应用名称映射
        app_name_mapping = mcp_config["search"]["app_name_mapping"]
        for app_name in apps:
            key = app_name_mapping.get(app_name)
            if key and key in apps_config:
                filtered_apps_config[key] = apps_config[key]
        apps_config = filtered_apps_config
    
    keyword = f"{seller_name} {product_name}" if seller_name else product_name
    
    # Convert devices_config to app_to_device mapping format
    app_to_device = _convert_devices_config_to_app_to_device(devices_config, mcp_config)
    if app_to_device:
        print(f"[MCP] 设备映射: {app_to_device}")
        _precheck_devices(list(app_to_device.values()))
    
    # Build tasks: if continuing, only create task for the interrupted app
    if continue_task and restored_state:
        # Create a single task for the interrupted app with continuation message
        app_type_map = {"美团": "mt", "京东外卖": "jd", "淘宝闪购": "tb"}
        app_type = app_type_map.get(restored_state.app_name, "unknown")
        device_id = restored_state.device_id
        
        # Find app config
        app_key = None
        app_name_mapping = mcp_config["search"]["app_name_mapping"]
        for name, key in app_name_mapping.items():
            if name == restored_state.app_name:
                app_key = key
                break
        
        if not app_key or app_key not in apps_config:
            return {
                "error": f"App config not found for {restored_state.app_name}",
                "session_id": session_id,
            }
        
        app_info = apps_config[app_key]
        # Modify task to include continuation message
        continuation_task = f"用户已完成操作（{reply_from_client}），继续执行原任务：{restored_state.task}"
        
        from phone_agent.utils.parallel_executor import ParallelTask
        tasks = [ParallelTask(
            device_id=device_id,
            task=continuation_task,
            app_name=restored_state.app_name,
            app_package=restored_state.app_package,
        )]
        print(f"[MCP] 继续任务: app={restored_state.app_name}, device={device_id}")
    else:
        tasks = build_tasks_from_configs(
            apps_config=apps_config,
            task_template=f"搜索{product_name}",
            product_name=product_name,
            seller_name=seller_name,
            app_to_device_mapping=app_to_device if app_to_device else None,
        )
    
    if not tasks:
        return {
            "error": "没有可用的设备或应用配置",
            "product_name": product_name,
            "platforms": [],
            }
    
    if continue_task and restored_state:
        model_config = ModelConfig(**restored_state.model_config)
        agent_config_dict = restored_state.agent_config.copy()
        # Override with any provided parameters
        if model_base_url:
            model_config.base_url = model_base_url
        if model_name:
            model_config.model_name = model_name
        if model_api_key:
            model_config.api_key = model_api_key
        agent_config = AgentConfig(**agent_config_dict)
        if max_steps:
            agent_config.max_steps = max_steps
    else:
        model_cfg = load_model_config(model_provider)
        model_config = ModelConfig(
            base_url=model_base_url or model_cfg["api_base"],
            model_name=model_name or model_cfg["model_name"],
            api_key=model_api_key or model_cfg["api_key"],
            lang="zh",
        )
        agent_config = AgentConfig(
            max_steps=max_steps,
            device_id=None,
            verbose=mcp_config["agent"]["verbose"],
            lang=mcp_config["agent"]["lang"],
            enable_screenshot_cache=mcp_config["agent"]["enable_screenshot_cache"],
            screenshot_cache_max_age=mcp_config["agent"]["screenshot_cache_max_age"],
        )
    
    # MCP mode: Always pass None for mongodb_connection_string to trigger sync mode
    print(f"[MCP] 开始执行 {len(tasks)} 个并行任务...")
    try:
        results = run_parallel_tasks(
            tasks=tasks,
            model_config=model_config,
            agent_config=agent_config,
            task_id=task_id,
            user_id=user_id,
            keyword=keyword,
            mongodb_connection_string=None,  # MCP mode: sync mode, no MongoDB
            device_manager=None,  # MCP mode: no DeviceManager
        )
        print(f"[MCP] run_parallel_tasks 返回了 {len(results)} 个结果")
    except Exception as e:
        print(f"[MCP错误] run_parallel_tasks 执行失败: {e}")
        import traceback
        traceback.print_exc()
        # Return error result
        return {
            "error": f"任务执行失败: {str(e)}",
            "product_name": product_name,
            "seller_name": seller_name,
            "task_id": task_id,
            }
    
    takeover_interrupted = False
    takeover_session_id = None
    takeover_message = None
    
    platform_results = []
    print(f"[MCP] 处理 {len(results)} 个结果...")
    for result in results:
        if result.stop_reason == "INFO_ACTION_NEEDS_REPLY":
            takeover_interrupted = True
            takeover_session_id = result.session_id
            takeover_message = result.result
            print(f"[MCP] 检测到接管中断: session_id={takeover_session_id}, message={takeover_message}")
            # Still add the result to platform_results for information
        platform_result = {
            "app": result.app_name,
            "device_id": result.device_id,
            "duration": result.duration,
            "raw_result": result.result,
        }
        
        if result.success:
            price_info = extract_price_from_message(result.result, app_name=result.app_name)
            if price_info:
                platform_result.update({
                    "status": "success",
                    "price": price_info.get("price"),
                    "delivery_fee": price_info.get("delivery_fee", 0.0),
                    "pack_fee": price_info.get("pack_fee", 0.0),
                    "total_fee": price_info.get("total_fee"),
                })
            else:
                platform_result.update({"status": "failed", "error": "无法提取价格信息"})
        else:
            platform_result.update({"status": "failed", "error": getattr(result, "error", "未知错误")})
        
        platform_results.append(platform_result)
    
    success_results = [r for r in platform_results if r["status"] == "success"]
    
    best_price = None
    if success_results:
        valid_results = [r for r in success_results if r.get("total_fee") is not None]
        if valid_results:
            best_result = min(valid_results, key=lambda x: x["total_fee"])
            best_price = {
                "app": best_result["app"],
                "total_fee": best_result["total_fee"],
            }
    
    max_duration = max((r["duration"] for r in platform_results), default=0.0)
    
    print(f"[MCP] 处理完成，takeover_interrupted={takeover_interrupted}, success_count={len(success_results)}")
    
    # If takeover interrupted, return immediately with session info
    if takeover_interrupted:
        return {
            "product_name": product_name,
            "seller_name": seller_name,
            "task_id": task_id,
            "session_id": takeover_session_id,
            "stop_reason": "INFO_ACTION_NEEDS_REPLY",
            "message": takeover_message,
            "platforms": platform_results,  # Partial results if any
            "summary": {
                "total_platforms": len(platform_results),
                "success_count": len(success_results),
                "failed_count": len(platform_results) - len(success_results),
                "interrupted": True,
            },
        }
    
    result_dict = {
        "product_name": product_name,
        "seller_name": seller_name,
        "task_id": task_id,
        "platforms": platform_results,
        "summary": {
            "total_platforms": len(platform_results),
            "success_count": len(success_results),
            "failed_count": len(platform_results) - len(success_results),
            "best_price": best_price,
            "total_duration": max_duration,
        },
    }
    print(f"[MCP] 准备返回结果给客户端: {len(platform_results)} 个平台结果")
    return result_dict

