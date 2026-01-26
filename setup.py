#!/usr/bin/env python3
"""Setup script for OrderWise-Agent."""

from setuptools import find_packages, setup

with open("README_PYPI.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="orderwise-agent",
    version="1.0.2",
    author="UCloud",
    author_email="orderwise.agent@gmail.com",
    description="基于 AutoGLM 的智能外卖比价 Agent",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ucloud/orderwise-agent",
    packages=find_packages(include=["orderwise_agent*", "phone_agent*", "mcp_mode*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10",
    install_requires=[
        "PyYAML>=6.0",
        "Pillow>=12.0.0",
        "pydantic>=2.12.5",
        "openai>=2.9.0",
        "pymongo>=4.15.5",
        "starlette>=0.50.0",
        "mcp>=1.0.0",
        "fastmcp>=0.1.0",
        "uvicorn>=0.20.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "orderwise-agent=orderwise_agent.__main__:main",
        ],
    },
)
