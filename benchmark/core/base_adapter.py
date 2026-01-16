"""框架适配器基类"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .task_definition import TaskDefinition


class TaskResult:
    """任务执行结果"""
    def __init__(
        self,
        task_id: str,
        framework_name: str,
        success: bool,
        execution_time: float,
        steps: int = 0,
        result_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        screenshots: Optional[list] = None,
    ):
        self.task_id = task_id
        self.framework_name = framework_name
        self.success = success
        self.execution_time = execution_time
        self.steps = steps
        self.result_data = result_data or {}
        self.error = error
        self.screenshots = screenshots or []

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "framework_name": self.framework_name,
            "success": self.success,
            "execution_time": self.execution_time,
            "steps": self.steps,
            "result_data": self.result_data,
            "error": self.error,
            "screenshots_count": len(self.screenshots),
        }


class BaseAdapter(ABC):
    """框架适配器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.initialized = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """初始化框架，返回是否成功"""
        pass
    
    @abstractmethod
    def execute_task(self, task: TaskDefinition) -> TaskResult:
        """执行单个任务，返回结果"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理资源"""
        pass
    
    @abstractmethod
    def get_framework_name(self) -> str:
        """返回框架名称"""
        pass
    
    def reset_environment(self):
        """重置环境（可选实现）"""
        pass

