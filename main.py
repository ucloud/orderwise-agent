#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS]

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Union

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.adb import ADBConnection, list_devices
from phone_agent.agent import AgentConfig
from phone_agent.config.apps import list_supported_apps
from phone_agent.model import ModelConfig
from phone_agent.utils.parallel_executor import (
    build_tasks_from_configs,
    extract_product_and_seller,
    load_apps_config,
    run_parallel_tasks,
    ParallelTask,
    _APP_TYPE_MAP,
)
from phone_agent.utils.mongodb_writer import MongoDBWriter
from phone_agent.utils.device_manager import DeviceManager
from phone_agent.utils.orderwise_logger import debug, info, warning, error, set_verbose, set_quiet
from bson.regex import Regex
from pymongo import MongoClient


def check_system_requirements(device_ids: Optional[List[str]] = None) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device(s)

    Args:
        device_ids: Optional list of device IDs to check. If None, checks default device.

    Returns:
        True if all checks pass, False otherwise.
    """
    print("Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Check 1: ADB installed
    print("1. Checking ADB installation...", end=" ")
    if shutil.which("adb") is None:
        print("FAILED")
        print("   Error: ADB is not installed or not in PATH.")
        print("   Solution: Install Android SDK Platform Tools:")
        print("     - macOS: brew install android-platform-tools")
        print("     - Linux: sudo apt install android-tools-adb")
        print("     - Windows: Download from https://developer.android.com/studio/releases/platform-tools")
        all_passed = False
    else:
        result = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.strip().split("\n")[0]
            print(f"OK ({version_line})")
        else:
            print("FAILED")
            print("   Error: ADB command failed to run.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    result = subprocess.run(
        ["adb", "devices"], capture_output=True, text=True, timeout=10
    )
    lines = result.stdout.strip().split("\n")
    devices = [line for line in lines[1:] if line.strip() and "\tdevice" in line]

    if not devices:
        print("FAILED")
        print("   Error: No devices connected.")
        print("   Solution:")
        print("     1. Enable USB debugging on your Android device")
        print("     2. Connect via USB and authorize the connection")
        print("     3. Or connect remotely: python main.py --connect <ip>:<port>")
        all_passed = False
    else:
        device_ids_list = [d.split("\t")[0] for d in devices]
        print(f"OK ({len(devices)} device(s): {', '.join(device_ids_list)})")

    # Auto-connect devices from listener_devices if provided
    if device_ids and all_passed:
        missing_devices = [d for d in device_ids if d not in device_ids_list]
        if missing_devices:
            print(f"   自动连接 {len(missing_devices)} 台未连接的设备...")
            from phone_agent.utils.device_manager import DeviceManager
            temp_manager = DeviceManager()
            results = temp_manager.connect_devices(device_ids=missing_devices)
            
            if any(results.values()):
                time.sleep(0.5)  # Brief wait for connections to stabilize
                device_ids_list = [d.device_id for d in list_devices()]
                print(f"   当前已连接 {len(device_ids_list)} 台设备")

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed
    def check_keyboard(device_id: Optional[str] = None) -> bool:
        cmd = ["adb"]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["shell", "ime", "list", "-s"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and "com.android.adbkeyboard/.AdbIME" in result.stdout
    
    # Determine which devices to check
    # If device_ids provided, use them (they should all be connected after auto-connect)
    if device_ids:
        devices_to_check = [d for d in device_ids if d in device_ids_list]
    else:
        devices_to_check = device_ids_list
    
    if devices_to_check:
        print(f"3. Checking ADB Keyboard on {len(devices_to_check)} device(s)...")
        failed_devices = [d for d in devices_to_check if not check_keyboard(d)]
        
        for device_id in devices_to_check:
            status = "OK" if device_id not in failed_devices else "FAILED"
            msg = "OK" if device_id not in failed_devices else "ADB Keyboard not installed"
            print(f"   {status} {device_id}: {msg}")
        
        if failed_devices:
            print("   Error: ADB Keyboard is not installed on some devices.")
            print("   Solution:")
            print("     1. Download ADB Keyboard APK from:")
            print("        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk")
            for device_id in failed_devices:
                print(f"     2. Install on {device_id}: adb -s {device_id} install ADBKeyboard.apk")
            print("     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard")
            all_passed = False
        else:
            print("   All devices OK")
    else:
        print("3. Checking ADB Keyboard...", end=" ")
        if check_keyboard():
            print("OK")
        else:
            print("FAILED")
            print("   Error: ADB Keyboard is not installed on the device.")
            print("   Solution:")
            print("     1. Download ADB Keyboard APK from:")
            print("        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk")
            print("     2. Install it on your device: adb install ADBKeyboard.apk")
            print("     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("All system checks passed!\n")
    else:
        print("System check failed. Please fix the issues above.")

    return all_passed


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    Check if the model API is accessible and the specified model exists.

    Checks:
    1. Network connectivity to the API endpoint
    2. Model exists in the available models list

    Args:
        base_url: The API base URL
        model_name: The model name to check
        api_key: The API key for authentication

    Returns:
        True if all checks pass, False otherwise.
    """
    print("Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("OK")
        else:
            print("FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("FAILED")
        error_msg = str(e)

        # Provide more specific error messages
        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print(f"   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("Model API checks passed!\n")
    else:
        print("Model API check failed. Please fix the issues above.")

    return all_passed


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings
    python main.py

    # Specify model endpoint
    python main.py --base-url http://localhost:8000/v1

    # Use API key for authentication
    python main.py --apikey sk-xxxxx

    # Run with specific device
    python main.py --device-id emulator-5554

    # Connect to remote device
    python main.py --connect 192.168.1.100:5555

    # List connected devices
    python main.py --list-devices

    # Enable TCP/IP on USB device and get connection info
    python main.py --enable-tcpip

    # List supported apps
    python main.py --list-apps
        """,
    )

    # Model options
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="Model API base URL",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        help="Model name",
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
        help="Maximum steps per task",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # Other options
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "cn"),
        help="Language for system prompt (cn or en, default: cn)",
    )

    # Parallel execution options
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution on multiple devices",
    )


    parser.add_argument(
        "--apps-config",
        type=str,
        help="Path to apps configuration JSON file (e.g., apps_config.json)",
    )

    parser.add_argument(
        "--product-name",
        type=str,
        help="Product name for price extraction tasks (used with instruction templates)",
    )

    parser.add_argument(
        "--seller-name",
        type=str,
        help="Seller name for price extraction tasks (used with instruction templates)",
    )

    # MongoDB options
    parser.add_argument(
        "--mongodb-connection",
        type=str,
        help="MongoDB connection string (e.g., mongodb://host:port)",
    )

    parser.add_argument(
        "--task-id",
        type=str,
        help="Task ID for MongoDB records (optional, auto-extracted in listener mode)",
    )

    parser.add_argument(
        "--user-id",
        type=str,
        help="User ID for MongoDB records (optional, auto-extracted in listener mode)",
    )

    parser.add_argument(
        "--mongodb-listener",
        action="store_true",
        help="Enable MongoDB listener mode (listens for new tasks in tasks collection)",
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    return parser.parse_args()


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    conn = ADBConnection()

    # Handle --list-devices
    if args.list_devices:
        devices = list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "OK" if device.status == "device" else "FAILED"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'OK' if success else 'FAILED'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'OK' if success else 'FAILED'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'OK' if success else 'FAILED'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def main():
    """Main entry point."""
    args = parse_args()
    
    # Initialize OrderWise logger verbosity
    set_quiet(args.quiet)
    set_verbose(not args.quiet)

    # Handle --list-apps (no system check needed)
    if args.list_apps:
        print("Supported apps:")
        for app in sorted(list_supported_apps()):
            print(f"  - {app}")
        return

    # Handle device commands (these may need partial system checks)
    if handle_device_commands(args):
        return

    # Initialize device manager for robust device management
    device_manager = None
    if args.mongodb_connection or args.parallel:
        device_manager = DeviceManager(
            mongodb_connection_string=args.mongodb_connection,
            health_check_interval=30,
            max_reconnect_attempts=3,
        )
    
    # Basic system check (use configured devices for listener mode)
    if args.mongodb_listener:
        from phone_agent.config.listener_devices import LISTENER_DEVICES
        if not check_system_requirements(device_ids=LISTENER_DEVICES):
            sys.exit(1)
    elif not check_system_requirements(device_ids=None):
        sys.exit(1)
    
    # Initialize device manager
    if device_manager:
        if args.mongodb_listener:
            device_manager.start_health_monitoring()

    # Create configurations (don't need API check yet)
    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey,
        lang=args.lang,
    )

    agent_config = AgentConfig(
        max_steps=args.max_steps,
        device_id=args.device_id,
        verbose=not args.quiet,
        lang=args.lang,
    )

    # Print header (only for non-listener mode)
    if not args.mongodb_listener:
        print("=" * 50)
        print("Phone Agent - AI-powered phone automation")
        print("=" * 50)
        print(f"Model: {model_config.model_name}")
        print(f"Base URL: {model_config.base_url}")
        print(f"Max Steps: {agent_config.max_steps}")
        print(f"Language: {agent_config.lang}")

        devices = list_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            print(f"Device: {devices[0].device_id} (auto-detected)")

        print("=" * 50)

    # Handle MongoDB listener mode
    if args.mongodb_listener:
        if not args.mongodb_connection:
            print("Error: --mongodb-connection is required for listener mode")
            sys.exit(1)
        if not args.apps_config:
            print("Error: --apps-config is required for listener mode")
            sys.exit(1)
        
        from phone_agent.utils.mongodb_listener import MongoDBListener
        
        apps_config = load_apps_config(args.apps_config)
        
        # 并行执行：Model API 检查、MongoDB 连接
        debug("并行初始化中...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            api_future = executor.submit(check_model_api, args.base_url, args.model, args.apikey)
            mongodb_future = executor.submit(MongoDBListener, args.mongodb_connection)
            
            # 等待 MongoDB 连接
            listener = mongodb_future.result()
            if not listener.is_connected():
                error("Error: 无法连接到MongoDB，退出")
                sys.exit(1)
            
            # 预启动逻辑已关闭（默认关闭）
            
            if not api_future.result():
                sys.exit(1)
        
        info("=" * 60)
        info("MongoDB监听模式")
        info("=" * 60)
        info(f"监听数据库: {args.mongodb_connection}")
        info("监听集合: tasks")
        info("按 Ctrl+C 退出监听")
        info("=" * 60)
        
        # Capture dependencies in closure to avoid scope issues in callback
        # Import with aliases to avoid local variable conflicts
        from phone_agent.utils.parallel_executor import (
            extract_product_and_seller as _extract_product_and_seller,
            build_tasks_from_configs as _build_tasks_from_configs,
            run_parallel_tasks as _run_parallel_tasks,
            _APP_TYPE_MAP as _APP_TYPE_MAP_local,
        )
        
        # Capture runtime variables
        _device_manager = device_manager
        _apps_config = apps_config
        _model_config = model_config
        _agent_config = agent_config
        _mongodb_connection = args.mongodb_connection
        
        # Thread pool for async task execution
        task_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="task-executor")
        
        # Track pre-checked devices to avoid duplicate checks
        prechecked_devices = set()
        precheck_lock = threading.Lock()
        
        def on_new_task(keyword: str, document: dict):
            """Callback for new task from MongoDB - executed asynchronously."""
            task_id = document.get('taskId') or ''
            user_id_raw = document.get('userId') or ''
            # Handle array case: if userId is array, extract first element
            user_id = user_id_raw[0] if isinstance(user_id_raw, list) and user_id_raw else user_id_raw
            
            if not task_id or not user_id:
                warning(f"[警告] 任务文档缺少必要字段: taskId={bool(task_id)}, userId={bool(user_id)}")
                debug(f"[调试] 文档内容: taskId={task_id}, userId={user_id} (type: {type(user_id).__name__})")
                return
            
            info(f"\n{'='*60}")
            info(f"[新任务] keyword={keyword}, taskId={task_id}, userId={user_id}")
            info(f"{'='*60}\n")
            
            # Extract product and seller from keyword
            product_name, seller_name = _extract_product_and_seller(keyword)
            
            # Ensure devices are connected using device manager
            # In MongoDB listener mode, device_manager always exists
            _device_manager.ensure_devices_connected(
                task_id=task_id,
                keyword=keyword,
                user_id=user_id,
            )
            app_to_device = _device_manager.app_to_device
            
            # Pre-check devices on first use (when MongoDB data is available)
            with precheck_lock:
                device_ids_to_check = _device_manager.get_unchecked_devices(
                    list(app_to_device.values()),
                    prechecked_devices
                )
                prechecked_devices.update(device_ids_to_check)
            
            if device_ids_to_check:
                info(f"[设备预检] 首次使用设备，进行预检: {device_ids_to_check}")
                if not check_system_requirements(device_ids=device_ids_to_check):
                    warning(f"[警告] 设备预检失败，但继续执行任务")
            
            debug(f"[调试] 从 MongoDB records 读取到的 device 映射: {app_to_device}")
            
            # 检查任务是否已被标记为完成
            if _mongodb_connection:
                client = MongoClient(_mongodb_connection, serverSelectionTimeoutMS=1000)
                doc = client['waimai-server']['tasks'].find_one(
                    {"taskId": task_id, "userId": user_id},
                    {"operationType": 1}
                )
                client.close()
                if doc and doc.get("operationType") == "search_completed":
                    info(f"[跳过] 任务已完成: keyword={keyword}, taskId={task_id}")
                    return
            
            tasks = _build_tasks_from_configs(
                _apps_config,
                task_template=keyword,
                product_name=product_name,
                seller_name=seller_name,
                app_to_device_mapping=app_to_device if app_to_device else None,
            )
            
            debug(f"[调试] 构建的任务列表:")
            for task in tasks:
                debug(f"  - {task.app_name} (app_type={_APP_TYPE_MAP_local.get(task.app_name, 'unknown')}): device_id={task.device_id}")
            
            if not tasks:
                error("Error: No tasks to execute")
                return
            
            # Execute parallel tasks with device lock support
            results = _run_parallel_tasks(
                tasks=tasks,
                model_config=_model_config,
                agent_config=_agent_config,
                task_id=task_id,
                user_id=user_id,
                keyword=keyword,
                mongodb_connection_string=_mongodb_connection,
                device_manager=_device_manager,
            )
            
            info(f"[任务完成] keyword: {keyword}\n")
        
        def on_new_task_wrapper(keyword: str, document: dict):
            """Wrapper to submit task to thread pool."""
            task_executor.submit(on_new_task, keyword, document)
        
        listener.start_listening(on_new_task_wrapper)
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            info("\n停止监听...")
            listener.stop_listening()
            task_executor.shutdown(wait=True)
            if device_manager:
                device_manager.stop_health_monitoring()
        
        return
    
    # Handle parallel execution
    if args.parallel:
        if not args.task:
            print("Error: Task is required for parallel execution")
            sys.exit(1)
        
        if not args.mongodb_connection:
            print("Error: --mongodb-connection is required for parallel execution")
            sys.exit(1)
        
        apps_config = load_apps_config(args.apps_config) if args.apps_config else {}
        
        # 如果没有显式提供 product_name 和 seller_name，尝试从任务中提取
        product_name = args.product_name
        seller_name = args.seller_name
        
        if not product_name and args.task:
            from phone_agent.utils.parallel_executor import extract_product_and_seller
            extracted_product, extracted_seller = extract_product_and_seller(args.task)
            if extracted_product:
                product_name = extracted_product
            if extracted_seller:
                seller_name = extracted_seller
        
        # Load device mapping from MongoDB if available
        app_to_device = {}
        if device_manager:
            # Note: user_id will be fetched from MongoDB if not provided
            device_manager.ensure_devices_connected(keyword=args.task)
            app_to_device = device_manager.app_to_device
        elif args.mongodb_connection:
            temp_manager = DeviceManager(mongodb_connection_string=args.mongodb_connection)
            # Note: user_id will be fetched from MongoDB if not provided
            temp_manager.ensure_devices_connected(keyword=args.task)
            app_to_device = temp_manager.app_to_device
        if app_to_device:
            debug(f"[MongoDB] 从数据库读取到 {len(app_to_device)} 个 device 映射")
        
        tasks = build_tasks_from_configs(
            apps_config,
            task_template=args.task,
            product_name=product_name,
            seller_name=seller_name,
            app_to_device_mapping=app_to_device if app_to_device else None,
        )
        
        if not tasks:
            error("Error: No tasks to execute")
            sys.exit(1)
        
        info(f"\n并行执行模式：{len(tasks)}个设备")
        info(f"{'='*60}\n")
        
        # Try to get task_id and user_id from MongoDB if not provided
        final_task_id = args.task_id
        final_user_id = args.user_id
        need_fetch_task_info = args.mongodb_connection and not final_task_id and not final_user_id
        
        def fetch_task_info():
            debug(f"[MongoDB] 开始查询任务信息: keyword={args.task}")
            mongodb_writer = MongoDBWriter(args.mongodb_connection)
            if not mongodb_writer.is_connected():
                error(f"[MongoDB] 连接失败")
                mongodb_writer.close()
                return None, None, {}
            
            collection = mongodb_writer.db['tasks']
            doc = collection.find_one({"keyword": args.task}, sort=[("createdAt", -1)])
            if not doc:
                doc = collection.find_one({"keyword": Regex(args.task, "i")}, sort=[("createdAt", -1)])
            
            if not doc:
                warning(f"[MongoDB] 未找到匹配的任务文档 (keyword={args.task})")
                mongodb_writer.close()
                return None, None, {}
            
            task_id = doc.get('taskId') 
            user_id_raw = doc.get('userId')
            user_id = user_id_raw[0] if isinstance(user_id_raw, list) and user_id_raw else user_id_raw
            
            fetched_app_to_device = {}
            temp_manager = device_manager
            if not temp_manager and args.mongodb_connection:
                temp_manager = DeviceManager(mongodb_connection_string=args.mongodb_connection)
            
            if temp_manager:
                temp_manager.ensure_devices_connected(task_id=task_id, keyword=args.task, user_id=user_id)
                fetched_app_to_device = temp_manager.app_to_device
            
            mongodb_writer.close()
            
            debug(f"[MongoDB] 找到文档: taskId={task_id[:8] if task_id else 'None'}..., userId={user_id} (type: {type(user_id).__name__})")
            if fetched_app_to_device:
                debug(f"[MongoDB] 读取到 {len(fetched_app_to_device)} 个 device 映射: {fetched_app_to_device}")
            
            if task_id and user_id:
                info(f"[MongoDB] 从数据库读取: taskId={task_id[:8]}..., userId={user_id}")
                return task_id, user_id, fetched_app_to_device
            warning(f"[MongoDB] 参数不完整: taskId={bool(task_id)}, userId={bool(user_id)}")
            return None, None, fetched_app_to_device
        
        # 并行执行：Model API 检查和 MongoDB 查询（如果需要）
        if apps_config:
            debug("并行初始化中...")
            max_workers = 2 if need_fetch_task_info else 1
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                api_future = executor.submit(check_model_api, args.base_url, args.model, args.apikey)
                task_info_future = executor.submit(fetch_task_info) if need_fetch_task_info else None
                
                if not api_future.result():
                    sys.exit(1)
                
                if task_info_future:
                    fetched_task_id, fetched_user_id, fetched_app_to_device = task_info_future.result()
                    if fetched_task_id and fetched_user_id:
                        final_task_id, final_user_id = fetched_task_id, fetched_user_id
                        info(f"[MongoDB] 使用查询结果: taskId={final_task_id[:8]}..., userId={final_user_id}")
                    else:
                        warning(f"[MongoDB] 查询失败，使用默认值: taskId={final_task_id}, userId={final_user_id}")
                    if fetched_app_to_device:
                        app_to_device.update(fetched_app_to_device)
                        if device_manager:
                            device_manager.app_to_device.update(fetched_app_to_device)
                            device_manager.connect_devices()
                        debug(f"[MongoDB] 合并 device 映射，总计 {len(app_to_device)} 个")
                        tasks = build_tasks_from_configs(
                            apps_config,
                            task_template=args.task,
                            product_name=product_name,
                            seller_name=seller_name,
                            app_to_device_mapping=app_to_device,
                        )
        elif not check_model_api(args.base_url, args.model, args.apikey):
            sys.exit(1)
        elif need_fetch_task_info:
            fetched_task_id, fetched_user_id, fetched_app_to_device = fetch_task_info()
            if fetched_task_id and fetched_user_id:
                final_task_id, final_user_id = fetched_task_id, fetched_user_id
            if fetched_app_to_device:
                app_to_device.update(fetched_app_to_device)
                if device_manager:
                    device_manager.app_to_device.update(fetched_app_to_device)
                    device_manager.connect_devices()
                debug(f"[MongoDB] 合并 device 映射，总计 {len(app_to_device)} 个")
                tasks = build_tasks_from_configs(
                    apps_config,
                    task_template=args.task,
                    product_name=product_name,
                    seller_name=seller_name,
                    app_to_device_mapping=app_to_device,
                )
            if fetched_task_id and fetched_user_id:
                final_task_id, final_user_id = fetched_task_id, fetched_user_id
        
        results = run_parallel_tasks(
            tasks=tasks,
            model_config=model_config,
            agent_config=agent_config,
            task_id=final_task_id,
            user_id=final_user_id,
            keyword=args.task,
            mongodb_connection_string=args.mongodb_connection,
        )
        
        print("\n详细结果:")
        for r in results:
            print(f"\n设备: {r.device_id}")
            print(f"任务: {r.task[:100]}...")
            print(f"{'结果' if r.success else '错误'}: {r.result[:200] if r.success else r.error}...")
        
        return

    # Check model API for non-parallel mode
    if not check_model_api(args.base_url, args.model, args.apikey):
        sys.exit(1)
    
    # Create agent for non-parallel mode
    agent = PhoneAgent(model_config=model_config, agent_config=agent_config)

    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        result = agent.run(args.task)
        print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                result = agent.run(task)
                print(f"\nResult: {result}\n")
                agent.reset()

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
