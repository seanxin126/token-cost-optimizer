#!/usr/bin/env python3
"""
Token Cost Optimizer - Fast Token & Cost Estimator
估算指定文件、目录或文本的 Token 消耗量与上下文占比。
"""

import sys
import os
from pathlib import Path

# 确保 Windows 终端 UTF-8 兼容输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def estimate_tokens_from_text(text: str) -> int:
    chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
    other_chars = len(text) - chinese_chars
    tokens = int((chinese_chars / 1.3) + (other_chars / 3.8))
    return max(1, tokens)

def main():
    if len(sys.argv) < 2:
        print("Usage: python estimate_tokens.py <file_or_directory_path>")
        sys.exit(1)
        
    target_path = Path(sys.argv[1])
    if not target_path.exists():
        print(f"Error: {target_path} not found")
        sys.exit(1)
        
    if target_path.is_file():
        content = target_path.read_text(encoding="utf-8", errors="replace")
        tokens = estimate_tokens_from_text(content)
        size_kb = len(content.encode("utf-8")) / 1024
        print(f"📄 文件: {target_path.name}")
        print(f"   大小: {size_kb:.1f} KB")
        print(f"   预估 Token 量: ~{tokens:,} Tokens")
    else:
        total_tokens = 0
        file_count = 0
        print(f"📁 扫描目录: {target_path}")
        ignored_dirs = {".git", ".venv", "__pycache__", ".vscode", "node_modules", "build", "dist"}
        for p in target_path.rglob("*"):
            if p.is_file() and not any(part in ignored_dirs for part in p.parts):
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    tokens = estimate_tokens_from_text(content)
                    total_tokens += tokens
                    file_count += 1
                except Exception:
                    pass
        print(f"   有效文本文件数: {file_count} 个")
        print(f"   目录总预估 Token 量: ~{total_tokens:,} Tokens")

if __name__ == "__main__":
    main()
