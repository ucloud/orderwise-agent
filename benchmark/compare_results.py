#!/usr/bin/env python3
"""对比 autoglm 和 orderwise 的结果"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List


project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from benchmark.core import TaskDefinition, Evaluator
from benchmark.core.base_adapter import TaskResult
from benchmark.core.metrics import MetricsCalculator


def load_tasks(task_files: List[str]) -> List[TaskDefinition]:
    """加载任务定义"""
    tasks = []
    base_path = Path(__file__).parent
    
    for task_file in task_files:
        task_path = base_path / task_file
        if not task_path.exists():
            print(f"Warning: Task file not found: {task_file}")
            continue
        
        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            tasks.extend(
                [TaskDefinition.from_dict(t) for t in task_data] 
                if isinstance(task_data, list) 
                else [TaskDefinition.from_dict(task_data)]
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading {task_file}: {e}")
    
    return tasks


def json_to_task_result(result_dict: Dict) -> TaskResult:
    """将 JSON 结果转换为 TaskResult 对象"""
    return TaskResult(
        task_id=result_dict["task_id"],
        framework_name=result_dict["framework_name"],
        success=result_dict["success"],
        execution_time=result_dict["execution_time"],
        steps=result_dict.get("steps", 0),
        result_data=result_dict.get("result_data", {}),
        error=result_dict.get("error"),
        screenshots=[],
    )


def load_results(results_file: Path) -> Dict[str, List[TaskResult]]:
    """加载结果文件并转换为 TaskResult 对象"""
    if not results_file.exists():
        print(f"Error: Results file not found: {results_file}")
        return {}
    
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading results file: {e}")
        return {}
    
    results = data.get("results", {})
    return {
        framework_name: [
            json_to_task_result(r) 
            for r in (framework_results if isinstance(framework_results, list) else [framework_results])
        ]
        for framework_name, framework_results in results.items()
    }


def print_summary(comparison: Dict) -> None:
    """打印benchmark摘要（表格形式）"""
    print("\n=== Benchmark Summary ===")
    
    # 收集所有框架的数据
    frameworks_data = {}
    for framework_name, metrics in comparison.items():
        if framework_name == "task_comparisons":
            continue
        frameworks_data[framework_name] = metrics.get("overall", {})
    
    if not frameworks_data:
        return
    
    task_comparisons = comparison.get("task_comparisons", {})
    comparison_metrics = {}
    if len(frameworks_data) == 2 and task_comparisons:
        orig_execution_times = []
        order_execution_times = []
        orig_price_accuracies = []
        order_price_accuracies = []
        orig_success_rates = []
        order_success_rates = []
        
        for task_comp in task_comparisons.values():
            orig = task_comp.get("original", {})
            order = task_comp.get("orderwise", {})
            
            if "avg_execution_time" in orig:
                orig_execution_times.append(orig["avg_execution_time"])
            if "avg_execution_time" in order:
                order_execution_times.append(order["avg_execution_time"])
            
            if "price_extraction_accuracy" in orig:
                orig_price_accuracies.append(orig["price_extraction_accuracy"])
            if "price_extraction_accuracy" in order:
                order_price_accuracies.append(order["price_extraction_accuracy"])
            
            if "success_rate" in orig:
                orig_success_rates.append(orig["success_rate"])
            if "success_rate" in order:
                order_success_rates.append(order["success_rate"])
        
        if orig_execution_times and order_execution_times:
            avg_orig_time = sum(orig_execution_times) / len(orig_execution_times)
            avg_order_time = sum(order_execution_times) / len(order_execution_times)
            time_improvement = (avg_orig_time - avg_order_time) / avg_orig_time if avg_orig_time > 0 else 0.0
            comparison_metrics["avg_execution_time"] = time_improvement
        
        if orig_price_accuracies and order_price_accuracies:
            avg_orig_price = sum(orig_price_accuracies) / len(orig_price_accuracies)
            avg_order_price = sum(order_price_accuracies) / len(order_price_accuracies)
            price_improvement = (avg_order_price - avg_orig_price) / avg_orig_price if avg_orig_price > 0 else 0.0
            comparison_metrics["price_extraction_accuracy"] = price_improvement
        
        if orig_success_rates and order_success_rates:
            avg_orig_success = sum(orig_success_rates) / len(orig_success_rates)
            avg_order_success = sum(order_success_rates) / len(order_success_rates)
            success_improvement = (avg_order_success - avg_orig_success) / avg_orig_success if avg_orig_success > 0 else 0.0
            comparison_metrics["success_rate"] = success_improvement
    
    # 准备表格数据
    headers = ["Metric"]
    for framework_name in frameworks_data.keys():
        headers.append(framework_name.capitalize())
    if comparison_metrics:
        headers.append("Improvement")
    
    rows = []
    
    # Avg Execution Time
    row = ["Avg Execution Time"]
    for framework_name in frameworks_data.keys():
        overall = frameworks_data[framework_name]
        avg_time = overall.get('avg_execution_time_all', 0) or overall.get('avg_execution_time', 0)
        row.append(f"{avg_time:.2f}s")
    if "avg_execution_time" in comparison_metrics:
        imp = comparison_metrics["avg_execution_time"]
        row.append(f"{imp:+.2%}" if imp != 0 else "-")
    rows.append(row)
    
    # Success Rate
    row = ["Avg Success Rate"]
    for framework_name in frameworks_data.keys():
        overall = frameworks_data[framework_name]
        successful_tasks = overall.get('successful_tasks', 0)
        total_tasks = overall.get('total_tasks', 0)
        success_rate = overall.get('success_rate', 0)
        row.append(f"{success_rate:.2%} ({successful_tasks}/{total_tasks})")
    if "success_rate" in comparison_metrics:
        imp = comparison_metrics["success_rate"]
        row.append(f"{imp:+.2%}" if imp != 0 else "-")
    elif comparison_metrics:
        row.append("-")
    rows.append(row)
    
    # Price Extraction Accuracy
    if any("price_extraction_accuracy" in frameworks_data[f] for f in frameworks_data.keys()):
        row = ["Avg Price Extraction Accuracy"]
        for framework_name in frameworks_data.keys():
            overall = frameworks_data[framework_name]
            accuracy = overall.get('price_extraction_accuracy', 0)
            row.append(f"{accuracy:.2%}" if accuracy > 0 else "-")
        if "price_extraction_accuracy" in comparison_metrics:
            imp = comparison_metrics["price_extraction_accuracy"]
            row.append(f"{imp:+.2%}" if imp != 0 else "-")
        rows.append(row)
    
    # 确保所有行都有相同的列数
    num_cols = len(headers)
    for row in rows:
        while len(row) < num_cols:
            row.append("-")
    
    # 打印表格
    col_widths = [max(len(str(row[i])) for row in [headers] + rows) for i in range(len(headers))]
    
    def print_row(row_data, is_header=False):
        formatted = " | ".join(str(item).ljust(col_widths[i]) for i, item in enumerate(row_data))
        print(f"  {formatted}")
        if is_header:
            separator = "-" * (sum(col_widths) + 3 * (len(headers) - 1))
            print(f"  {separator}")
    
    print()
    print_row(headers, is_header=True)
    for row in rows:
        print_row(row)




def print_comparison(comparison: Dict, tasks: List[TaskDefinition] = None) -> None:
    """打印版本对比结果"""
    task_comparisons = comparison.get("task_comparisons", {})
    if not task_comparisons:
        print("\n没有可对比的任务（需要两个框架都有结果）")
        return
    
    print("\n=== Version Comparison ===")
    for task_id, task_comp in task_comparisons.items():
        print(f"\nTask: {task_id}")
        
        orig = task_comp.get("original", {})
        order = task_comp.get("orderwise", {})
        
        print(f"  Autoglm: {orig.get('avg_execution_time', 0):.2f}s, "
              f"Success: {orig.get('success_rate', 0):.2%}")
        print(f"  OrderWise: {order.get('avg_execution_time', 0):.2f}s, "
              f"Success: {order.get('success_rate', 0):.2%}")
        
        if "parallel_efficiency" in task_comp:
            print(f"  Parallel Efficiency: {task_comp['parallel_efficiency']:.2%}")
        
        if "time_improvement" in task_comp:
            imp = task_comp['time_improvement']
            faster = "OrderWise" if imp > 0 else "autoglm"
            print(f"  Time Improvement: {abs(imp):.2%} ({faster}更快)")
        
        if "price_extraction_accuracy" in orig or "price_extraction_accuracy" in order:
            print(f"  Price Extraction: Autoglm {orig.get('price_extraction_accuracy', 0):.2%}, "
                  f"OrderWise {order.get('price_extraction_accuracy', 0):.2%}")


def main():
    parser = argparse.ArgumentParser(description="对比 autoglm 和 orderwise 的结果")
    parser.add_argument(
        "--results-file",
        type=str,
        default="results/results.json",
        help="结果文件路径"
    )
    parser.add_argument(
        "--task-files",
        nargs="+",
        default=["tasks/waimai_compare_tasks.json"],
        help="任务定义文件"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="更新结果文件中的 comparison 字段"
    )
    
    args = parser.parse_args()
    base_path = Path(__file__).parent
    
    # 加载任务定义
    tasks = load_tasks(args.task_files)
    if not tasks:
        print("Error: No tasks loaded")
        return 1
    print(f"Loaded {len(tasks)} tasks")
    
    # 加载结果
    results_file = base_path / args.results_file
    task_results = load_results(results_file)
    if not task_results:
        return 1
    
    print(f"\nLoaded results for frameworks: {list(task_results.keys())}")
    
    # 计算对比指标
    comparison = Evaluator().calculate_comparison_metrics(task_results, tasks)
    
    # 计算任务级别的对比（如果两个框架都有结果）
    if "autoglm" in task_results and "orderwise" in task_results:
        orig_map = {r.task_id: r for r in task_results["autoglm"]}
        order_map = {r.task_id: r for r in task_results["orderwise"]}
        comparison["task_comparisons"] = {
            task.task_id: MetricsCalculator.calculate_comparison_metrics(
                [orig_map[task.task_id]], [order_map[task.task_id]], task
            )
            for task in tasks
            if task.task_id in orig_map and task.task_id in order_map
        }
    
    # 打印结果
    print_summary(comparison)
    print_comparison(comparison, tasks)
    
    # 更新结果文件
    if args.update:
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["comparison"] = comparison
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\n已更新 {results_file} 中的 comparison 字段")
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error updating results file: {e}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

