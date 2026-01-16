"""统一评估器"""
import json
import os
import subprocess
import time
from typing import List, Dict, Any, Optional
from .base_adapter import BaseAdapter, TaskResult
from .task_definition import TaskDefinition
from .metrics import MetricsCalculator
from ..utils import get_project_root

_home_func = None

def _get_home_func():
    """延迟导入 home 函数以避免循环依赖"""
    global _home_func
    if _home_func is None:
        from phone_agent.adb import home
        _home_func = home
    return _home_func


class Evaluator:
    """统一评估器"""
    
    def __init__(self):
        self.metrics_calculator = MetricsCalculator()
        self._app_packages_cache: Optional[Dict[str, str]] = None
    
    def _get_app_packages(self) -> Dict[str, str]:
        """获取app名称到包名的映射（缓存）"""
        if self._app_packages_cache is not None:
            return self._app_packages_cache
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        apps_config_path = os.path.join(project_root, "examples/apps_config.json")
        
        self._app_packages_cache = {}
        if not os.path.exists(apps_config_path):
            return self._app_packages_cache
        
        with open(apps_config_path, 'r', encoding='utf-8') as f:
            apps_config = json.load(f)
        
        for app_key, app_info in apps_config.items():
            app_name = app_info.get("name")
            package = app_info.get("package")
            if app_name and package:
                self._app_packages_cache[app_name] = package
        
        return self._app_packages_cache
    
    def _get_app_devices(self, adapter: BaseAdapter, task: TaskDefinition) -> Dict[str, str]:
        """获取app名称到device_id的映射"""
        devices = {}
        apps = task.expected_result.apps or []
        framework_name = adapter.get_framework_name()
        
        if framework_name == "autoglm":
            device_id = getattr(adapter, 'device_id', None)
            if device_id:
                devices = {app: device_id for app in apps}
        elif hasattr(adapter, '_build_app_to_device_mapping'):
            mapping = adapter._build_app_to_device_mapping()
            devices = {app: device_id for app in apps if (device_id := mapping.get(app))}
        elif hasattr(adapter, '_get_device_for_app'):
            devices = {app: device_id for app in apps if (device_id := adapter._get_device_for_app(app))}
        
        return devices
    
    @staticmethod
    def _force_stop_app(device_id: str, package: str) -> None:
        """强制关闭app"""
        subprocess.run(
            ["adb", "-s", device_id, "shell", "am", "force-stop", package],
            capture_output=True,
            timeout=5,
            check=False
        )
    
    def _cleanup_task_apps(self, adapter: BaseAdapter, task: TaskDefinition) -> None:
        """关闭任务中使用的app"""
        apps = task.expected_result.apps or []
        if not apps:
            return
        
        app_packages = self._get_app_packages()
        app_devices = self._get_app_devices(adapter, task)
        
        for app_name in apps:
            package = app_packages.get(app_name)
            device_id = app_devices.get(app_name)
            
            if package and device_id:
                self._force_stop_app(device_id, package)
    
    def evaluate_task(
        self,
        adapter: BaseAdapter,
        task: TaskDefinition,
    ) -> TaskResult:
        """评估单个任务"""
        start_time = time.time()
        
        adapter.reset_environment()
        result = adapter.execute_task(task)
        
        # 计算执行时间（不包括清理时间）
        result.execution_time = time.time() - start_time
        
        self._cleanup_task_apps(adapter, task)
        time.sleep(2.0)
        
        if task.evaluation.timeout and result.execution_time > task.evaluation.timeout:
            result.success = False
            result.error = f"Task timeout ({result.execution_time:.2f}s > {task.evaluation.timeout}s)"
        
        return result
    
    def evaluate_tasks_separated(
        self,
        adapters: List[BaseAdapter],
        tasks: List[TaskDefinition],
        app_device_mapping_path: Optional[str] = None,
    ) -> Dict[str, List[TaskResult]]:
        """分开测试每个版本，避免设备状态污染"""
        all_results = {}
        home = _get_home_func()
        
        for i, adapter in enumerate(adapters):
            framework_name = adapter.get_framework_name()
            print(f"\n{'='*60}")
            print(f"Testing {framework_name} ({i+1}/{len(adapters)})...")
            print(f"{'='*60}")
            
            all_results[framework_name] = []
            
            for j, task in enumerate(tasks, 1):
                print(f"\n[{j}/{len(tasks)}] {task.task_id}: {task.task[:50]}...")
                result = self.evaluate_task(adapter, task)  # 已包含关闭应用和等待2秒
                all_results[framework_name].append(result)
                status = "OK" if result.success else "FAILED"
                print(f"  {status} {result.execution_time:.2f}s")
            
            adapter.cleanup()
            
            if app_device_mapping_path and i < len(adapters) - 1:
                self._cleanup_devices(app_device_mapping_path, home)
        
        return all_results
    
    @staticmethod
    def _cleanup_devices(app_device_mapping_path: str, home_func) -> None:
        """清理所有设备状态"""
        if not os.path.exists(app_device_mapping_path):
            return
        
        with open(app_device_mapping_path, 'r') as f:
            app_device_mapping = json.load(f)
        
        device_ids = list(app_device_mapping.values())
        print(f"\n清理 {len(device_ids)} 台设备...")
        
        for device_id in device_ids:
            home_func(device_id=device_id, delay=0.5)
            print(f"  {device_id}")
        
        time.sleep(1)
    
    def calculate_comparison_metrics(
        self,
        results: Dict[str, List[TaskResult]],
        tasks: List[TaskDefinition],
    ) -> Dict[str, Dict[str, Any]]:
        """计算对比指标"""
        comparison = {}
        
        for framework_name, framework_results in results.items():
            # 按任务分组
            task_results_map = {}
            for result in framework_results:
                if result.task_id not in task_results_map:
                    task_results_map[result.task_id] = []
                task_results_map[result.task_id].append(result)
            
            # 计算每个任务的指标
            task_metrics = {}
            for task in tasks:
                task_results = task_results_map.get(task.task_id, [])
                if task_results:
                    task_metrics[task.task_id] = self.metrics_calculator.calculate_all_metrics(
                        task_results, task
                    )
            
            # 计算总体指标
            all_results = [r for results_list in task_results_map.values() for r in results_list]
            sample_task = tasks[0] if tasks else None
            overall_metrics = self.metrics_calculator.calculate_all_metrics(
                all_results, sample_task
            ) if all_results else {}
            
            # 按任务分别计算价格提取准确率后取平均值
            if "price_extraction_accuracy" in overall_metrics and task_metrics:
                task_accuracies = []
                for task in tasks:
                    if task.task_id in task_metrics:
                        accuracy = task_metrics[task.task_id].get("price_extraction_accuracy")
                        if accuracy is not None:
                            task_accuracies.append(accuracy)
                if task_accuracies:
                    overall_metrics["price_extraction_accuracy"] = sum(task_accuracies) / len(task_accuracies)
            
            comparison[framework_name] = {
                "overall": overall_metrics,
                "per_task": task_metrics,
            }
        
        return comparison
