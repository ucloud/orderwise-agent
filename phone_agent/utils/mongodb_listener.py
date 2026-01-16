"""MongoDB listener for new tasks."""

import time
import threading
from typing import Callable, Optional

from pymongo import MongoClient


class MongoDBListener:
    """MongoDB listener for new tasks in tasks collection."""
    
    def __init__(self, connection_string: str, database_name: str = "waimai-server", 
                 collection_name: str = "tasks"):
        """
        Initialize MongoDB listener.
        
        Args:
            connection_string: MongoDB connection string, e.g., "mongodb://host:port"
            database_name: Database name, default "waimai-server"
            collection_name: Collection name, default "tasks"
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None
        self._running = False
        self._thread = None
        self._callback = None
        self._connect()
    
    def _connect(self):
        """Establish MongoDB connection."""
        self.client = MongoClient(self.connection_string)
        self.db = self.client[self.database_name]
        self.collection = self.db[self.collection_name]
        self.client.admin.command('ping')
        print(f"[MongoDB监听器] 连接成功: {self.database_name}.{self.collection_name}")
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self.client is not None and self.collection is not None
    
    def start_listening(self, callback: Callable[[str, dict], None], 
                       filter_keyword: Optional[str] = None):
        """
        Start listening for new documents.
        
        Args:
            callback: Callback function receiving (keyword, document)
            filter_keyword: Optional keyword filter
        """
        if not self.is_connected():
            print("[MongoDB监听器] 未连接，无法启动监听")
            return
        
        if self._running:
            print("[MongoDB监听器] 已在运行中")
            return
        
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, args=(filter_keyword,), daemon=True)
        self._thread.start()
        print(f"[MongoDB监听器] 开始监听 {self.database_name}.{self.collection_name} 的新数据...")
    
    def _listen_loop(self, filter_keyword: Optional[str] = None):
        """Listen loop using Change Streams with polling fallback."""
        processed_task_ids = set()
        
        try:
            pipeline = [{"$match": {"operationType": "insert"}}]
            if filter_keyword:
                pipeline.append({"$match": {"fullDocument.keyword": filter_keyword}})
            
            with self.collection.watch(pipeline) as stream:
                print("[MongoDB监听器] 使用 Change Streams 实时监听...")
                for change in stream:
                    if not self._running:
                        break
                    
                    doc = change.get("fullDocument")
                    if doc:
                        self._process_document(doc, processed_task_ids)
        except Exception as e:
            print(f"[MongoDB监听器] Change Streams 不可用，回退到轮询模式: {e}")
            self._listen_loop_polling(filter_keyword, processed_task_ids)
    
    def _process_document(self, doc: dict, processed_task_ids: set) -> None:
        """Process a document and trigger callback if new task detected."""
        task_id = doc.get("taskId")
        keyword = doc.get("keyword")
        
        if not task_id or not keyword or task_id in processed_task_ids:
            return
        
        processed_task_ids.add(task_id)
        print(f"[MongoDB监听器] 检测到新任务: keyword={keyword}, taskId={task_id}")
        if self._callback:
            self._callback(keyword, doc)
    
    def _listen_loop_polling(self, filter_keyword: Optional[str] = None, processed_task_ids: Optional[set] = None):
        """Fallback polling loop."""
        processed_task_ids = processed_task_ids or set()
        last_id = self._get_last_id()
        
        while self._running:
            new_docs = self._query_new_docs(last_id, filter_keyword)
            
            for doc in new_docs:
                self._process_document(doc, processed_task_ids)
                doc_id = doc.get("_id")
                if doc_id and (not last_id or doc_id > last_id):
                    last_id = doc_id
            
            time.sleep(2 if not new_docs else 0.5)
    
    def _get_last_id(self):
        """Get last document _id."""
        if self.collection is None:
            return None
        doc = self.collection.find_one(sort=[("_id", -1)])
        return doc.get("_id") if doc else None
    
    def _query_new_docs(self, last_id, filter_keyword):
        """Query new documents."""
        if self.collection is None:
            return []
        query = {}
        if last_id:
            query["_id"] = {"$gt": last_id}
        if filter_keyword:
            query["keyword"] = filter_keyword
        return list(self.collection.find(query).sort("_id", 1).limit(10))
    
    def stop_listening(self):
        """Stop listening."""
        if not self._running:
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("[MongoDB监听器] 已停止监听")
    
    def close(self):
        """Close MongoDB connection."""
        self.stop_listening()
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            self.collection = None

