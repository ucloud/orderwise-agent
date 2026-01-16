#!/usr/bin/env python3
"""
OrderWise MCP 模式在 UCloud Sandbox 上的部署脚本

使用方法:
1. 设置环境变量: export AGENTBOX_API_KEY=your_api_key
2. 运行脚本: python build_template.py
"""

import argparse
import os
import sys
from pathlib import Path

from ucloud_sandbox import Template, Sandbox, default_build_logger

# OrderWise 项目根目录（相对于当前脚本）
PROJECT_ROOT = Path(__file__).parent.parent
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
TEMPLATE_ALIAS = "orderwise-mcp"


def load_requirements():
    """从 requirements.txt 加载依赖（排除 vllm，MCP 模式使用外部模型服务）"""
    if not REQUIREMENTS_FILE.exists():
        return []
    exclude_packages = ['vllm', 'sglang', 'transformers']  # 模型部署相关包，MCP 模式不需要
    with open(REQUIREMENTS_FILE, 'r') as f:
        deps = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if not any(pkg in line.lower() for pkg in exclude_packages):
                    deps.append(line)
    return deps


def define_template():
    """定义 OrderWise MCP 模式的 Template"""
    requirements = load_requirements()
    
    context_path = PROJECT_ROOT.parent
    project_rel_path = PROJECT_ROOT.name
    
    return (
        Template(
            file_context_path=str(context_path),
            file_ignore_patterns=[".git", "__pycache__", "*.pyc", ".DS_Store", "logs", "*.log", "benchmark/results"]
        )
        .from_python_image("3.11")
        .apt_install(["android-tools-adb", "git", "curl", "wget"])
        .pip_install(requirements if requirements else [
            "PyYAML>=6.0", "Pillow==12.0.0", "pydantic==2.12.5",
            "openai==2.9.0", "pymongo==4.15.5", "starlette==0.50.0",
            "mcp>=1.0.0", "fastmcp>=0.1.0"
        ])
        .copy(
            project_rel_path,
            "/workspace/orderwise-agent"
        )
        .run_cmd("cd /workspace/orderwise-agent && pip install .", user="root")
        .set_envs({"PYTHONPATH": "/workspace/orderwise-agent"})
    )


def create_sandbox(template_alias: str = TEMPLATE_ALIAS, skip_build: bool = False):
    """创建 Sandbox 实例"""
    if not skip_build:
        print("构建 Template...")
        template = define_template()
        build_info = Template.build(
            template,
            alias=template_alias,
            cpu_count=2,
            memory_mb=2048,
            on_build_logs=default_build_logger()
        )
        print(f"Template 构建完成: {build_info.template_id}")
    
    print("创建 Sandbox...")
    sandbox = Sandbox.create(template=template_alias, timeout=1200)
    print(f"Sandbox 创建成功: {sandbox.sandbox_id}")
    
    if sandbox.commands.run("adb version", timeout=10).exit_code == 0:
        print("ADB 已安装")
    
    return sandbox


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="部署 OrderWise MCP 到 UCloud Sandbox")
    parser.add_argument("--skip-build", action="store_true", help="跳过 Template 构建（使用已存在的 Template）")
    args = parser.parse_args()
    
    if not os.getenv("AGENTBOX_API_KEY"):
        print("错误: 请设置环境变量 AGENTBOX_API_KEY")
        sys.exit(1)
    
    if not PROJECT_ROOT.exists():
        print(f"错误: 找不到项目目录: {PROJECT_ROOT}")
        sys.exit(1)
    
    print("=" * 60)
    print("OrderWise MCP 模式 - UCloud Sandbox 部署")
    print("=" * 60)
    
    sandbox = create_sandbox(skip_build=args.skip_build)
    
    print("\n" + "=" * 60)
    print("部署完成!")
    print("=" * 60)
    print(f"\nSandbox ID: {sandbox.sandbox_id}")
    print("\n下一步:")
    print("1. 连接 Android 设备: adb connect your-cloud-phone-ip:port")
    print("2. 配置设备映射和模型服务")
    print("3. 启动 MCP 服务器")


if __name__ == "__main__":
    main()

