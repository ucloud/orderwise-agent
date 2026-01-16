"""原始Open-AutoGLM适配器（顺序执行版本）"""
import time
from typing import Dict, Any

from benchmark.core.base_adapter import BaseAdapter, TaskResult
from benchmark.core.task_definition import TaskDefinition
from benchmark.adapters.common import (
    create_model_config,
    create_agent_config,
    build_app_task_description,
    format_app_result,
)


class AutoGLMOriginalAdapter(BaseAdapter):
    """原始AutoGLM适配器 - 顺序执行版本，固定使用单个设备"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.device_id = config.get("device_id")
    
    def initialize(self) -> bool:
        """初始化（延迟创建agent）"""
        self.initialized = True
        return True
    
    def execute_task(self, task: TaskDefinition) -> TaskResult:
        """执行任务 - 顺序执行多个app"""
        if not self.initialized:
            return TaskResult(
                task_id=task.task_id,
                framework_name=self.get_framework_name(),
                success=False,
                execution_time=0.0,
                error="Adapter not initialized"
            )
        
        start_time = time.time()
        apps = task.expected_result.apps or []
        app_results = []
        
        model_config = create_model_config(self.config)
        agent_config = create_agent_config(self.config, self.device_id)
        from phone_agent import PhoneAgent
        agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        
        for app_name in apps:
            app_start_time = time.time()
            
            if app_results:
                from phone_agent.adb import home
                home(device_id=self.device_id, delay=0.5)
            
            app_task = build_app_task_description(app_name, task)
            app_result = agent.run(app_task)
            app_time = time.time() - app_start_time
            app_results.append(format_app_result(app_name, app_result, app_time))
            agent.reset()
        
        total_time = time.time() - start_time
        successful_apps = sum(1 for r in app_results if r["success"])
        
        # 多app任务需要所有app都成功，单app任务至少1个成功
        success = successful_apps == len(apps) if len(apps) > 1 else successful_apps > 0
        
        return TaskResult(
            task_id=task.task_id,
            framework_name=self.get_framework_name(),
            success=success,
            execution_time=total_time,
            steps=0,
            result_data={
                "app_results": app_results,
                "total_apps": len(apps),
                "successful_apps": successful_apps,
                "parallel": False,
            },
            error=None,
        )
    
    def reset_environment(self):
        """重置环境"""
        pass
    
    def cleanup(self):
        """清理资源"""
        self.initialized = False
    
    def get_framework_name(self) -> str:
        """返回框架名称"""
        return "autoglm"
