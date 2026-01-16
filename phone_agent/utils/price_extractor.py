"""Price extraction from finish messages."""

import re
from typing import Optional, Dict


def extract_price_from_message(message: str, app_name: Optional[str] = None) -> Optional[Dict[str, float]]:
    """
    Extract price information from finish message.
    
    Field meanings (完全依赖模型识别，不进行任何计算):
    - price: 商品单价 (product unit price, extracted from "优惠后价格" or "商品单价")
    - delivery_fee: 配送费 (delivery fee, extracted from "配送费" or "运费")
    - pack_fee: 包装费 (packing fee, extracted from "打包费" or "包装费")
    - total_fee: 总计 (total amount, extracted from "合计" or "应付总额" or "订单总价")
    
    Important: price 和 total_fee 之间没有任何计算逻辑，完全依赖模型识别的结果。
    如果模型没有输出某个字段，该字段将返回 None（而不是通过计算得出）。
    
    Supports three app formats:
    - Meituan: "商家：XXX，优惠后价格¥X.X，打包费¥X.X，配送费¥X.X，合计¥XX.X"
    - JD: "商家：XXX，优惠后价格¥X.X，打包费¥X.X，运费¥X.X，应付总额¥XX.X"
    - Taobao: "商家：XXX，商品单价¥XX.X，打包费¥X.X，配送费¥X.X，合计¥XX.X"
    
    Special handling for "凑单" (make up order) scenario:
    - If "差X元起送" is detected, total_fee should be 0 (cannot checkout yet)
    - price = 商品单价, delivery_fee = 配送费, total_fee = 0
    
    Args:
        message: Finish message from agent
        app_name: App name for format detection (optional)
        
    Returns:
        dict with keys: price (商品单价, may be None), delivery_fee (配送费), 
        pack_fee (包装费), total_fee (总计, may be None)
        or None if both price and total_fee extraction fail
    """
    if not message:
        return None
    
    message = re.sub(r'\*\*([^*]+)\*\*', r'\1', message)
    
    is_minimum_price_not_met = is_coupon_scenario(message)
    
    pack_fee = _extract_price_by_patterns(message, [
        r"(?:打包|包装)费[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
    ]) or 0.0
    
    delivery_fee = _extract_price_by_patterns(message, [
        r"(?:运费|配送费)[：:]?\s*¥?\s*(\d+(?:\.\d+)?)(?:\s*¥?\s*\d+(?:\.\d+)?)?",
        r"另需配送费约[：:]?\s*¥(\d+(?:\.\d+)?)",
    ]) or 0.0
    
    total_fee = _extract_price_by_patterns(message, [
        r"(?:订单总价|合计|应付总额)[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"总价[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"价格信息[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"购物车总价[：:为]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"总计[：:]?\s*(?:已优惠[^¥]*)?¥?\s*(\d+(?:\.\d+)?)",
        r"价格[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"优惠价[：:]?\s*¥?\s*(\d+(?:\.\d+)?)(?:（到手价）)?",
    ])
    
    price = _extract_price_by_patterns(message, [
        r"优惠后(?:商品)?价格[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"商品(?:单价|金额|价格)[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"优惠后[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"单件预估[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"商品[：:]\s*[^¥]*?-\s*¥?\s*(\d+(?:\.\d+)?)",
        r"优惠价[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        r"原价[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
        ])
    
    if is_minimum_price_not_met:
        total_fee = 0.0
        if price is None:
            price = _extract_price_by_patterns(message, [
                r"券后约?[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
                r"单件预估[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
                r"价格[：:是]?\s*¥?\s*(\d+(?:\.\d+)?)(?:/件|/杯|/份|/个)?",
                r"商品(?:价格|单价)[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
                r"价格信息[：:]?\s*¥?\s*(\d+(?:\.\d+)?)",
            ])
        if price is not None or delivery_fee > 0:
            return {
                'price': price or 0.0,
                'delivery_fee': delivery_fee,
                'pack_fee': pack_fee,
                'total_fee': 0.0
            }
        return None
    
    if total_fee is not None or price is not None:
        return {
            'price': price if price is not None else None,
            'delivery_fee': delivery_fee,
            'pack_fee': pack_fee,
            'total_fee': total_fee if total_fee is not None else None
        }
    
    return None


def detect_minimum_price(message: str) -> Optional[str]:
    """
    Detect if minimum order price is not met and extract the amount needed.
    
    Args:
        message: Finish message from agent
        
    Returns:
        "差X元起送" if minimum price not met (X is the amount needed), None otherwise
    """
    if not message:
        return None
    
    message = re.sub(r'\*\*([^*]+)\*\*', r'\1', message)
    
    amount_patterns = [
        r"(?:还)?差[：:：]?\s*¥\s*(\d+)\s*起送",  # "差¥2起送" or "还差¥2起送" (no 元)
        r"(?:还)?差[：:：]?\s*¥?\s*(\d+)\s*元(?:起送|起达)",  # "差2元起送" or "还差2元起达"
        r"满\d+元起送[，,]\s*还差[：:：]?\s*¥?\s*(\d+)\s*元",  # "满20元起送，还差2元"
        r"(?:还)?差[：:：]?\s*¥?\s*(\d+)\s*(?:元|达到起送费|才能达到起送费)",  # "差：¥3达到起送费"
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, message)
        if match:
            amount = match.group(1)
            return f"差{amount}元起送"
    
    fallback_keywords = [
        r"去凑单",
        r"差.*[元¥]?\d+.*起送",
        r"还差.*[元¥]?\d+.*起送",
        r"还差.*[元¥]?\d+.*起达",
        r"未满足起送价",
        r"起送价未满足",
    ]
    
    for keyword in fallback_keywords:
        if re.search(keyword, message):
            fallback_match = re.search(r"(?:还)?差[：:：]?\s*¥?\s*(\d+)", message)
            if fallback_match:
                amount = fallback_match.group(1)
                return f"差{amount}元起送"
            return None
    
    return None


def is_coupon_scenario(text: str) -> bool:
    """
    Check if text indicates a "去凑单" (make up order) scenario.
    
    This is a shared utility function used across the codebase to detect
    when minimum order price is not met.
    
    Args:
        text: Text to check (can be thinking, message, or any text)
        
    Returns:
        True if "去凑单" scenario is detected, False otherwise
    """
    if not text:
        return False
    # Use same pattern as extract_price_from_message for consistency
    # Match formats like: "差¥2起送", "差2元起送", "还差¥2起送", "还差2元起送", "去凑单", etc.
    coupon_pattern = r'差.*?[元¥]?\d+.*?起送|还差.*?[元¥]?\d+.*?起送|去凑单|凑单助手|满.*元起送.*差.*元|还差[：:]\s*¥?\s*\d+达到起送费|还差¥?\s*\d+才能达到起送费'
    return bool(re.search(coupon_pattern, text))


def is_login_page(text: str) -> bool:
    """
    Check if text indicates a login/verification page.
    
    This is a shared utility function used across the codebase to detect
    when the agent encounters a login or verification page.
    
    Args:
        text: Text to check (can be thinking, message, or any text)
        
    Returns:
        True if login page is detected, False otherwise
    """
    if not text:
        return False
    # 移除过于宽泛的"手机号"，避免误判结算页面的联系人信息
    login_keywords = ["登录", "验证码", "请输入手机号", "请输入验证码", "获取验证码", "同意协议并登录", "登录页面", "需要登录", "未登录", "人机验证", "真人验证", "需要真人完成验证", "手机号登录", "手机号验证"]
    return any(keyword in text for keyword in login_keywords)


def is_privacy_policy_page(text: str) -> bool:
    """
    Check if text indicates a privacy policy agreement page.
    
    Args:
        text: Text to check (can be thinking, message, or any text)
        
    Returns:
        True if privacy policy page is detected, False otherwise
    """
    if not text:
        return False
    privacy_keywords = ["隐私政策", "隐私协议", "隐私政策协议", "用户协议", "温馨提示"]
    return any(keyword in text for keyword in privacy_keywords)


def _extract_price_by_patterns(text: str, patterns: list) -> Optional[float]:
    """Extract price using multiple regex patterns."""
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None