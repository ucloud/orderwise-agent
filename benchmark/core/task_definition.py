"""统一任务定义格式"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskCategory(Enum):
    """任务类别"""
    BASIC = "basic"
    WAIMAI_COMPARE = "waimai_compare"
    COMPLEX = "complex"
    CROSS_APP = "cross_app"


@dataclass
class ExpectedResult:
    """期望结果定义"""
    type: str  # price_comparison, info_extraction, etc.
    apps: Optional[List[str]] = None
    product: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None


@dataclass
class EvaluationCriteria:
    """评估标准"""
    success_criteria: List[str]
    metrics: List[str]
    timeout: Optional[int] = None  # 超时时间（秒）


@dataclass
class TaskDefinition:
    """统一任务定义"""
    task_id: str
    category: TaskCategory
    task: str  # 任务描述
    expected_result: ExpectedResult
    evaluation: EvaluationCriteria
    metadata: Optional[Dict[str, Any]] = None
    display_name: Optional[str] = None  # 显示名称，用于可视化

    @classmethod
    def from_dict(cls, data: dict) -> "TaskDefinition":
        """从字典创建任务定义"""
        # 提取expected_result中支持的字段
        expected_result_data = data["expected_result"]
        supported_fields = {"type", "apps", "product", "conditions"}
        
        # 分离支持的字段和额外字段
        expected_result_dict = {k: v for k, v in expected_result_data.items() if k in supported_fields}
        extra_fields = {k: v for k, v in expected_result_data.items() if k not in supported_fields}
        
        metadata = {**(data.get("metadata") or {}), **extra_fields} if extra_fields else (data.get("metadata") or {})
        
        return cls(
            task_id=data["task_id"],
            category=TaskCategory(data["category"]),
            task=data["task"],
            expected_result=ExpectedResult(**expected_result_dict),
            evaluation=EvaluationCriteria(**data["evaluation"]),
            metadata=metadata if metadata else None,
            display_name=data.get("display_name")
        )

