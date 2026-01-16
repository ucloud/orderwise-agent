# 外卖比价 Benchmark - OrderWise vs 原始GLM

专门用于对比**原始GLM版本**和**OrderWise版本**在外卖比价任务上的表现。

对比**原始AutoGLM版本**（顺序执行）和**OrderWise版本**（并行执行）在外卖比价任务上的表现。

## 快速开始

### 1. 配置模型服务

编辑配置文件，设置模型服务地址：

**原始版本配置** (`configs/framework_configs/autoglm.yaml`):
```yaml
base_url: "http://localhost:4244/v1"
model: "autoglm-phone-9b"
```

**OrderWise版本配置** (`configs/framework_configs/orderwise.yaml`):
```yaml
base_url: "http://localhost:4244/v1"
model: "autoglm-phone-9b"
apps_config_path: "examples/apps_config.json"
app_device_mapping_path: "examples/app_device_mapping.json"
```

### 2. 运行Benchmark

```bash
# 运行完整benchmark（对比两个版本）
cd benchmark
python runner.py

# 使用自定义配置
python runner.py --config configs/benchmark_config.yaml

# 指定输出目录
python runner.py --output-dir results/waimai_benchmark_$(date +%Y%m%d)
```

### 3. 查看和对比结果

运行 `runner.py` 后，结果保存在 `results/benchmark_results.json`。

运行 `compare_results.py` 对比两个版本并生成对比指标：

```bash
python compare_results.py --results-file results/benchmark_results.json
```

对比结果包括：并行效率提升、时间提升、价格提取准确率、多app覆盖率等。

## 目录结构

```
benchmark/
├── core/              # 核心组件（适配器、评估器、指标计算）
├── adapters/          # 框架适配器（autoglm、orderwise）
├── tasks/             # 任务定义（waimai_compare_tasks.json）
├── configs/           # 配置文件（autoglm.yaml、orderwise.yaml）
├── results/           # 结果目录（运行后生成）
├── runner.py          # 主运行器
└── compare_results.py # 结果对比工具
```

## 任务类型

- **单app比价** - 基础价格查询
- **双app并行比价** - 测试并行执行能力
- **带商家名称的比价** - 测试指定商家搜索
- **凑单场景** - 测试起送价场景处理
- **三app并行比价+找最便宜** - 综合测试

### 任务格式示例

```json
{
  "task_id": "2 Apps (no seller)",
  "category": "waimai_compare",
  "task": "比较美团和京东外卖上'去云南'的价格",
  "expected_result": {
    "type": "price_comparison",
    "apps": ["美团", "京东外卖"],
    "product": "去云南",
    "parallel": true
  },
    "evaluation": {
      "success_criteria": [
        "都搜索到目标商品",
        "价格信息正确提取（price, delivery_fee, pack_fee, total_fee）"
      ],
    "metrics": [
      "success_rate",
      "execution_time",
      "parallel_efficiency",
      "price_extraction_accuracy",
      "multi_app_coverage"
    ],
    "timeout": 180
  }
}
```

## 评估指标

- **基础指标**：任务完成率、执行时间、执行步数
- **价格提取准确率**：评估 price, delivery_fee, pack_fee, total_fee 四个字段
- **多app覆盖率**：成功比价的app数量 / 期望的app数量
- **并行效率提升**：(顺序执行时间 - 并行执行时间) / 顺序执行时间
- **时间提升**：(原始版本时间 - OrderWise时间) / 原始版本时间

## 结果解读

重点关注指标：
- **并行效率提升**：值越大越好，0.5 表示时间节省50%
- **时间提升**：OrderWise相比原始版本的提升，0.6 表示快60%
- **价格提取准确率**：OrderWise应明显高于原始版本
- **多app覆盖率**：成功比价的app比例

### 示例输出

```
=== Version Comparison ===

Task: 2 Apps (no seller)
  Parallel Efficiency: 45.23%
  Time Improvement: 48.50%
  Original - Execution Time: 125.30s
  OrderWise - Execution Time: 64.50s
```

## 注意事项

- 确保有足够的设备用于并行执行
- 确保模型服务正常运行
- 确保网络连接正常
- 确保 `examples/apps_config.json` 配置正确
