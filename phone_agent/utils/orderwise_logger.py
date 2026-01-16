"""OrderWise 日志工具 - 仅用于 OrderWise 改造的部分"""
import os
import sys

_verbose = os.getenv("ORDERWISE_VERBOSE", "0") == "1"
_quiet = os.getenv("ORDERWISE_QUIET", "0") == "1"

def set_verbose(enabled: bool):
    """设置 verbose 模式"""
    global _verbose
    _verbose = enabled

def set_quiet(enabled: bool):
    """设置 quiet 模式"""
    global _quiet
    _quiet = enabled

def debug(msg: str, flush: bool = False):
    """调试信息（仅在 verbose 模式显示）"""
    if _verbose and not _quiet:
        print(msg, flush=flush)

def info(msg: str, flush: bool = False):
    """正常信息（quiet 模式不显示）"""
    if not _quiet:
        print(msg, flush=flush)

def warning(msg: str, flush: bool = False):
    """警告信息（quiet 模式也显示）"""
    print(msg, flush=flush)

def error(msg: str, flush: bool = False):
    """错误信息（quiet 模式也显示）"""
    print(msg, flush=flush, file=sys.stderr)

