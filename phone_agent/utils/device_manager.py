"""Device manager for robust device connection and health monitoring."""

import time
import threading
from typing import Dict, List, Optional, Set, Union
from dataclasses import dataclass

from phone_agent.adb import ADBConnection, list_devices, DeviceInfo
from phone_agent.utils.mongodb_writer import get_device_mapping_from_mongodb


@dataclass
class DeviceStatus:
    """Device status information."""
    device_id: str
    app_type: str
    connected: bool
    last_check: float
    reconnect_count: int = 0


class DeviceManager:
    """
    Robust device manager for multi-host, multi-device scenarios.
    
    Features:
    - Auto-connect devices from MongoDB
    - Health monitoring and auto-reconnect
    - Thread-safe operations
    - Support for multiple hosts and devices
    """
    
    def __init__(
        self,
        mongodb_connection_string: Optional[str] = None,
        health_check_interval: int = 30,
        max_reconnect_attempts: int = 3,
        reconnect_delay: float = 2.0,
    ):
        """
        Initialize device manager.
        
        Args:
            mongodb_connection_string: MongoDB connection string for reading device info
            health_check_interval: Health check interval in seconds
            max_reconnect_attempts: Maximum reconnect attempts per device
            reconnect_delay: Delay between reconnect attempts in seconds
        """
        self.mongodb_connection_string = mongodb_connection_string
        self.health_check_interval = health_check_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        
        self.conn = ADBConnection()
        self.device_statuses: Dict[str, DeviceStatus] = {}
        self.app_to_device: Dict[str, str] = {}
        
        self._lock = threading.Lock()
        self._device_locks: Dict[str, threading.Lock] = {}  # Per-device locks for concurrent access control
        self._health_check_thread: Optional[threading.Thread] = None
        self._running = False
    
    def load_devices_from_mongodb(
        self,
        task_id: Optional[str] = None,
        keyword: Optional[str] = None,
        user_id: Optional[Union[str, int]] = None,
        use_latest: bool = False,
    ) -> Dict[str, str]:
        """
        Load device mapping from MongoDB.
        
        Args:
            task_id: Task ID to query
            keyword: Keyword to query
            user_id: User ID to query (for distinguishing devices per user)
            use_latest: Use latest task with device info
        
        Returns:
            Dict mapping app_type -> device_id
        """
        if not self.mongodb_connection_string:
            return {}
        
        app_to_device = get_device_mapping_from_mongodb(
            self.mongodb_connection_string,
            task_id=task_id,
            keyword=keyword,
            user_id=user_id,
            use_latest=use_latest,
        )
        
        with self._lock:
            self.app_to_device.update(app_to_device)
            for app_type, device_id in app_to_device.items():
                if device_id not in self.device_statuses:
                    self.device_statuses[device_id] = DeviceStatus(
                        device_id=device_id,
                        app_type=app_type,
                        connected=False,
                        last_check=0.0,
                    )
                if device_id not in self._device_locks:
                    self._device_locks[device_id] = threading.Lock()
        
        return app_to_device
    
    def connect_devices(
        self,
        device_ids: Optional[List[str]] = None,
        app_to_device: Optional[Dict[str, str]] = None,
    ) -> Dict[str, bool]:
        """
        Connect to devices. Handles all device states (device/unauthorized/offline) internally.
        
        Args:
            device_ids: List of device IDs to connect (if None, uses app_to_device)
            app_to_device: Mapping of app_type -> device_id
        
        Returns:
            Dict mapping device_id -> success status
        """
        if app_to_device:
            device_ids = list(app_to_device.values())
        
        if not device_ids:
            device_ids = list(self.app_to_device.values())
        
        if not device_ids:
            return {}
        
        results = {}
        device_to_app = {v: k for k, v in (app_to_device or self.app_to_device).items()}
        
        for device_id in set(device_ids):
            device_info = self.conn.get_device_info(device_id)
            app_type = device_to_app.get(device_id, "unknown")

            if device_info and device_info.status == "device":
                results[device_id] = True
                self._update_device_status(device_id, True, app_type)
                continue

            if device_info and device_info.status == "unauthorized":
                print(f"[设备管理器] 设备未授权，重新连接: {device_id} ({app_type})")
                self.conn.disconnect(device_id)
                time.sleep(1)

            success, msg = self.conn.connect(device_id)
            results[device_id] = success
            self._update_device_status(device_id, success, app_type, msg)
        
        return results

    def _update_device_status(
        self,
        device_id: str,
        connected: bool,
        app_type: str,
        msg: Optional[str] = None,
    ):
        with self._lock:
            status = self.device_statuses.get(device_id)
            if status:
                status.connected = connected
                status.last_check = time.time()
                if not connected:
                    status.reconnect_count += 1
            else:
                self.device_statuses[device_id] = DeviceStatus(
                    device_id=device_id,
                    app_type=app_type,
                    connected=connected,
                    last_check=time.time(),
                )

        if connected:
            print(f"[设备管理器] 连接成功: {device_id} ({app_type})")
        else:
            print(f"[设备管理器] 连接失败: {device_id} ({app_type}): {msg or 'unknown'}")
    
    def get_connected_devices(self) -> List[str]:
        """Get list of currently connected device IDs."""
        with self._lock:
            return [
                device_id for device_id, status in self.device_statuses.items()
                if status.connected
            ]
    
    def is_device_connected(self, device_id: str) -> bool:
        """Check if a device is connected."""
        with self._lock:
            status = self.device_statuses.get(device_id)
            if status:
                return status.connected
            return self.conn.is_connected(device_id)
    
    def get_device_for_app(self, app_type: str) -> Optional[str]:
        """Get device ID for a specific app type."""
        with self._lock:
            return self.app_to_device.get(app_type)
    
    def start_health_monitoring(self):
        """Start background health monitoring thread."""
        if self._running:
            return
        
        self._running = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
        )
        self._health_check_thread.start()
        print("[设备管理器] 健康监控已启动")
    
    def stop_health_monitoring(self):
        """Stop background health monitoring."""
        self._running = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5)
        print("[设备管理器] 健康监控已停止")
    
    def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            time.sleep(self.health_check_interval)
            self._check_and_reconnect()
    
    def _check_and_reconnect(self):
        """Check device health and reconnect if needed."""
        with self._lock:
            devices_to_check = list(self.device_statuses.keys())

        for device_id in devices_to_check:
            with self._lock:
                status = self.device_statuses.get(device_id)
                if not status:
                    continue

            device_info = self.conn.get_device_info(device_id)
            is_connected = device_info and device_info.status == "device"

            with self._lock:
                status.connected = is_connected
                status.last_check = time.time()

            if is_connected:
                continue

            if device_info and device_info.status == "unauthorized":
                print(f"[设备管理器] 设备未授权，重新连接: {device_id} ({status.app_type})")
                self.conn.disconnect(device_id)
                time.sleep(1)

            if status.reconnect_count < self.max_reconnect_attempts:
                print(f"[设备管理器] 设备断开，尝试重连: {device_id} ({status.app_type})")
                success, msg = self.conn.connect(device_id)

                with self._lock:
                    status.connected = success
                    status.last_check = time.time()
                    if success:
                        status.reconnect_count = 0
                        print(f"[设备管理器] 重连成功: {device_id}")
                    else:
                        status.reconnect_count += 1
                        print(f"[设备管理器] 重连失败 ({status.reconnect_count}/{self.max_reconnect_attempts}): {device_id}: {msg}")

                time.sleep(self.reconnect_delay)
    
    def get_status_summary(self) -> Dict[str, Dict]:
        """Get status summary of all devices."""
        with self._lock:
            return {
                device_id: {
                    "app_type": status.app_type,
                    "connected": status.connected,
                    "reconnect_count": status.reconnect_count,
                    "last_check": status.last_check,
                }
                for device_id, status in self.device_statuses.items()
            }
    
    def ensure_devices_connected(
        self,
        task_id: Optional[str] = None,
        keyword: Optional[str] = None,
        user_id: Optional[Union[str, int]] = None,
    ) -> bool:
        """
        Ensure all required devices are connected.
        Loads from MongoDB if needed and connects devices.
        
        Args:
            task_id: Task ID for loading devices
            keyword: Keyword for loading devices
            user_id: User ID for loading devices (for distinguishing devices per user)
        
        Returns:
            True if all devices are connected
        """
        app_to_device = self.load_devices_from_mongodb(
            task_id=task_id,
            keyword=keyword,
            user_id=user_id,
        )
        
        if not app_to_device:
            return False
        
        results = self.connect_devices(app_to_device=app_to_device)
        return all(results.values())
    
    def acquire_device(self, device_id: str, timeout: float = 300.0) -> bool:
        """
        Acquire lock for a device to prevent concurrent access.
        
        Args:
            device_id: Device ID to acquire
            timeout: Maximum time to wait for lock (seconds)
        
        Returns:
            True if lock acquired successfully
        """
        with self._lock:
            if device_id not in self._device_locks:
                self._device_locks[device_id] = threading.Lock()
            lock = self._device_locks[device_id]
        
        acquired = lock.acquire(timeout=timeout)
        if acquired:
            print(f"[设备锁] 获取设备锁: {device_id}")
        else:
            print(f"[设备锁] 获取设备锁超时: {device_id}")
        return acquired
    
    def release_device(self, device_id: str):
        """
        Release lock for a device.
        
        Args:
            device_id: Device ID to release
        """
        with self._lock:
            lock = self._device_locks.get(device_id)
        
        if lock and lock.locked():
            lock.release()
            print(f"[设备锁] 释放设备锁: {device_id}")
    
    def get_unchecked_devices(self, device_ids: List[str], checked_devices: Set[str]) -> List[str]:
        """
        Get list of devices that haven't been pre-checked yet.
        
        Args:
            device_ids: List of device IDs to check
            checked_devices: Set of already checked device IDs
        
        Returns:
            List of device IDs that need pre-checking
        """
        return [d for d in device_ids if d and d not in checked_devices]
    
