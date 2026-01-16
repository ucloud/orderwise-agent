#!/usr/bin/env python3
"""
OrderWise MCP 模式 Sandbox 配置脚本

使用方法:
1. 构建 Template 并部署 Sandbox: python build_template.py
2. 配置 Sandbox: python configure_sandbox.py --sandbox-id <sandbox_id> [选项]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from ucloud_sandbox import Sandbox


def connect_devices(sandbox: Sandbox, device_ips: list[str], adbkey_path: Optional[str] = None):
    """连接 Android 设备"""
    print("连接 Android 设备...")
    
    # 重置 ADB 服务器
    print("   重置 ADB 服务器...")
    sandbox.commands.run("adb kill-server", timeout=10)
    
    # 清理旧密钥（无论是否提供新密钥）
    sandbox.commands.run("rm -f ~/.android/adbkey* 2>/dev/null || true", timeout=10)
    sandbox.commands.run("mkdir -p ~/.android", timeout=10)
    
    if adbkey_path:
        # 使用指定的 adbkey（私钥）
        print(f"   使用指定的 ADB 密钥: {adbkey_path}")
        
        if os.path.exists(adbkey_path):
            with open(adbkey_path, 'rb') as f:
                adbkey_content = f.read()
            sandbox.files.write("~/.android/adbkey", adbkey_content)
            # 设置正确的文件权限（ADB 要求私钥权限为 600）
            sandbox.commands.run("chmod 600 ~/.android/adbkey", timeout=10)
            
            # 尝试复制对应的公钥（如果存在）
            pub_key_path = adbkey_path + '.pub'
            if os.path.exists(pub_key_path):
                with open(pub_key_path, 'rb') as f:
                    pub_key_content = f.read()
                sandbox.files.write("~/.android/adbkey.pub", pub_key_content)
                sandbox.commands.run("chmod 644 ~/.android/adbkey.pub", timeout=10)
            
            print("   ADB 密钥已复制到 sandbox")
        else:
            print(f"   警告: 本地文件不存在: {adbkey_path}")
            print("   将生成新密钥")
    
    # 启动 ADB 服务器
    sandbox.commands.run("adb start-server", timeout=10)
    
    for i, device_ip in enumerate(device_ips, 1):
        print(f"   连接设备 {i}: {device_ip}...")
        result = sandbox.commands.run(f"adb connect {device_ip}", timeout=10)
        if result.exit_code == 0:
            print(f"设备 {i} 连接成功: {device_ip}")
        else:
            print(f"设备 {i} 连接失败: {device_ip}")
            print(f"   错误: {result.stderr}")
    
    print("\n已连接的设备:")
    result = sandbox.commands.run("adb devices", timeout=10)
    print(result.stdout)
    
    if "unauthorized" in result.stdout:
        print("\n设备未授权，等待授权中（最多 60 秒）...")
        for waited in range(0, 60, 3):
            time.sleep(3)
            result = sandbox.commands.run("adb devices", timeout=10)
            if "unauthorized" not in result.stdout and "device" in result.stdout:
                print("设备已授权")
                return
            if waited % 15 == 0 and waited > 0:
                print(f"   已等待 {waited} 秒...")
        print("等待超时，部分设备可能仍未授权")


def configure_device_mapping(sandbox: Sandbox, device_ips: list[str]):
    """配置设备映射"""
    print("\n配置设备映射...")
    
    if len(device_ips) < 3:
        print("警告: 需要至少 3 台设备（美团、京东外卖、淘宝闪购）")
        device_ips = device_ips + ["未配置"] * (3 - len(device_ips))
    
    mapping = {
        "app1": device_ips[0],
        "app2": device_ips[1],
        "app3": device_ips[2],
    }
    
    mapping_path = "/workspace/orderwise-agent/mcp_mode/mcp_server/app_device_mapping.json"
    sandbox.files.write(mapping_path, json.dumps(mapping, indent=2, ensure_ascii=False))
    print(f"设备映射已配置: {mapping_path}")
    print(json.dumps(mapping, indent=2, ensure_ascii=False))


def configure_model_service(sandbox: Sandbox, provider: str, api_base: str, api_key: str, model_name: str):
    """配置模型服务（写入 env.sh）"""
    print(f"\n配置模型服务...")
    env_content = f"""export PHONE_AGENT_BASE_URL="{api_base}"
export PHONE_AGENT_API_KEY="{api_key}"
export PHONE_AGENT_MODEL="{model_name}"
export PHONE_AGENT_MAX_STEPS="100"
"""
    sandbox.files.write("/workspace/orderwise-agent/env.sh", env_content)
    print("模型配置已保存")


def start_mcp_server(sandbox: Sandbox, background: bool = True):
    """启动 MCP 服务器"""
    print("\n启动 MCP 服务器...")
    cmd = "cd /workspace/orderwise-agent && source env.sh && python mcp_mode/mcp_server/order_wise_mcp_server.py"
    
    if background:
        sandbox.commands.run(f"{cmd} > /tmp/mcp_server.log 2>&1 &", timeout=10)
        print("MCP 服务器启动命令已执行")
        time.sleep(30)
        
        proc = sandbox.commands.run("ps aux | grep -v grep | grep order_wise_mcp_server || true", timeout=10)
        if proc.stdout.strip():
            print("   进程运行中")
        else:
            print("   进程未找到，查看启动日志:")
            log = sandbox.commands.run("tail -50 /tmp/mcp_server.log 2>/dev/null || echo '无日志'", timeout=10)
            print(log.stdout[:500])
    else:
        result = sandbox.commands.run(cmd, timeout=5)
        if result.exit_code != 0:
            print(f"启动失败: {result.stderr}")


def verify_service(sandbox: Sandbox):
    """验证服务状态"""
    print("\n验证服务状态...")
    
    for i in range(5):
        result = sandbox.commands.run("curl -s http://localhost:8703/ 2>&1 || true", timeout=10)
        if result.exit_code == 0 and "status" in result.stdout.lower():
            print("MCP 服务器运行正常")
            return
        if i < 4:
            print(f"   等待中... ({i+1}/5)")
            time.sleep(2)
    
    print("\n服务器未响应")
    proc = sandbox.commands.run("ps aux | grep -v grep | grep order_wise_mcp_server || true", timeout=10)
    port = sandbox.commands.run("netstat -tlnp 2>/dev/null | grep 8703 || ss -tlnp 2>/dev/null | grep 8703 || true", timeout=10)
    print(f"   进程: {'运行中' if proc.stdout.strip() else '未找到'}")
    print(f"   端口: {'监听中' if '8703' in port.stdout else '未监听'}")


def main():
    parser = argparse.ArgumentParser(description="配置 OrderWise MCP Sandbox")
    parser.add_argument("--sandbox-id", required=True, help="Sandbox ID（从部署脚本获取）")
    parser.add_argument("--devices", nargs="+", help="Android 设备 IP:端口列表（至少 3 个）")
    parser.add_argument("--model-provider", choices=["zhipu", "local", "openai"], 
                       help="模型提供商（默认: 从环境变量或配置文件推断）")
    parser.add_argument("--model-api-base", help="模型 API 地址（默认: 从环境变量 PHONE_AGENT_BASE_URL 读取）")
    parser.add_argument("--model-api-key", help="模型 API Key（默认: 从环境变量 PHONE_AGENT_API_KEY 读取）")
    parser.add_argument("--model-name", help="模型名称（默认: 从环境变量 PHONE_AGENT_MODEL 读取）")
    parser.add_argument("--adbkey", help="本地 ADB 密钥文件路径（本地文件系统路径，如 ~/.android/adbkey），将复制到 sandbox 的 ~/.android/adbkey")
    parser.add_argument("--skip-devices", action="store_true", help="跳过设备连接")
    parser.add_argument("--skip-model", action="store_true", help="跳过模型配置")
    parser.add_argument("--skip-start", action="store_true", help="跳过启动 MCP 服务器")
    parser.add_argument("--foreground", action="store_true", help="前台运行 MCP 服务器（不后台运行）")
    
    args = parser.parse_args()
    
    if not args.skip_model:
        api_base = args.model_api_base or os.getenv("PHONE_AGENT_BASE_URL")
        api_key = args.model_api_key or os.getenv("PHONE_AGENT_API_KEY") or os.getenv("ZHIPU_API_KEY")
        model_name = args.model_name or os.getenv("PHONE_AGENT_MODEL")
        
        if not all([api_base, api_key, model_name]):
            print("错误: 请设置模型配置（命令行参数或环境变量）")
            sys.exit(1)
        
        if not args.model_provider:
            args.model_provider = "zhipu" if "bigmodel.cn" in api_base or "zhipu" in api_base.lower() else "openai" if "openai.com" in api_base else "local"
        
        args.model_api_base, args.model_api_key, args.model_name = api_base, api_key, model_name
    
    print("=" * 60)
    print("OrderWise MCP 模式 - Sandbox 配置")
    print("=" * 60)
    print(f"Sandbox ID: {args.sandbox_id}")
    
    print("\n连接到 Sandbox...")
    sandbox = Sandbox.connect(sandbox_id=args.sandbox_id)
    print("连接成功")
    
    if hasattr(sandbox, 'get_host'):
        print(f"   MCP 服务: http://{sandbox.get_host(8703)}")
    
    if not args.skip_devices:
        if args.devices:
            connect_devices(sandbox, args.devices, adbkey_path=args.adbkey)
            configure_device_mapping(sandbox, args.devices)
        else:
            print("未提供设备 IP，跳过设备配置（使用 --devices 指定）")
    
    if not args.skip_model:
        configure_model_service(sandbox, args.model_provider, args.model_api_base, args.model_api_key, args.model_name)
    
    if not args.skip_start:
        start_mcp_server(sandbox, background=not args.foreground)
        verify_service(sandbox)
    
    print("\n" + "=" * 60)
    print("配置完成!")
    print("=" * 60)
    if hasattr(sandbox, 'get_host'):
        print(f"\nMCP 服务地址: http://{sandbox.get_host(8703)}")
    print("查看日志: python view_logs.py", args.sandbox_id)


if __name__ == "__main__":
    main()

