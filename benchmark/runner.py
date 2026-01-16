#!/usr/bin/env python3
"""Benchmark 执行器 - 统一的任务评估和对比工具"""
import argparse
import json
import os
import sys
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from benchmark.core import TaskDefinition, Evaluator
from benchmark.core.base_adapter import BaseAdapter, TaskResult
from benchmark.core.metrics import MetricsCalculator
from benchmark.adapters import AutoGLMOriginalAdapter, AutoGLMOrderWiseAdapter
from benchmark.utils import get_project_root


def load_tasks(task_files: List[str]) -> List[TaskDefinition]:
    """加载任务定义"""
    tasks = []
    for task_file in task_files:
        task_path = Path(__file__).parent / task_file
        if not task_path.exists():
            print(f"Warning: Task file not found: {task_file}")
            continue
        
        with open(task_path, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
            if isinstance(task_data, list):
                tasks.extend([TaskDefinition.from_dict(t) for t in task_data])
            else:
                tasks.append(TaskDefinition.from_dict(task_data))
    
    return tasks


def print_summary(comparison: Dict[str, Any]) -> None:
    """打印评估摘要"""
    print("\n=== Benchmark Summary ===")
    for framework_name, metrics in comparison.items():
        if framework_name == "task_comparisons":
            continue
        
        overall = metrics.get("overall", {})
        successful_tasks = overall.get('successful_tasks', 0)
        total_tasks = overall.get('total_tasks', 0)
        
        print(f"\n{framework_name}:")
        print(f"  Success Rate: {overall.get('success_rate', 0):.2%} ({successful_tasks}/{total_tasks})")
        
        avg_time = overall.get('avg_execution_time', 0)
        if successful_tasks > 0:
            print(f"  Avg Execution Time: {avg_time:.2f}s (成功任务)")
        else:
            avg_time_all = overall.get('avg_execution_time_all', 0)
            print(f"  Avg Execution Time: {avg_time_all:.4f}s (所有任务，无成功任务)")
        
        if "price_extraction_accuracy" in overall:
            print(f"  Price Extraction Accuracy: {overall.get('price_extraction_accuracy', 0):.2%}")
            print(f"  Multi-App Coverage: {overall.get('multi_app_coverage', 0):.2%}")


def print_comparison(comparison: Dict[str, Any]) -> None:
    """打印版本对比结果"""
    if "task_comparisons" not in comparison:
        return
    
    print("\n=== Version Comparison ===")
    for task_id, task_comp in comparison["task_comparisons"].items():
        print(f"\nTask: {task_id}")
        if "parallel_efficiency" in task_comp:
            print(f"  Parallel Efficiency: {task_comp['parallel_efficiency']:.2%}")
        if "time_improvement" in task_comp:
            print(f"  Time Improvement: {task_comp['time_improvement']:.2%}")
        
        original_metrics = task_comp.get("original", {})
        orderwise_metrics = task_comp.get("orderwise", {})
        
        print(f"  Original - Execution Time: {original_metrics.get('avg_execution_time', 0):.2f}s")
        print(f"  OrderWise - Execution Time: {orderwise_metrics.get('avg_execution_time', 0):.2f}s")


def load_adapter(framework_config: Dict[str, Any]) -> BaseAdapter:
    """加载框架适配器"""
    adapter_name = framework_config.get("adapter")
    config_path = framework_config.get("config_path")
    
    adapter_config = {}
    if config_path:
        config_file = Path(__file__).parent / config_path
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                adapter_config = yaml.safe_load(f) or {}
    
    adapter_map = {
        "autoglm_adapter": AutoGLMOriginalAdapter,
        "orderwise_adapter": AutoGLMOrderWiseAdapter,
    }
    
    adapter_class = adapter_map.get(adapter_name)
    if not adapter_class:
        raise ValueError(f"Unknown adapter: {adapter_name}")
    
    return adapter_class(adapter_config)


def load_existing_results(results_file: str) -> Dict[str, Any]:
    """加载现有的结果文件，统一转换为数组格式以便处理"""
    if not os.path.exists(results_file):
        return {"results": {}, "comparison": {}}
    
    with open(results_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        results = data.get("results", {})
        
        # 统一转换为数组格式：单条记录 -> [记录]，数组 -> 数组
        normalized_results = {
            k: v if isinstance(v, list) else [v]
            for k, v in results.items()
        }
        
        return {
            "results": normalized_results,
            "comparison": data.get("comparison", {}),
        }


def update_result_in_file(
    results_file: str,
    framework_name: str,
    task_id: str,
    result: TaskResult
) -> None:
    """更新结果文件中的单个任务结果"""
    data = load_existing_results(results_file)
    result_dict = result.to_dict()
    results_list = data["results"].setdefault(framework_name, [])
    for i, existing in enumerate(results_list):
        if existing.get("task_id") == task_id:
            results_list[i] = result_dict
            break
    else:
        results_list.append(result_dict)
    
    # 单任务单框架场景：保存为单条记录，否则保存为数组
    if len(data["results"]) == 1 and len(results_list) == 1:
        data["results"][framework_name] = results_list[0]
    else:
        data["results"][framework_name] = results_list
    
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_single_task(
    evaluator: Evaluator,
    adapter: BaseAdapter,
    task: TaskDefinition,
    results_file: str
) -> TaskResult:
    """执行单个任务并更新结果文件"""
    print("\n" + "="*60)
    print(f"执行任务: {task.task_id}")
    print(f"框架: {adapter.get_framework_name()}")
    print(f"任务描述: {task.task}")
    print("="*60)
    
    result = evaluator.evaluate_task(adapter, task)
    
    print("\n" + "-"*60)
    status = "成功" if result.success else "失败"
    print(f"执行结果: {status}")
    print(f"执行时间: {result.execution_time:.2f}秒")
    if result.error:
        print(f"错误信息: {result.error}")
    print("-"*60)
    
    update_result_in_file(results_file, adapter.get_framework_name(), task.task_id, result)
    print(f"\n结果已保存到: {results_file}")
    
    return result


def interactive_mode(
    evaluator: Evaluator,
    adapters: List[BaseAdapter],
    tasks: List[TaskDefinition],
    output_dir: str
) -> int:
    """交互模式：可以指定任务ID，逐个执行任务"""
    results_file = os.path.join(output_dir, "results.json")
    task_map = {task.task_id: task for task in tasks}
    adapter_map = {adapter.get_framework_name(): adapter for adapter in adapters}
    
    print("\n" + "="*60)
    print("交互模式")
    print("="*60)
    print("\n可用任务:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task.task_id}: {task.task[:50]}...")
    
    print("\n可用框架:")
    for framework_name in adapter_map.keys():
        print(f"  - {framework_name}")
    
    while True:
        print("\n" + "-"*60)
        print("输入命令:")
        print("  task_id framework_name  - 执行指定任务")
        print("  list                    - 列出所有任务")
        print("  status                  - 查看当前结果状态")
        print("  quit/exit               - 退出")
        print("-"*60)
        
        command = input("\n> ").strip()
        
        if not command or command.lower() in ['quit', 'exit', 'q']:
            break
        
        if command.lower() == "list":
            for task in tasks:
                print(f"  - {task.task_id}: {task.task[:50]}...")
            continue
        
        if command.lower() == "status":
            _show_status(results_file)
            continue
        
        parts = command.split()
        if len(parts) != 2:
            print("错误: 格式应为 'task_id framework_name'")
            continue
        
        task_id, framework_name = parts
        
        task = task_map.get(task_id)
        if not task:
            print(f"错误: 任务 '{task_id}' 不存在")
            continue
        
        adapter = adapter_map.get(framework_name)
        if not adapter:
            print(f"错误: 框架 '{framework_name}' 不存在")
            continue
        
        run_single_task(evaluator, adapter, task, results_file)
    
    return 0


def _show_status(results_file: str) -> None:
    """显示当前结果状态"""
    data = load_existing_results(results_file)
    print("\n当前结果状态:")
    
    for framework_name, results_list in data.get("results", {}).items():
        if not results_list:
            continue
        print(f"\n  {framework_name}:")
        for result in results_list:
            status = "OK" if result.get("success") else "FAILED"
            print(f"    {status} {result.get('task_id')}: {result.get('execution_time', 0):.2f}s")


def get_app_device_mapping_path(frameworks_config: List[Dict[str, Any]]) -> Optional[str]:
    """获取应用到设备映射配置路径"""
    for framework_config in frameworks_config:
        if framework_config.get("name") != "orderwise":
            continue
        
        config_path = Path(__file__).parent / framework_config.get("config_path", "")
        if not config_path.exists():
            continue
        
        with open(config_path, 'r', encoding='utf-8') as f:
            orderwise_config = yaml.safe_load(f)
            app_device_mapping_path = orderwise_config.get("app_device_mapping_path")
            if not app_device_mapping_path:
                continue
            
            if os.path.isabs(app_device_mapping_path):
                return app_device_mapping_path
            
            return os.path.join(get_project_root(), app_device_mapping_path)
    
    return None


def batch_mode(
    evaluator: Evaluator,
    adapters: List[BaseAdapter],
    tasks: List[TaskDefinition],
    app_device_mapping_path: Optional[str],
    output_dir: str
) -> int:
    """批量模式：执行所有任务"""
    print("\nStarting benchmark evaluation...")
    results = evaluator.evaluate_tasks_separated(adapters, tasks, app_device_mapping_path)
    
    comparison = evaluator.calculate_comparison_metrics(results, tasks)
    
    if len(adapters) == 2:
        original_adapter = next((a for a in adapters if a.get_framework_name() == "autoglm"), None)
        orderwise_adapter = next((a for a in adapters if a.get_framework_name() == "orderwise"), None)
        
        if original_adapter and orderwise_adapter:
            task_comparisons = {}
            for task in tasks:
                original_results = [r for r in results.get("autoglm", []) if r.task_id == task.task_id]
                orderwise_results = [r for r in results.get("orderwise", []) if r.task_id == task.task_id]
                
                if original_results and orderwise_results:
                    task_comparisons[task.task_id] = MetricsCalculator.calculate_comparison_metrics(
                        original_results, orderwise_results, task
                    )
            
            comparison["task_comparisons"] = task_comparisons
    
    os.makedirs(output_dir, exist_ok=True)
    results_file = os.path.join(output_dir, "results.json")
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(
            {
                "results": {k: [r.to_dict() for r in v] for k, v in results.items()},
                "comparison": comparison,
            },
            f,
            indent=2,
            ensure_ascii=False
        )
    
    print(f"\nResults saved to: {results_file}")
    print_summary(comparison)
    print_comparison(comparison)
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run benchmark comparison")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/benchmark_config.yaml",
        help="Benchmark config file"
    )
    parser.add_argument(
        "--frameworks",
        nargs="+",
        help="Specific frameworks to test (default: all enabled)"
    )
    parser.add_argument(
        "--task-filter",
        nargs="+",
        help="Filter tasks by category"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for results"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode: run all tasks automatically (default: interactive mode)"
    )
    parser.add_argument(
        "--task-id",
        type=str,
        help="Task ID to run (requires --framework, runs single task and exits)"
    )
    parser.add_argument(
        "--framework",
        type=str,
        help="Framework name to use (requires --task-id, runs single task and exits)"
    )
    
    args = parser.parse_args()
    
    config_path = Path(__file__).parent / args.config
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        return 1
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    task_files = config.get("tasks", {}).get("task_files", [])
    tasks = load_tasks(task_files)
    
    if args.task_filter:
        tasks = [t for t in tasks if t.category.value in args.task_filter]
    
    print(f"Loaded {len(tasks)} tasks")
    
    frameworks_config = config.get("frameworks", [])
    adapters = []
    
    for framework_config in frameworks_config:
        if not framework_config.get("enabled", True):
            continue
        
        framework_name = framework_config.get("name")
        if args.frameworks and framework_name not in args.frameworks:
            continue
        
        print(f"Loading adapter: {framework_name}")
        adapter = load_adapter(framework_config)
        
        if adapter.initialize():
            adapters.append(adapter)
            print(f"  {framework_name} initialized")
        else:
            print(f"  {framework_name} initialization failed")
    
    if not adapters:
        print("Error: No adapters initialized")
        return 1
    
    evaluator = Evaluator()
    output_dir = args.output_dir or config.get("evaluation", {}).get("output_dir", "results")
    results_file = os.path.join(output_dir, "results.json")
    
    if args.task_id and args.framework:
        task_map = {task.task_id: task for task in tasks}
        adapter_map = {adapter.get_framework_name(): adapter for adapter in adapters}
        task = task_map.get(args.task_id)
        adapter = adapter_map.get(args.framework)
        
        if not task:
            print(f"Error: Task '{args.task_id}' not found")
            return 1
        if not adapter:
            print(f"Error: Framework '{args.framework}' not found")
            return 1
        
        run_single_task(evaluator, adapter, task, results_file)
    elif args.batch:
        app_device_mapping_path = get_app_device_mapping_path(frameworks_config)
        batch_mode(evaluator, adapters, tasks, app_device_mapping_path, output_dir)
    else:
        interactive_mode(evaluator, adapters, tasks, output_dir)
    
    for adapter in adapters:
        adapter.cleanup()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

