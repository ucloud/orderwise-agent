"""MongoDB data writer for search results."""

import signal
import time
from datetime import datetime
from typing import Optional, Union
from pymongo import MongoClient
from bson.regex import Regex

# Global flag for interrupt handling (per-process, thread-safe for single-threaded usage)
_interrupt_flag = False
_old_signal_handler = None

def _set_interrupt_flag(signum, frame):
    """Signal handler to set interrupt flag."""
    global _interrupt_flag
    _interrupt_flag = True

def _restore_signal_handler():
    """Restore original signal handler."""
    global _old_signal_handler, _interrupt_flag
    if _old_signal_handler is not None:
        signal.signal(signal.SIGINT, _old_signal_handler)
        _old_signal_handler = None
    _interrupt_flag = False


def get_device_mapping_from_mongodb(
    mongodb_connection_string: str,
    task_id: Optional[str] = None,
    keyword: Optional[str] = None,
    user_id: Optional[Union[str, int]] = None,
    use_latest: bool = False,
) -> dict:
    """
    从 MongoDB 读取 device 映射（统一函数，所有模式复用）。
    
    Args:
        mongodb_connection_string: MongoDB 连接字符串
        task_id: 可选，通过 task_id 查询
        keyword: 可选，通过 keyword 查询
        user_id: 可选，通过 user_id 查询（用于区分不同用户的设备）
        use_latest: 如果为 True，查询最新的有 records 的文档（用于预启动）
    
    Returns:
        dict: app_type -> device_id 的映射，例如 {"jd": "192.168.1.100:5555", ...}
    """
    app_to_device = {}
    
    if not mongodb_connection_string:
        return app_to_device
    
    mongodb_writer = MongoDBWriter(mongodb_connection_string)
    if not mongodb_writer.is_connected():
        mongodb_writer.close()
        return app_to_device
    
    collection = mongodb_writer.db['tasks']
    doc = None
    
    if isinstance(user_id, list):
        user_id = user_id[0] if user_id else None
    
    if use_latest:
        # 查询最新的有 records 且 records 中有 device 字段的文档（用于预启动）
        # 使用 $elemMatch 确保至少有一个 record 有 device 字段
        query = {"records": {"$elemMatch": {"device": {"$exists": True, "$ne": None}}}}
        if user_id:
            query["userId"] = user_id
        doc = collection.find_one(query, sort=[("updatedAt", -1)])
        if doc:
            doc_user_id = doc.get('userId')
            print(f"[MongoDB] 查询到最新文档: taskId={doc.get('taskId', 'N/A')[:8] if doc.get('taskId') else 'N/A'}, userId={doc_user_id}, records数量={len(doc.get('records', []))}")
    elif task_id:
        query = {"taskId": task_id}
        if user_id:
            query["userId"] = user_id
        doc = collection.find_one(query)
    
    if not doc and keyword:
        query = {"keyword": keyword}
        if user_id:
            query["userId"] = user_id
        doc = collection.find_one(query, sort=[("createdAt", -1)])
        if not doc:
            query = {"keyword": Regex(keyword, "i")}
            if user_id:
                query["userId"] = user_id
            doc = collection.find_one(query, sort=[("createdAt", -1)])
    
    if doc:
        records = doc.get('records', [])
        doc_user_id = doc.get('userId')
        print(f"[MongoDB] 找到文档: userId={doc_user_id}, records 数量: {len(records)}")
        for record in records:
            app_type = record.get('appType')
            device = record.get('device')
            operation_type = record.get('operationType')
            print(f"[MongoDB] record: appType={app_type}, device={device}, operationType={operation_type}")
            if app_type and device:
                app_to_device[app_type] = device
            elif app_type:
                print(f"[MongoDB] 警告: {app_type} 记录缺少 device 字段")
    else:
        if user_id:
            print(f"[MongoDB] 未找到 userId={user_id} 的设备信息")
        else:
            print(f"[MongoDB] 未找到设备信息")
    
    print(f"[MongoDB] 最终加载的设备映射: {app_to_device}")
    mongodb_writer.close()
    return app_to_device


class MongoDBWriter:
    """MongoDB writer for search results."""
    
    def __init__(self, connection_string: str, database_name: str = "waimai-server"):
        """
        Initialize MongoDB connection.
        
        Args:
            connection_string: MongoDB connection string, e.g., "mongodb://host:port"
            database_name: Database name, default "waimai-server"
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.client = None
        self.db = None
        self._connect()
    
    def _connect(self):
        """Establish MongoDB connection."""
        self.client = MongoClient(self.connection_string)
        self.db = self.client[self.database_name]
        self.client.admin.command('ping')
        print(f"[MongoDB] 连接成功: {self.database_name}")
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self.client is not None and self.db is not None
    
    def _build_query(self, task_id: str, user_id: Union[str, int]) -> dict:
        """Build MongoDB query with taskId and userId."""
        return {"taskId": task_id, "userId": user_id}
    
    def _is_final_state(self, operation_type: Optional[str]) -> bool:
        """Check if operationType is a final state that should not be overwritten."""
        return operation_type in ("search_success", "search_fail")
    
    def _should_skip_update(self, existing_op_type: Optional[str], new_op_type: Optional[str]) -> bool:
        """Check if update should be skipped to protect final states."""
        return self._is_final_state(existing_op_type) and not self._is_final_state(new_op_type)
    
    def _update_or_create_record(
        self,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
        record: dict,
    ) -> None:
        """Update existing record or create new one."""
        if self.db is None:
            print(f"[MongoDB] {app_type}: db未初始化")
            return
        
        if isinstance(user_id, list):
            user_id = user_id[0] if user_id else None
        
        if not task_id or not user_id:
            print(f"[MongoDB] {app_type}: 参数无效 (task_id={task_id}, user_id={user_id})")
            return
        
        collection = self.db['tasks']
        query = self._build_query(task_id, user_id)
        doc = collection.find_one(query)
        
        # Note: device field is read-only, not written here
        
        if doc and doc.get("records"):
            existing_record_index = None
            for idx, r in enumerate(doc.get("records", [])):
                if r.get("appType") == app_type:
                    existing_record_index = idx
                    break
            
            if existing_record_index is not None:
                existing_op_type = doc.get("records", [])[existing_record_index].get("operationType")
                new_op_type = record.get("operationType")
                
                if self._should_skip_update(existing_op_type, new_op_type):
                    print(f"[MongoDB] {app_type}: 跳过更新 - 记录已完成 ({existing_op_type})，不允许覆盖为 {new_op_type}")
                    return
                
                print(f"[MongoDB] {app_type}: 更新现有记录，索引={existing_record_index}, operationType={existing_op_type} -> {new_op_type}")
                update_fields = {
                    "userId": user_id,
                    "keyword": keyword,
                    "updatedAt": datetime.now(),
                    f"records.{existing_record_index}.operationType": record["operationType"],
                    f"records.{existing_record_index}.failReason": record.get("failReason"),
                    f"records.{existing_record_index}.completedAt": record["completedAt"],
                    f"records.{existing_record_index}.searchResult": record["searchResult"]
                }
                # Note: device field is read-only, not updated here
                result = collection.update_one(query, {"$set": update_fields})
                print(f"[MongoDB] {app_type}: 更新结果 - matched={result.matched_count}, modified={result.modified_count}")
                if result.matched_count == 0:
                    print(f"[MongoDB] {app_type}: 警告 - 未找到匹配的文档 (taskId={task_id[:8]}...)")
                if result.modified_count == 0:
                    print(f"[MongoDB] {app_type}: 警告 - 文档未修改（可能值相同）")
            else:
                # Insert at correct position based on app_type order (jd -> tb -> mt)
                self._insert_record_at_ordered_position(
                    collection, task_id, user_id, keyword, app_type, record
                )
        else:
            # Initialize records array with ordered placeholders (jd -> tb -> mt)
            self._initialize_ordered_records(
                collection, task_id, user_id, keyword, app_type, record
            )
    
    def _get_app_type_order(self) -> list:
        """Get app type order: jd -> tb -> mt"""
        return ["jd", "tb", "mt"]
    
    def _initialize_ordered_records(
        self,
        collection,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
        record: dict,
    ) -> None:
        """Initialize records array with ordered placeholders."""
        app_order = self._get_app_type_order()
        app_index = app_order.index(app_type) if app_type in app_order else len(app_order)
        
        # Create placeholder records for all apps before current one
        records = []
        for i, at in enumerate(app_order):
            if i < app_index:
                placeholder = {
                    "operationType": None,
                    "failReason": None,
                    "appType": at,
                    "completedAt": None,
                    "searchResult": []
                }
                records.append(placeholder)
            elif i == app_index:
                records.append(record)
        
        query = self._build_query(task_id, user_id)
        collection.update_one(
            query,
            {
                "$set": {
                    "userId": user_id,
                    "keyword": keyword,
                    "updatedAt": datetime.now(),
                    "records": records
                }
            },
            upsert=True
        )
        print(f"[MongoDB] {app_type}: 创建新文档，按顺序初始化记录")
    
    def _insert_record_at_ordered_position(
        self,
        collection,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
        record: dict,
    ) -> None:
        """Insert record at correct position based on app_type order (jd -> tb -> mt)."""
        app_order = self._get_app_type_order()
        app_index = app_order.index(app_type) if app_type in app_order else len(app_order)
        
        # Get existing records
        query = self._build_query(task_id, user_id)
        doc = collection.find_one(query)
        if not doc:
            print(f"[MongoDB] {app_type}: 未找到匹配的文档 (taskId={task_id[:8]}..., userId={user_id})，无法插入记录")
            return
        existing_records = doc.get("records", [])
        existing_types = [r.get("appType") for r in existing_records]
        
        # Find insertion position: count how many ordered apps should come before this one
        insert_index = sum(1 for at in app_order[:app_index] if at in existing_types)
        
        # Insert at position
        collection.update_one(
            query,
            {
                "$set": {
                    "userId": user_id,
                    "keyword": keyword,
                    "updatedAt": datetime.now()
                },
                "$push": {
                    "records": {
                        "$each": [record],
                        "$position": insert_index
                    }
                }
            }
        )
        print(f"[MongoDB] {app_type}: 按顺序插入记录，位置={insert_index}")
    
    def write_search_result(
        self,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        product: str,
        seller: Optional[str],
        app_type: str,
        price: Optional[float],
        delivery_fee: float,
        total_fee: Optional[float],
        pack_fee: float = 0.0,
        minimum_price: Optional[str] = None,
    ) -> bool:
        """
        Write search result to tasks collection.
        
        Args:
            task_id: Task ID
            user_id: User ID (str or int, preserves MongoDB type)
            keyword: Search keyword (user input)
            product: Product name
            seller: Seller name (can be None)
            app_type: App type ('mt', 'jd', 'tb')
            price: Product price (商品单价, can be None if not extracted by model)
            delivery_fee: Delivery fee
            total_fee: Total fee (总计, can be None if not extracted by model)
            pack_fee: Packing fee
            minimum_price: 'false' if minimum order not met, None otherwise
            
        Returns:
            bool: True if write successful
        """
        if not self.is_connected():
            print("[MongoDB] 未连接")
            return False
        
        # Build search result item
        search_result_item = {
            "product": product,
            "seller": seller,
            "price": price,
            "deliveryFee": delivery_fee,
            "packFee": pack_fee,
            "totalFee": total_fee,
            "minimumPrice": minimum_price,
        }
        
        record = {
            "operationType": "search_success",
            "failReason": None,
            "appType": app_type,
            "completedAt": datetime.now().isoformat(),
            "searchResult": [search_result_item]
        }
        
        self._update_or_create_record(task_id, user_id, keyword, app_type, record)
        print(f"[MongoDB] 写入成功: {app_type}")
        return True
    
    def write_search_fail(
        self,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
        reason: str,
    ) -> bool:
        """
        Write search failure record to tasks collection.
        
        Args:
            task_id: Task ID
            user_id: User ID (str or int, preserves MongoDB type)
            keyword: Search keyword
            app_type: App type ('mt', 'jd', 'tb')
            reason: Failure reason
            
        Returns:
            bool: True if write successful
        """
        if not self.is_connected():
            print("[MongoDB] 未连接")
            return False
        
        record = {
            "operationType": "search_fail",
            "failReason": reason,
            "appType": app_type,
            "completedAt": datetime.now().isoformat(),
            "searchResult": []
        }
        
        self._update_or_create_record(task_id, user_id, keyword, app_type, record)
        print(f"[MongoDB] {app_type}: 写入失败记录, 原因: {reason}")
        return True
    
    def write_takeover(
        self,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
    ) -> bool:
        """Write takeover record to tasks collection."""
        if not self.is_connected():
            print(f"[MongoDB] {app_type}: 未连接，无法写入takeover")
            return False
        
        if not task_id or not user_id or not keyword:
            print(f"[MongoDB] {app_type}: 参数缺失，无法写入takeover (task_id={bool(task_id)}, user_id={bool(user_id)}, keyword={bool(keyword)})")
            return False
        
        record = {
            "operationType": "takeover",
            "failReason": None,
            "appType": app_type,
            "completedAt": datetime.now().isoformat(),
            "searchResult": []
        }
        
        try:
            self._update_or_create_record(task_id, user_id, keyword, app_type, record)
            print(f"[MongoDB] {app_type}: 触发接管 (taskId={task_id[:8]}...)")
            return True
        except Exception as e:
            print(f"[MongoDB] {app_type}: 写入takeover失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def write_takeover_exit(
        self,
        task_id: str,
        user_id: Union[str, int],
        keyword: str,
        app_type: str,
    ) -> bool:
        """Write takeover exit record to tasks collection."""
        if not self.is_connected():
            return False
        
        record = {
            "operationType": "takeover_exit",
            "failReason": None,
            "appType": app_type,
            "completedAt": datetime.now().isoformat(),
            "searchResult": []
        }
        
        self._update_or_create_record(task_id, user_id, keyword, app_type, record)
        print(f"[MongoDB] {app_type}: 退出接管")
        return True
    
    def get_document_operation_type(self, task_id: str, user_id: Union[str, int]) -> Optional[str]:
        """Get top-level operationType from document."""
        if not self.is_connected():
            return None
        
        collection = self.db['tasks']
        query = self._build_query(task_id, user_id)
        doc = collection.find_one(query, {"operationType": 1})
        return doc.get("operationType") if doc else None
    
    def get_record_operation_type(self, task_id: str, app_type: str, user_id: Union[str, int]) -> Optional[str]:
        """Get operationType for the specified app_type record."""
        if not self.is_connected():
            return None
        
        collection = self.db['tasks']
        query = self._build_query(task_id, user_id)
        doc = collection.find_one(query, {"records": 1})
        if not doc:
            return None
        
        for record in doc.get("records", []):
            if record.get("appType") == app_type:
                return record.get("operationType")
        return None
    
    def wait_for_takeover_exit(
        self,
        task_id: str,
        app_type: str,
        user_id: Union[str, int],
        message: str = "等待前端写入 takeover_exit...",
        max_wait_time: int = 300,
    ) -> bool:
        """Wait for takeover_exit using polling. Returns True if task should be terminated."""
        doc_op_type = self.get_document_operation_type(task_id, user_id)
        if doc_op_type == "search_completed":
            print(f"[任务终止] 检测到顶层 operationType=search_completed，终止执行")
            return True
        
        op_type = self.get_record_operation_type(task_id, app_type, user_id)
        if op_type not in ("takeover", "user_takeover"):
            return False
        
        print(f"[Takeover] 检测到 {op_type}，{message}")
        start_time = time.time()
        check_interval = 0.3
        sleep_chunk = 0.05
        
        global _interrupt_flag, _old_signal_handler
        _old_signal_handler = signal.signal(signal.SIGINT, _set_interrupt_flag)
        _interrupt_flag = False
        
        while time.time() - start_time < max_wait_time:
            if _interrupt_flag:
                _restore_signal_handler()
                print(f"[Takeover] 收到中断信号，终止任务")
                return True
            
            doc_op_type = self.get_document_operation_type(task_id, user_id)
            if doc_op_type == "search_completed":
                _restore_signal_handler()
                print(f"[任务终止] 检测到顶层 operationType=search_completed，终止执行")
                return True
            
            op_type = self.get_record_operation_type(task_id, app_type, user_id)
            if op_type not in ("takeover", "user_takeover"):
                _restore_signal_handler()
                print(f"[Takeover] 检测到 {op_type}，继续执行")
                return False
            
            remaining = min(check_interval, max_wait_time - (time.time() - start_time))
            if remaining <= 0:
                break
            
            # Split sleep into chunks for faster interrupt response
            end_sleep = time.time() + remaining
            while time.time() < end_sleep:
                if _interrupt_flag:
                    _restore_signal_handler()
                    print(f"[Takeover] 收到中断信号，终止任务")
                    return True
                sleep_time = min(sleep_chunk, end_sleep - time.time())
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        _restore_signal_handler()
        print(f"[Takeover] 超时，继续执行")
        return False
    
    def close(self):
        """Close MongoDB connection."""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None



