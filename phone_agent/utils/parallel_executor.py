"""Parallel execution on multiple devices."""

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from phone_agent import PhoneAgent
from phone_agent.adb.screenshot import get_screenshot
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig
from phone_agent.utils.orderwise_logger import debug, info, warning, error

# App name to app type mapping
_APP_TYPE_MAP = {
    "美团": "mt",
    "京东外卖": "jd",
    "淘宝闪购": "tb",
}


def _format_app_prefix(app_name: Optional[str]) -> str:
    """Format app name prefix for logging."""
    return f"[{app_name}] " if app_name else ""


def _get_session_manager():
    """Get session manager (lazy import to avoid circular dependency)."""
    from mcp_mode.mcp_server.session_manager import get_session_manager
    return get_session_manager()


def _delete_session(session_id: str) -> None:
    """Delete session (lazy import to avoid circular dependency)."""
    _get_session_manager().delete(session_id)


class TakeoverInterrupt(Exception):
    """Exception raised when takeover is triggered in sync mode (MCP mode)."""
    def __init__(self, task_id: str, app_type: str, user_id: Union[str, int], message: str):
        self.task_id = task_id
        self.app_type = app_type
        self.user_id = user_id
        self.message = message
        super().__init__(message)


@dataclass
class ParallelTask:
    """Task configuration for parallel execution."""
    device_id: str
    task: str
    app_name: Optional[str] = None
    app_package: Optional[str] = None


@dataclass
class ParallelResult:
    """Result of parallel task execution."""
    device_id: str
    task: str
    app_name: Optional[str]
    result: str
    duration: float
    success: bool
    error: Optional[str] = None
    session_id: Optional[str] = None  # Session ID for continuing interrupted tasks (MCP sync mode)
    stop_reason: Optional[str] = None  # Stop reason: "INFO_ACTION_NEEDS_REPLY" for takeover


def _create_takeover_callbacks(
    mongodb_writer: Optional[Any],
    task_id: str,
    user_id: Union[str, int],
    keyword: str,
    app_type: str,
    device_id: Optional[str] = None,
    sync_mode: bool = False,
    session_id: Optional[str] = None,  # Pre-generated session_id for sync mode
) -> tuple[Callable[[str], None], Callable[[], None]]:
    """
    Create takeover callback and check callback for manual takeover.
    
    Args:
        mongodb_writer: MongoDBWriter instance (None for sync mode)
        task_id: Task ID
        user_id: User ID
        keyword: Keyword
        app_type: App type
        device_id: Device ID
        sync_mode: If True, use sync mode (MCP mode, immediate return). If False, use async mode (MongoDB polling).
    
    Returns:
        Tuple of (takeover_callback, takeover_check_callback)
    """
    if sync_mode:
        if not session_id:
            session_id = f"{task_id}_{app_type}_{user_id}_{uuid.uuid4().hex[:8]}"
        
        def takeover_callback(message: str) -> None:
            """Sync mode takeover callback: raise exception to notify worker process."""
            info(f"[Takeover同步模式] {app_type}: {message}，触发TakeoverInterrupt...")
            raise TakeoverInterrupt(
                task_id=task_id,
                app_type=app_type,
                user_id=user_id,
                message=message
            )
        
        def takeover_check_callback() -> bool:
            """Sync mode check callback: always return False."""
            return False
        
        return takeover_callback, takeover_check_callback
    
    if mongodb_writer is None:
        raise ValueError("mongodb_writer is required for async mode")
    
    def takeover_callback(message: str) -> None:
        """Async mode takeover callback: write to MongoDB and wait for frontend."""
        info(f"[Takeover异步模式] {app_type}: {message}")
        if mongodb_writer.write_takeover(task_id, user_id, keyword, app_type):
            mongodb_writer.wait_for_takeover_exit(
                task_id, app_type, user_id,
                f"{message}\n[Takeover] 等待前端写入 takeover_exit..."
            )
        else:
            warning(f"[Takeover异步模式] write_takeover 失败，跳过等待")
    
    def takeover_check_callback() -> bool:
        """Async mode check callback: check MongoDB for takeover exit."""
        return mongodb_writer.wait_for_takeover_exit(task_id, app_type, user_id)
    
    return takeover_callback, takeover_check_callback


def _launch_app(device_id: str, app_package: str) -> None:
    """Launch app on device."""
    adb_cmd = ["adb"]
    if device_id:
        adb_cmd.extend(["-s", device_id])
    
    if app_package == "com.taobao.shangou":
        subprocess.run(
            adb_cmd + ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "https://m.tb.cn/h.7R6B3Yc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3.0)
    else:
        subprocess.run(
            adb_cmd + ["shell", "monkey", "-p", app_package, "-c", "android.intent.category.LAUNCHER", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3.8 if "jd" in app_package.lower() or "jingdong" in app_package.lower() else 2.3)


# Global thread pool executor for async MongoDB writes
_mongodb_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="mongodb-writer")


def _write_result_to_mongodb(
    result: str,
    app_name: Optional[str],
    keyword: str,
    task_id: Optional[str],
    user_id: Optional[Union[str, int]],
    mongodb_connection_string: str,
    device_id: Optional[str] = None,
) -> None:
    """Write task result to MongoDB asynchronously (non-blocking)."""
    def _write_with_error_handling():
        try:
            from phone_agent.utils.mongodb_writer import MongoDBWriter
            from phone_agent.utils.price_extractor import extract_price_from_message, detect_minimum_price
            
            mongodb_writer = MongoDBWriter(mongodb_connection_string)
            if not mongodb_writer.is_connected():
                mongodb_writer.close()
                return
            
            # Use default values if not provided (same as MobileAgent-v3)
            final_task_id = task_id
            if not final_task_id:
                timestamp = int(time.time() * 1000)
                final_task_id = f"task_{timestamp}_{hashlib.md5(keyword.encode()).hexdigest()[:8]}"
                debug(f"[MongoDB] 未找到taskId，使用默认值: {final_task_id}")
            
            final_user_id = user_id
            if not final_user_id:
                final_user_id = "default_user"
                debug(f"[MongoDB] 未找到userId，使用默认值: {final_user_id}")
            
            price_info = extract_price_from_message(result, app_name)
            minimum_price = detect_minimum_price(result)
            app_type = _APP_TYPE_MAP.get(app_name, "unknown")
            
            if not price_info and result:
                price_keywords = ["订单总价", "总价", "合计", "应付总额", "总计", "运费", "打包费"]
                found_keywords = [kw for kw in price_keywords if kw in result]
                debug(f"[MongoDB] 价格提取失败: message长度={len(result)}, 前200字符={result[:200]}, 关键词={found_keywords}")
            
            if price_info:
                product = keyword or "未知商品"
                product_patterns = [
                    r"商品[：:]\s*([^\n，,。¥]+)",
                    r"商品名称[：:]\s*([^\n，,。¥]+)",
                ]
                for pattern in product_patterns:
                    match = re.search(pattern, result)
                    if match:
                        extracted_product = match.group(1).strip()
                        if "的" in extracted_product:
                            product_parts = extracted_product.split("的", 1)
                            if len(product_parts) > 1:
                                extracted_product = product_parts[1].strip()
                        # Clean product name: remove price, quantity, and dashes
                        extracted_product = re.sub(r'¥\d+(?:\.\d+)?|\s*[×xX]\s*\d+|^\s*-\s*|\s*-\s*$', '', extracted_product).strip()
                        if extracted_product:
                            product = extracted_product
                            break
                
                seller = None
                seller_patterns = [
                    r"(?:商家|店铺)[：:]\s*([^，,。\n]+?)(?=[，,。\n]|$)",
                    r"([^，,。\n]+?\([^)]+店\))(?:[：:]|$)",
                ]
                invalid_phrases = ["任务已完成", "已经成功", "为您下单", "订单详情", "用户搜索时候的品牌名", "未知商家", "XXX", "xxx", "Xxx"]
                
                for pattern in seller_patterns:
                    seller_match = re.search(pattern, result)
                    if seller_match:
                        candidate = seller_match.group(1).strip()
                        candidate = re.sub(r'^(我可以看到|店铺名称|找到|店铺|商家名称|[-*]\s*)\s*', '', candidate, flags=re.IGNORECASE).strip()
                        if (candidate and len(candidate) >= 2 and len(candidate) <= 50 and 
                            not any(phrase in candidate for phrase in invalid_phrases) and
                            candidate not in ["XXX", "xxx", "Xxx", "未知", "未知商家"]):
                            seller = candidate
                            break
                
                if not seller and keyword:
                    _, extracted_seller = extract_product_and_seller(keyword)
                    if extracted_seller:
                        seller = extracted_seller
                
                mongodb_writer.write_search_result(
                    task_id=final_task_id,
                    user_id=final_user_id,
                    keyword=keyword,
                    product=product,
                    seller=seller,
                    app_type=app_type,
                    price=price_info['price'],
                    delivery_fee=price_info['delivery_fee'],
                    total_fee=price_info['total_fee'],
                    pack_fee=price_info['pack_fee'],
                    minimum_price=minimum_price,
                )
            else:
                mongodb_writer.write_search_fail(
                    task_id=final_task_id,
                    user_id=final_user_id,
                    keyword=keyword,
                    app_type=app_type,
                    reason="无法提取价格信息",
                )
            
            mongodb_writer.close()
        except Exception as e:
            error(f"{_format_app_prefix(app_name)}[MongoDB] 异步写入失败: {e}")
    
    _mongodb_executor.submit(_write_with_error_handling)


def _run_single_task_worker(
    device_id: str,
    task: str,
    app_name: Optional[str],
    app_package: Optional[str],
    model_base_url: str,
    model_name: str,
    model_api_key: str,
    model_lang: str,
    max_steps: int,
    verbose: bool,
    lang: str,
    enable_screenshot_cache: bool,
    screenshot_cache_max_age: float,
    result_queue: Queue,
    task_id: Optional[str] = None,
    user_id: Optional[Union[str, int]] = None,
    keyword: Optional[str] = None,
    mongodb_connection_string: Optional[str] = None,
    device_manager: Optional[Any] = None,
) -> None:
    """Worker function to run a single task on a device."""
    from phone_agent.adb import ADBConnection
    start_time = time.time()

    device_connected_by_worker = False
    conn = None

    def _put_connection_error(msg: str):
        result_queue.put(ParallelResult(
            device_id=device_id,
            task=task,
            app_name=app_name,
            result=None,
            duration=time.time() - start_time,
            success=False,
            error=f"Device connection failed: {msg}",
        ))

    try:
        if device_manager:
            device_info = device_manager.conn.get_device_info(device_id)
            if device_info and device_info.status == "unauthorized":
                warning(f"{_format_app_prefix(app_name)}[设备] 设备未授权，重新连接: {device_id}")
                device_manager.conn.disconnect(device_id)
                time.sleep(1)

            results = device_manager.connect_devices(device_ids=[device_id])
            if not results.get(device_id):
                error(f"{_format_app_prefix(app_name)}[设备] 连接失败: {device_id}")
                _put_connection_error(device_id)
                return
            device_connected_by_worker = True
        else:
            conn = ADBConnection()
            device_info = conn.get_device_info(device_id)

            if device_info and device_info.status == "unauthorized":
                warning(f"{_format_app_prefix(app_name)}[设备] 设备未授权，重新连接: {device_id}")
                conn.disconnect(device_id)
                time.sleep(1)

            if not device_info or device_info.status != "device":
                success, msg = conn.connect(device_id, timeout=5)
                if not success:
                    error(f"{_format_app_prefix(app_name)}[设备] 连接失败: {device_id}, {msg}")
                    _put_connection_error(msg)
                    return
                device_connected_by_worker = True

        if app_package:
            _launch_app(device_id, app_package)
    except Exception as e:
        error(f"{_format_app_prefix(app_name)}[设备连接错误] {str(e)}")
        _put_connection_error(str(e))
        return
    
    model_config = ModelConfig(
        base_url=model_base_url,
        model_name=model_name,
        api_key=model_api_key,
        lang=model_lang,
    )
    agent_config = AgentConfig(
        max_steps=max_steps,
        device_id=device_id,
        verbose=verbose,
        lang=lang,
        enable_screenshot_cache=enable_screenshot_cache,
        screenshot_cache_max_age=screenshot_cache_max_age,
        app_name=app_name,
    )
    
    # Determine mode: sync (MCP) if mongodb_connection_string is None/empty, async (Listener) otherwise
    sync_mode = not mongodb_connection_string
    
    # Setup takeover callbacks based on mode
    takeover_callback = None
    takeover_check_callback = None
    session_id_for_takeover = None
    stop_reason = None
    app_type = _APP_TYPE_MAP.get(app_name, "unknown")
    
    required_params = {"keyword": keyword, "task_id": task_id, "user_id": user_id}
    if not sync_mode:
        required_params["mongodb_connection_string"] = mongodb_connection_string
    
    missing_params = [name for name, value in required_params.items() if not value]
    
    if missing_params:
        mode_name = "同步模式" if sync_mode else "异步模式"
        warning(f"[警告] {app_name}: {mode_name} takeover功能不可用，缺少参数: {', '.join(missing_params)}")
    
    if sync_mode and not missing_params:
        session_id_for_takeover = f"{task_id}_{app_type}_{user_id}_{uuid.uuid4().hex[:8]}"
        
        from mcp_mode.mcp_server.session_manager import get_session_manager, TaskState
        
        session_manager = get_session_manager()
        state = TaskState(
            device_id=device_id,
            app_name=app_name or "unknown",
            task=task,
            model_config={
                "base_url": model_base_url,
                "model_name": model_name,
                "api_key": model_api_key,
                "lang": model_lang,
            },
            agent_config={
                "max_steps": max_steps,
                "device_id": device_id,
                "verbose": verbose,
                "lang": lang,
                "enable_screenshot_cache": enable_screenshot_cache,
                "screenshot_cache_max_age": screenshot_cache_max_age,
                "app_name": app_name,
            },
            keyword=keyword or task,
            task_id=task_id or "unknown",
            user_id=str(user_id) if user_id else "unknown",
            app_package=app_package,
        )
        session_manager.save(session_id_for_takeover, state)
        debug(f"[Takeover同步模式] {app_name}: 已保存任务状态，session_id={session_id_for_takeover}")
        
        takeover_callback, takeover_check_callback = _create_takeover_callbacks(
            mongodb_writer=None,
            task_id=task_id,
            user_id=user_id,
            keyword=keyword,
            app_type=app_type,
            device_id=device_id,
            sync_mode=True,
            session_id=session_id_for_takeover,
        )
        agent_config.takeover_check_callback = takeover_check_callback
    elif not missing_params:
        from phone_agent.utils.mongodb_writer import MongoDBWriter
        
        mongodb_writer = MongoDBWriter(mongodb_connection_string)
        if mongodb_writer.is_connected():
            takeover_callback, takeover_check_callback = _create_takeover_callbacks(
                mongodb_writer=mongodb_writer,
                task_id=task_id,
                user_id=user_id,
                keyword=keyword,
                app_type=app_type,
                device_id=device_id,
                sync_mode=False,
            )
            agent_config.takeover_check_callback = takeover_check_callback
        else:
            warning(f"[警告] MongoDB未连接，takeover功能不可用: {app_name}")
    
    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
        takeover_callback=takeover_callback,
    )
    
    try:
        result = agent.run(task)
        duration = time.time() - start_time
        
        debug(f"{_format_app_prefix(app_name)}[任务完成] agent.run() 返回: {result[:100] if result else 'None'}")
        
        if mongodb_connection_string and keyword:
            _write_result_to_mongodb(
                result, app_name, keyword, task_id, user_id, mongodb_connection_string, device_id
            )
        
        app_prefix = _format_app_prefix(app_name)
        debug(f"{app_prefix}[任务完成] 准备放入结果队列...")
        result_queue.put(ParallelResult(
            device_id=device_id,
            task=task,
            app_name=app_name,
            result=result,
            duration=duration,
            success=True,
        ))
        debug(f"{app_prefix}[任务完成] 已放入结果队列")
        
        # Clean up session if task completed successfully
        if session_id_for_takeover:
            _delete_session(session_id_for_takeover)
    except TakeoverInterrupt as e:
        duration = time.time() - start_time
        session_id = session_id_for_takeover
        
        info(f"[Takeover同步模式] {app_name}: 捕获到TakeoverInterrupt，会话ID={session_id}")
        
        result_queue.put(ParallelResult(
            device_id=device_id,
            task=task,
            app_name=app_name,
            result=e.message,
            duration=duration,
            success=False,
            error="Takeover required",
            session_id=session_id,
            stop_reason="INFO_ACTION_NEEDS_REPLY",
        ))
        
        session_manager = _get_session_manager()
        
        info(f"[Takeover同步模式] {app_name}: 等待用户输入（session_id={session_id}）...")
        reply = session_manager.wait_for_reply(session_id, timeout=None)
        
        if not reply:
            warning(f"[Takeover同步模式] {app_name}: 未收到用户输入，任务终止")
            result_queue.put(ParallelResult(
                device_id=device_id,
                task=task,
                app_name=app_name,
                result=None,
                duration=time.time() - start_time,
                success=False,
                error="Takeover timeout: no user reply",
            ))
            return
        
        info(f"[Takeover同步模式] {app_name}: 收到用户输入: {reply}，继续执行任务")
        modified_task = f"用户已完成操作（{reply}），继续执行原任务：{task}"
        
        result = agent.run(modified_task)
        duration = time.time() - start_time
        
        if mongodb_connection_string and keyword:
            _write_result_to_mongodb(
                result, app_name, keyword, task_id, user_id, mongodb_connection_string, device_id
            )
        
        result_queue.put(ParallelResult(
            device_id=device_id,
            task=task,
            app_name=app_name,
            result=result,
            duration=duration,
            success=True,
        ))
        
        session_manager.delete(session_id)
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        error(f"{_format_app_prefix(app_name)}[错误] 任务执行失败: {error_msg}")
        
        result_queue.put(ParallelResult(
            device_id=device_id,
            task=task,
            app_name=app_name,
            result=None,
            duration=duration,
            success=False,
            error=error_msg,
        ))
        
        if session_id_for_takeover:
            _delete_session(session_id_for_takeover)
    finally:
        if device_connected_by_worker:
            if device_manager:
                device_manager.conn.disconnect(device_id)
            elif conn:
                conn.disconnect(device_id)


def run_parallel_tasks(
    tasks: List[ParallelTask],
    model_config: ModelConfig,
    agent_config: AgentConfig,
    task_id: Optional[str] = None,
    user_id: Optional[Union[str, int]] = None,
    keyword: Optional[str] = None,
    mongodb_connection_string: Optional[str] = None,
    device_manager: Optional[Any] = None,
) -> List[ParallelResult]:
    """Run tasks in parallel on multiple devices."""
    if not tasks:
        return []
    
    device_locks_acquired = []
    if device_manager:
        device_ids = list(set(task.device_id for task in tasks))
        failed_devices = set()
        for device_id in device_ids:
            if device_manager.acquire_device(device_id):
                device_locks_acquired.append(device_id)
            else:
                warning(f"[警告] 无法获取设备锁: {device_id}，跳过该设备的所有任务")
                failed_devices.add(device_id)
        
        if failed_devices:
            tasks = [t for t in tasks if t.device_id not in failed_devices]
            if not tasks:
                # Release acquired locks before returning
                for device_id in device_locks_acquired:
                    device_manager.release_device(device_id)
                return []
    
    result_queue = Queue()
    processes = []
    
    try:
        for task in tasks:
            p = Process(
                target=_run_single_task_worker,
                args=(
                    task.device_id,
                    task.task,
                    task.app_name,
                    task.app_package,
                    model_config.base_url,
                    model_config.model_name,
                    model_config.api_key,
                    model_config.lang,
                    agent_config.max_steps,
                    agent_config.verbose,
                    agent_config.lang,
                    agent_config.enable_screenshot_cache,
                    agent_config.screenshot_cache_max_age,
                    result_queue,
                    task_id,
                    user_id,
                    keyword,
                    mongodb_connection_string,
                    device_manager,
                ),
            )
            processes.append(p)
            p.start()
            info(f"启动设备 {task.device_id} 运行任务: {task.task[:50]}...")
        
        results = []
        
        info(f"[MCP] 等待 {len(tasks)} 个任务完成...")
        start_wait_time = time.time()
        while len(results) < len(tasks):
            elapsed = time.time() - start_wait_time
            debug(f"[MCP] 等待结果... (已收到 {len(results)}/{len(tasks)}, 已等待 {elapsed:.1f}秒)")
            result = result_queue.get()
            debug(f"[MCP] 收到结果: {result.app_name}, success={result.success}, error={result.error if hasattr(result, 'error') else 'None'}")
            results.append(result)
            
            if result.stop_reason == "INFO_ACTION_NEEDS_REPLY":
                info(f"[MCP] 检测到 takeover（{result.app_name}），立即返回结果（不等待其他进程完成）")
                while len(results) < len(tasks):
                    try:
                        result = result_queue.get(timeout=0.1)
                        results.append(result)
                        debug(f"[MCP] 收到额外结果: {result.app_name}")
                    except:
                        break
                break
        
        # Only wait for processes if no takeover was detected
        takeover_detected = any(r.stop_reason == "INFO_ACTION_NEEDS_REPLY" for r in results)
        if not takeover_detected:
            for p in processes:
                p.join()
        success_results = [r for r in results if r.success]
        max_duration = max(r.duration for r in success_results) if success_results else 0
        
        info(f"\n{'='*60}")
        info("所有任务完成！")
        for r in results:
            if r.success:
                info(f"  {r.app_name or '任务'} (设备: {r.device_id}): {r.duration:.2f}秒")
            else:
                error(f"  {r.app_name or '任务'} (设备: {r.device_id}): 失败 - {r.error}")
        if success_results:
            info(f"  总耗时（并行）: {max_duration:.2f}秒")
        info(f"{'='*60}\n")
        
        return results
    finally:
        # Release device locks after processes complete
        if device_manager:
            for device_id in device_locks_acquired:
                device_manager.release_device(device_id)


def _load_json_config(config_path: Optional[str]) -> Any:
    if config_path and Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_devices_config(config_path: Optional[str] = None) -> Dict[str, str]:
    return _load_json_config(config_path) if config_path else {}

def load_apps_config(config_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    if config_path:
        config = _load_json_config(config_path)
        if config:
            return config
    
    return {
        "app1": {
            "package": "com.sankuai.meituan",
            "name": "美团",
            "instruction_template": "1. 已经打开美团app, 点击进入'外卖'页面\n2. 在搜索结果中找到对应品牌/商家的商品并购买\"{product_name}\"（遵循系统规则d)，优先选择不包含数量关键词的商品，数量默认为1，除非用户明确指定）\n3. 价格识别规则（按顺序执行，必须严格遵守）：\n   - 如果进入订单确认页面（看到\"去结算\"等按钮），必须完成以下操作（按顺序执行，不能跳过）：\n     * 第一步：点击使用默认地址（如果未选择）\n     * 第二步（关键）：如果看到\"美团红包\"区域显示\"待使用 X元红包 >\"或\"还有¥X红包可用>\"，必须立即点击该红包区域（点击\"待使用 X元红包 >\"或\"还有¥X红包可用>\"这个可点击的文本区域），进入红包选择页面\n     * 第三步：在红包选择页面，如果有可用的红包（显示\"可用红包\"），必须选择一个红包并点击\"确认\"按钮来使用红包\n     * 第四步：点击确认后，必须等待页面返回订单确认页面，并等待页面价格更新，然后重新查看页面底部的\"合计\"或\"总计\"价格，确保看到的是使用红包后的最终价格（如果价格没有变化，说明红包没有成功使用，需要重新尝试）\n     * 第五步：只有在确认红包已使用且价格已更新后，才能提取价格信息并完成任务\n   - **重要**：在订单确认页面，绝对不要点击\"提交订单\"、\"立即支付\"或任何支付相关的按钮。只需要识别价格信息后立即finish。\n   - 输出格式：商家：XXX，优惠后价格¥X.X，打包费¥X.X，配送费¥X.X，合计¥XX.X（严格按照系统规则h)的格式要求）"
        },
        "app2": {
            "package": "com.jd.waimai",
            "name": "京东外卖",
            "instruction_template": "1. 已经打开京东外卖app\n2. 在搜索结果中按照系统规则11进行搜索：当前任务要搜索的关键词是\"{product_name}\"，绝对不要点击任何搜索历史记录或推荐关键词（包括\"瑞幸咖啡\"等历史项），必须只在搜索框中输入\"{product_name}\"进行搜索。\n3. 在搜索结果中找到对应品牌/商家的商品并加入购物车（遵循系统规则d)，优先选择不包含数量关键词的商品，数量默认为1，除非用户明确指定）\n4. 点击\"去结算\"或\"领券结算\"进入结算页面\n5. 价格识别规则（按顺序执行，必须严格遵守）：\n   - 在结算页面（看到\"立即支付\"按钮）识别价格信息\n   - **绝对禁止**：在结算页面/订单确认页面，绝对不要点击\"立即支付\"、\"提交订单\"或任何支付相关的按钮。只需要识别价格信息后立即finish。\n   - 输出格式：商家：XXX，优惠后价格¥X.X，打包费¥X.X，运费¥X.X，应付总额¥XX.X（严格按照系统规则h)的格式要求）"
        },
        "app3": {
            "package": "com.taobao.shangou",
            "name": "淘宝闪购",
            "instruction_template": "**严格限制**：禁止使用浏览器地址栏、打开新标签页或导航到其他网站，只能在淘宝闪购页面内操作。\n1. 已经打开淘宝闪购网页版 - 如果出现\"无法获取定位\"的对话框，点击选择地址按钮; 然后点击收货地址下面的第一条地址\n2. 在搜索结果中找到对应品牌/商家的商品并加入购物车（遵循系统规则d)，优先选择不包含数量关键词的商品，数量默认为1，除非用户明确指定）\n3. 点击\"去结算\"进入结算页面\n4. 价格识别规则（重要）：\n   - 在结算页面（看到\"提交订单\"或\"立即支付\"按钮）识别价格信息\n   - **重要**：绝对不要点击\"提交订单\"、\"立即支付\"或任何支付相关的按钮。只需要识别价格信息后立即finish。\n   - 输出格式：商家：XXX，商品单价¥XX.X，打包费¥X.X，配送费¥X.X，合计¥XX.X（严格按照系统规则h)的格式要求）"
        }
    }


def extract_product_and_seller(task: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract product name and seller name from user task description.
    
    Examples:
        "星巴克抹茶拿铁" -> ("抹茶拿铁", "星巴克")
        "抹茶拿铁" -> ("抹茶拿铁", None)
        "打开美团购买附近瑞幸的疯狂红茶拿铁" -> ("疯狂红茶拿铁", "瑞幸")
    
    Args:
        task: User task description.
    
    Returns:
        Tuple of (product_name, seller_name). Either can be None.
    """
    if not task:
        return None, None
    
    # 常见商家名称列表（按长度从长到短排序，优先匹配长名称）
    common_sellers = [
        "星巴克", "瑞幸", "霸王茶姬", "喜茶", "奈雪的茶", "lavazza", "库迪", "tims",
        "一点点", "CoCo都可", "蜜雪冰城", "茶百道", "书亦烧仙草",
        "麦当劳", "肯德基", "汉堡王", "必胜客", "达美乐",
        "海底捞", "呷哺呷哺", "小龙坎", "大龙燚",
    ]
    
    # 尝试匹配商家名称（从长到短）
    seller_name = None
    product_name = task
    
    for seller in sorted(common_sellers, key=len, reverse=True):
        # 匹配模式：商家名 + 商品名 或 商品名 + 商家名
        patterns = [
            (rf"^{re.escape(seller)}(.+)$", 1),  # 商家名开头，后面是商品
            (rf"^(.+){re.escape(seller)}$", 1),  # 商家名结尾，前面是商品
            (rf".*{re.escape(seller)}(.+)$", 1),  # 商家名在中间，后面是商品
            (rf"^(.+){re.escape(seller)}.*$", 1),  # 商家名在中间，前面是商品
        ]
        
        for pattern, group_idx in patterns:
            match = re.search(pattern, task)
            if match:
                seller_name = seller
                product_part = match.group(group_idx).strip() if match.groups() else task.replace(seller, "").strip()
                product_part = re.sub(r"^(打开|购买|点|要|来|一杯|一份|一个)\s*", "", product_part, flags=re.IGNORECASE)
                product_part = re.sub(r"\s*(的|附近|购买|点|要|来|一杯|一份|一个)$", "", product_part, flags=re.IGNORECASE)
                product_part = product_part.replace("的", "").strip()
                if seller in product_part:
                    product_part = product_part.replace(seller, "").strip()
                if product_part and len(product_part) >= 2:
                    product_name = product_part
                elif not product_part:
                    product_name = task.replace(seller, "").strip()
                    product_name = re.sub(r"^(打开|购买|点|要|来)\s*", "", product_name, flags=re.IGNORECASE)
                break
        
        if seller_name:
            break
    
    if not seller_name:
        nearby_pattern = r"附近(.+?)的"
        match = re.search(nearby_pattern, task)
        if match:
            potential_seller = match.group(1).strip()
            for seller in common_sellers:
                if seller in potential_seller or potential_seller in seller:
                    seller_name = seller
                    product_name = re.sub(nearby_pattern, "", task).strip()
                    product_name = re.sub(r"^(打开|购买|点|要|来)\s*", "", product_name, flags=re.IGNORECASE)
                    product_name = product_name.replace("的", "").strip()
                    break
    
    if product_name:
        product_name = re.sub(r"^(打开|购买|点|要|来|一杯|一份|一个)\s*", "", product_name, flags=re.IGNORECASE)
        product_name = product_name.strip()
        if not product_name:
            product_name = None
    
    if not seller_name and product_name:
        pattern1 = r'^([a-zA-Z][a-zA-Z0-9]{1,})([\u4e00-\u9fa5]+.*)$'
        match = re.match(pattern1, product_name)
        if match:
            english_part = match.group(1)
            chinese_part = match.group(2)
            if len(english_part) >= 2:
                product_name = f"{english_part} {chinese_part}"
        elif ' ' not in product_name:
            common_product_prefixes = ['抹茶', '奶茶', '咖啡', '拿铁', '美式', '卡布', '摩卡', '拿', '茶', '奶']
            pattern2 = r'^([\u4e00-\u9fa5]{2,4})([\u4e00-\u9fa5]{2,}.*)$'
            match = re.match(pattern2, product_name)
            if match:
                potential_seller = match.group(1)
                potential_product = match.group(2)
                if (len(potential_seller) >= 2 and len(potential_product) >= 2 and 
                    not any(potential_seller.startswith(prefix) for prefix in common_product_prefixes)):
                    product_name = f"{potential_seller} {potential_product}"
    
    return product_name, seller_name


def build_tasks_from_configs(
    apps_config: Dict[str, Dict[str, Any]],
    task_template: Optional[str] = None,
    product_name: Optional[str] = None,
    seller_name: Optional[str] = None,
    app_to_device_mapping: Optional[Dict[str, str]] = None,
    **task_kwargs,
) -> List[ParallelTask]:
    """Build parallel tasks from configuration files.
    
    Args:
        apps_config: App configuration mapping with instruction templates.
        task_template: Optional task template string (legacy support).
        product_name: Product name for instruction template.
        seller_name: Seller name for instruction template.
        app_to_device_mapping: Mapping from app_type (jd/tb/mt) to device_id from MongoDB.
        **task_kwargs: Additional keyword arguments for task template.
    
    Returns:
        List of ParallelTask objects.
    """
    tasks = []
    
    # Build tasks in order: jd -> tb -> mt
    app_order = ["app2", "app3", "app1"]  # jd, tb, mt
    
    for app_key in app_order:
        if app_key not in apps_config:
            continue
        
        app_info = apps_config[app_key]
        app_name = app_info.get('name', app_key)
        app_type = _APP_TYPE_MAP.get(app_name)
        
        # Get device_id from MongoDB mapping
        device_id = None
        if app_to_device_mapping and app_type and app_type in app_to_device_mapping:
            device_id = app_to_device_mapping[app_type]
            debug(f"[调试] {app_name} ({app_type}): 使用 MongoDB device={device_id}")
        
        if not device_id:
            warning(f"[警告] {app_name} ({app_type}): 未找到 device_id，跳过此应用")
            continue
        
        app_package = app_info.get('package')
        task = None
        
        if product_name:
            instruction_template = app_info.get('instruction_template')
            if instruction_template:
                needs_seller = '{seller_name}' in instruction_template
                if needs_seller and not seller_name:
                    template = app_info.get('instruction_template_no_seller') or instruction_template
                else:
                    template = instruction_template
                
                if template:
                    task = template.format(
                        product_name=product_name,
                        seller_name=seller_name or ''
                    )
                    if seller_name and '{seller_name}' not in template:
                        task = f"注意：品牌/商家名称是\"{seller_name}\"，商品名称是\"{product_name}\"。{task}"
                    elif not seller_name:
                        task = f"当前任务：搜索并购买\"{product_name}\"。{task}"
        
        if not task:
            task = task_template.format(**task_kwargs) if task_template else (f"在{app_name}中完成任务" if app_name else "完成任务")
        
        if app_name:
            task = f"[App: {app_name}]\n{task}"
        
        tasks.append(ParallelTask(
            device_id=device_id,
            task=task,
            app_name=app_name,
            app_package=app_package,
        ))
    
    return tasks