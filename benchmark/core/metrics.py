"""评估指标定义和计算"""
import os
import sys
from typing import List, Dict, Any, Optional
from .base_adapter import TaskResult
from .task_definition import TaskDefinition
from ..utils import get_project_root

project_root = get_project_root()
sys.path.insert(0, project_root)


class MetricsCalculator:
    """指标计算器"""
    
    @staticmethod
    def calculate_success_rate(results: List[TaskResult]) -> float:
        """计算成功率"""
        if not results:
            return 0.0
        successful = sum(1 for r in results if r.success)
        return successful / len(results)
    
    @staticmethod
    def calculate_avg_execution_time(results: List[TaskResult]) -> float:
        """计算平均执行时间，优先使用成功任务的时间"""
        if not results:
            return 0.0
        
        success_times = [r.execution_time for r in results if r.success]
        if success_times:
            return sum(success_times) / len(success_times)
        
        all_times = [r.execution_time for r in results]
        return sum(all_times) / len(all_times) if all_times else 0.0
    
    @staticmethod
    def calculate_avg_steps(results: List[TaskResult]) -> float:
        """计算平均步数"""
        if not results:
            return 0.0
        steps = [r.steps for r in results if r.success]
        return sum(steps) / len(steps) if steps else 0.0
    
    @staticmethod
    def calculate_error_rate(results: List[TaskResult]) -> float:
        """计算错误率"""
        if not results:
            return 0.0
        errors = sum(1 for r in results if not r.success)
        return errors / len(results)
    
    @staticmethod
    def calculate_price_extraction_accuracy(results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """计算价格提取准确率（针对比价任务）
        
        判断标准：
        1. 必需字段：total_fee, delivery_fee, pack_fee 必须存在
        2. 字段值：必须是数字类型，且 >= 0
        3. total_fee 在 minimum_order 场景允许为 0，其他场景必须 > 0
        4. delivery_fee 和 pack_fee 允许为 0（表示免费）
        5. price 为可选字段（可以为 None）
        6. 多app任务需要所有app都准确提取才算准确
        """
        if not task or task.category.value != "waimai_compare":
            return 0.0
        
        try:
            from phone_agent.utils.price_extractor import extract_price_from_message
        except ImportError:
            return MetricsCalculator._calculate_price_accuracy_simple(results, task)
        
        # 判断是否为 minimum_order 场景
        is_minimum_order = (task.metadata or {}).get("scenario") == "minimum_order"
        expected_apps = len(task.expected_result.apps or [])
        if expected_apps == 0:
            return 0.0
        
        total_tasks = 0
        accurate_tasks = 0
        
        for result in results:
            if not result.success:
                continue
            
            total_tasks += 1
            result_data = result.result_data
            app_results = result_data.get("app_results", [])
            
            # 对于多app任务，需要所有app都成功
            successful_apps = [r for r in app_results if r.get("success")]
            if len(successful_apps) != expected_apps:
                continue  # 不是所有app都成功，跳过
            
            all_apps_accurate = True
            for app_result in successful_apps:
                price_info = app_result.get("price_info")
                if not price_info:
                    result_text = app_result.get("result", "")
                    if not result_text:
                        all_apps_accurate = False
                        break
                    price_info = extract_price_from_message(result_text, app_result.get("app"))
                
                if not price_info:
                    all_apps_accurate = False
                    break
                
                total_fee = price_info.get("total_fee")
                delivery_fee = price_info.get("delivery_fee")
                pack_fee = price_info.get("pack_fee")
                
                if not all(fee is not None for fee in [total_fee, delivery_fee, pack_fee]):
                    all_apps_accurate = False
                    break
                
                if not isinstance(total_fee, (int, float)) or (not is_minimum_order and total_fee <= 0):
                    all_apps_accurate = False
                    break
                
                if not isinstance(delivery_fee, (int, float)) or delivery_fee < 0:
                    all_apps_accurate = False
                    break
                
                if not isinstance(pack_fee, (int, float)) or pack_fee < 0:
                    all_apps_accurate = False
                    break
            
            if all_apps_accurate:
                accurate_tasks += 1
        
        return accurate_tasks / total_tasks if total_tasks > 0 else 0.0
    
    @staticmethod
    def _calculate_price_accuracy_simple(results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """简单的价格准确率计算（备用方法）"""
        accurate = 0
        total = 0
        
        for result in results:
            if not result.success:
                continue
            
            result_data = result.result_data
            app_results = result_data.get("app_results", [])
            
            for app_result in app_results:
                if app_result.get("success"):
                    total += 1
                    if "price_info" in app_result or "price" in str(app_result.get("result", "")):
                        accurate += 1
        
        return accurate / total if total > 0 else 0.0
    
    @staticmethod
    def calculate_parallel_efficiency(original_results: List[TaskResult], orderwise_results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """计算并行效率提升（OrderWise vs 原始版本）"""
        if not task or task.category.value != "waimai_compare":
            return 0.0
        
        original_time = 0.0
        for result in original_results:
            if result.success:
                result_data = result.result_data
                app_results = result_data.get("app_results", [])
                original_time += sum(r.get("execution_time", 0) for r in app_results)
        
        orderwise_time = 0.0
        for result in orderwise_results:
            if result.success:
                orderwise_time = max(orderwise_time, result.execution_time)
        
        if original_time == 0:
            return 0.0
        
        # 计算效率提升百分比
        efficiency = (original_time - orderwise_time) / original_time
        return max(0.0, min(1.0, efficiency))  # 限制在0-1之间
    
    @staticmethod
    def calculate_multi_app_coverage(results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """计算多app覆盖率"""
        if not task or task.category.value != "waimai_compare":
            return 0.0
        
        expected_apps = task.expected_result.apps or []
        if not expected_apps:
            return 0.0
        
        total_expected = len(expected_apps)
        total_covered = 0
        successful_count = 0
        
        for result in results:
            if not result.success:
                continue
            
            successful_count += 1
            result_data = result.result_data
            successful_apps = result_data.get("successful_apps", 0)
            total_covered += successful_apps
        
        if successful_count == 0:
            return 0.0
        
        avg_covered = total_covered / successful_count
        return avg_covered / total_expected if total_expected > 0 else 0.0
    
    @staticmethod
    def calculate_scenario_detection_accuracy(results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """计算场景识别准确率（针对起送价场景）"""
        if not task or task.task_id != "1 App (minimum order)":
            return 0.0
        
        try:
            from phone_agent.utils.price_extractor import is_coupon_scenario
        except ImportError:
            return 0.0
        
        total_detections = 0
        accurate_detections = 0
        
        for result in results:
            if not result.success:
                continue
            
            result_data = result.result_data
            app_results = result_data.get("app_results", [])
            
            for app_result in app_results:
                if not app_result.get("success"):
                    continue
                
                result_text = app_result.get("result", "")
                if not result_text:
                    continue
                
                total_detections += 1
                if is_coupon_scenario(result_text):
                    accurate_detections += 1
        
        return accurate_detections / total_detections if total_detections > 0 else 0.0
    
    @staticmethod
    def calculate_minimum_order_amount_accuracy(results: List[TaskResult], task: Optional[TaskDefinition]) -> float:
        """计算起送价差额提取准确率"""
        if not task or task.task_id != "1 App (minimum order)":
            return 0.0
        
        try:
            from phone_agent.utils.price_extractor import detect_minimum_price, is_coupon_scenario
        except ImportError:
            return 0.0
        
        total_extractions = 0
        accurate_extractions = 0
        
        for result in results:
            if not result.success:
                continue
            
            result_data = result.result_data
            app_results = result_data.get("app_results", [])
            
            for app_result in app_results:
                if not app_result.get("success"):
                    continue
                
                result_text = app_result.get("result", "")
                if not result_text:
                    continue
                
                if not is_coupon_scenario(result_text):
                    continue
                
                total_extractions += 1
                amount_info = detect_minimum_price(result_text)
                if amount_info and amount_info.startswith("差") and "元起送" in amount_info:
                    accurate_extractions += 1
        
        return accurate_extractions / total_extractions if total_extractions > 0 else 0.0
    
    
    @staticmethod
    def calculate_all_metrics(results: List[TaskResult], task: Optional[TaskDefinition] = None) -> Dict[str, Any]:
        """计算所有指标"""
        successful_tasks = sum(1 for r in results if r.success)
        success_times = [r.execution_time for r in results if r.success]
        all_times = [r.execution_time for r in results]
        
        base_metrics = {
            "success_rate": MetricsCalculator.calculate_success_rate(results),
            "avg_execution_time": MetricsCalculator.calculate_avg_execution_time(results),
            "avg_steps": MetricsCalculator.calculate_avg_steps(results),
            "error_rate": MetricsCalculator.calculate_error_rate(results),
            "total_tasks": len(results),
            "successful_tasks": successful_tasks,
            "avg_execution_time_successful": sum(success_times) / len(success_times) if success_times else 0.0,
            "avg_execution_time_all": sum(all_times) / len(all_times) if all_times else 0.0,
        }
        
        if task and task.category.value == "waimai_compare":
            base_metrics.update({
                "price_extraction_accuracy": MetricsCalculator.calculate_price_extraction_accuracy(results, task),
                "multi_app_coverage": MetricsCalculator.calculate_multi_app_coverage(results, task),
            })
            
            if task.task_id == "1 App (minimum order)":
                base_metrics["scenario_detection_accuracy"] = MetricsCalculator.calculate_scenario_detection_accuracy(results, task)
                base_metrics["minimum_order_amount_accuracy"] = MetricsCalculator.calculate_minimum_order_amount_accuracy(results, task)
        
        return base_metrics
    
    @staticmethod
    def calculate_comparison_metrics(
        original_results: List[TaskResult],
        orderwise_results: List[TaskResult],
        task: Optional[TaskDefinition] = None
    ) -> Dict[str, Any]:
        """计算对比指标（原始版本对比 OrderWise 版本）"""
        comparison = {
            "original": MetricsCalculator.calculate_all_metrics(original_results, task),
            "orderwise": MetricsCalculator.calculate_all_metrics(orderwise_results, task),
        }
        
        if task and task.category.value == "waimai_compare":
            comparison["parallel_efficiency"] = MetricsCalculator.calculate_parallel_efficiency(
                original_results, orderwise_results, task
            )
            
            # 计算时间提升
            original_time = comparison["original"].get("avg_execution_time", 0)
            orderwise_time = comparison["orderwise"].get("avg_execution_time", 0)
            comparison["time_improvement"] = (original_time - orderwise_time) / original_time if original_time > 0 else 0.0
        
        return comparison

