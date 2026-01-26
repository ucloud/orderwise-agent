"""CLI 工具函数"""

APP_NAME_MAPPING = {"美团": "app1", "京东外卖": "app2", "淘宝闪购": "app3"}

def parse_apps_and_devices(apps_args):
    """解析 --apps 参数，必须指定设备映射格式"""
    apps_list = []
    device_mapping = {}
    
    for app_arg in apps_args:
        if "=" in app_arg:
            app_name, device_id = app_arg.split("=", 1)
            apps_list.append(app_name)
            app_key = APP_NAME_MAPPING.get(app_name)
            if app_key:
                device_mapping[app_key] = device_id
        else:
            raise ValueError(f"必须指定设备映射，格式：平台名=device-id。例如：--apps 美团=device1-id 京东外卖=device2-id")
    
    if not device_mapping:
        raise ValueError("必须至少指定一个平台的设备映射")
    
    return apps_list, device_mapping

def print_result(result):
    """打印比价结果"""
    if "error" in result:
        print(f"错误: {result['error']}")
        return False
    
    best = result['best_price']
    print(f"\n比价完成！")
    if best:
        print(f"最低价格: {best['app']} - ¥{best['total_fee']:.2f}")
        print(f"\n详细结果:")
        for app, data in result['platform_results'].items():
            print(f"  {app}: ¥{data['total_fee']:.2f}")
    else:
        print("未找到价格信息")
    return True

