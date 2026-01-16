"""Benchmark utility functions."""
import os


def get_project_root() -> str:
    """Get project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


