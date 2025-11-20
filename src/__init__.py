"""
BackcastPro package entry point.

This module provides access to the main BackcastPro functionality.
"""

# Import everything from the BackcastPro package
from .BackcastPro import *

# Also make the BackcastPro package directly accessible
import BackcastPro

# .envファイルの読み込み（プロジェクトルートから）
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.joinpath(Path(__file__), '.env'))