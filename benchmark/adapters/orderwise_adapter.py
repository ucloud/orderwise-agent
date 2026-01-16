"""OrderWise适配器（并行执行版本）"""
import os
import time
from typing import Dict, Any, List, Optional

from phone_agent import PhoneAgent
from phone_agent.utils.parallel_executor import (
    build_tasks_from_configs,
    load_apps_config,
    load_devices_config,
    run_parallel_tasks,
)
from phone_agent.utils.price_extractor import extract_price_from_message

from benchmark.core.base_adapter import BaseAdapter, TaskResult
from benchmark.core.task_definition import TaskDefinition
from benchmark.adapters.common import (
    create_model_config,
    create_agent_config,
    build_app_task_description,
    format_app_result,
)
from benchmark.utils import get_project_root


def _convert_devices_config_to_app_to_device(devices_config: Dict[str, str]) -> Dict[str, str]:
    """将devices_config转换为app_to_device映射格式"""
    if not devices_config:
        return {}
    
    app_key_to_type = {"app1": "mt", "app2": "jd", "app3": "tb"}
    return {app_key_to_type[key]: device_id for key, device_id in devices_config.items() if key in app_key_to_type}


class AutoGLMOrderWiseAdapter(BaseAdapter):
    """OrderWise适配器 - 支持并行执行和价格提取"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.agent = None
        self.device_id = config.get("device_id")
        self.apps_config_path = config.get("apps_config_path", "examples/apps_config.json")
        app_device_mapping_path = config.get("app_device_mapping_path")
        if app_device_mapping_path and not os.path.isabs(app_device_mapping_path):
            self.app_device_mapping_path = os.path.join(get_project_root(), app_device_mapping_path)
        else:
            self.app_device_mapping_path = app_device_mapping_path
    
    def initialize(self) -> bool:
        """初始化OrderWise"""
        model_config = create_model_config(self.config)
        agent_config = create_agent_config(self.config, self.device_id)
        self.agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        self.initialized = True
        return True
    
    def execute_task(self, task: TaskDefinition) -> TaskResult:
        """执行任务 - 支持并行执行"""
        if not self.initialized:
            return TaskResult(
                task_id=task.task_id,
                framework_name=self.get_framework_name(),
                success=False,
                execution_time=0.0,
                error="Adapter not initialized"
            )
        
        start_time = time.time()
        steps = 0
        error = None
        
        apps = task.expected_result.apps or []
        product = task.expected_result.product or ""
        seller = task.metadata.get("seller") if task.metadata else None
        
        if len(apps) > 1:
            result_data = self._execute_parallel(apps, product, task.task, seller)
        else:
            result_data = self._execute_single(apps[0] if apps else None, product, task.task)
        
        if "app_results" in result_data:
            for app_result in result_data["app_results"]:
                if "result" in app_result:
                    price_info = extract_price_from_message(
                        app_result["result"],
                        app_result.get("app")
                    )
                    if price_info:
                        app_result["price_info"] = price_info
        
        successful_apps = result_data.get("successful_apps", 0)
        total_apps = len(apps)
        success = successful_apps == total_apps if total_apps > 1 else successful_apps > 0
        
        total_time = time.time() - start_time
        result_data["total_execution_time"] = total_time
        result_data["parallel"] = len(apps) > 1
        
        return TaskResult(
            task_id=task.task_id,
            framework_name=self.get_framework_name(),
            success=success,
            execution_time=total_time,
            steps=steps,
            result_data=result_data,
            error=error,
        )
    
    def _execute_parallel(self, apps: List[str], product: str, task_desc: str, seller: Optional[str] = None) -> Dict[str, Any]:
        """并行执行多个应用"""
        apps_config = load_apps_config(self.apps_config_path)
        
        app_to_device_mapping = None
        if self.app_device_mapping_path:
            app_device_mapping = load_devices_config(self.app_device_mapping_path)
            app_to_device_mapping = _convert_devices_config_to_app_to_device(app_device_mapping)
            if app_to_device_mapping:
                print(f"[Benchmark] 已加载设备映射: {app_to_device_mapping}")
        
        tasks = build_tasks_from_configs(
            apps_config,
            task_template=task_desc,
            product_name=product,
            seller_name=seller,
            app_to_device_mapping=app_to_device_mapping,
        )
        
        filtered_tasks = [t for t in tasks if t.app_name in apps]
        
        if not filtered_tasks:
            return {
                "app_results": [],
                "total_apps": len(apps),
                "successful_apps": 0,
                "parallel": True,
            }
        
        model_config = create_model_config(self.config)
        agent_config = create_agent_config(self.config, self.device_id)
        
        parallel_start = time.time()
        results = run_parallel_tasks(
            tasks=filtered_tasks,
            model_config=model_config,
            agent_config=agent_config,
            task_id=None,
            user_id=None,
            keyword=task_desc,
            mongodb_connection_string=None,  # 不使用MongoDB
            device_manager=None,
        )
        parallel_time = time.time() - parallel_start
        
        app_results = [{
            "app": r.app_name or "unknown",
            "result": r.result,
            "execution_time": r.duration,
            "success": r.success,
            "error": r.error,
        } for r in results]
        
        successful_apps = sum(1 for r in app_results if r["success"])
        
        return {
            "app_results": app_results,
            "total_apps": len(apps),
            "successful_apps": successful_apps,
            "parallel": True,
            "parallel_execution_time": parallel_time,
        }
    
    def _execute_single(self, app_name: Optional[str], product: str, task_desc: str) -> Dict[str, Any]:
        """单个app执行"""
        app_name = app_name or "默认app"
        app_start = time.time()
        
        app_task = f"在{app_name}中{task_desc}" if "比较" in task_desc else f"在{app_name}中搜索'{product}'并查看价格"
        result = self.agent.run(app_task)
        app_time = time.time() - app_start
        
        return {
            "app_results": [format_app_result(app_name, result, app_time)],
            "total_apps": 1,
            "successful_apps": 1 if result else 0,
            "parallel": False,
        }
    
    def reset_environment(self):
        """重置环境"""
        if self.agent:
            self.agent.reset()
    
    def cleanup(self):
        """清理资源"""
        if self.agent:
            self.agent = None
        self.initialized = False
    
    def get_framework_name(self) -> str:
        """返回框架名称"""
        return "orderwise"

