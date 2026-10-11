#!/usr/bin/env python3
"""
Token Cost Optimizer - JSON Schema & Structural Compressor
将庞大的 JSON 数据压缩为结构 Schema + 单个精简样本，避免将数十万行 JSON 灌入模型。
"""

import sys
import json
from pathlib import Path
from typing import Any

# 确保 Windows 终端 UTF-8 兼容输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def summarize_json_structure(data: Any, max_depth: int = 3, current_depth: int = 0,
                             keep_sample: bool = False) -> Any:
    """keep_sample=True 时叶子保留一个真实样本值（超长截断），适合需要看实际值的排错场景。"""
    if current_depth > max_depth:
        return "..."

    if isinstance(data, dict):
        summary = {}
        for k, v in list(data.items())[:15]:
            summary[k] = summarize_json_structure(v, max_depth, current_depth + 1, keep_sample)
        if len(data) > 15:
            summary["_total_keys_count"] = len(data)
        return summary
    elif isinstance(data, list):
        if not data:
            return []
        sample = summarize_json_structure(data[0], max_depth, current_depth + 1, keep_sample)
        return [sample, f"... ({len(data)} total items)"]
    else:
        if keep_sample:
            if isinstance(data, str) and len(data) > 120:
                return data[:117] + "..."
            return data
        return type(data).__name__

def main():
    if len(sys.argv) < 2:
        print("Usage: python compress_json.py <json_file_path> [--sample]")
        print("  --sample: 叶子保留真实样本值（超长截断），适合排错时看实际值")
        sys.exit(1)

    path = Path(sys.argv[1])
    keep_sample = "--sample" in sys.argv
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)

    raw_text = path.read_text(encoding="utf-8", errors="replace")
    original_size = len(raw_text)

    try:
        data = json.loads(raw_text)
        summary = summarize_json_structure(data, keep_sample=keep_sample)
        formatted = json.dumps(summary, indent=2, ensure_ascii=False)
        compressed_size = len(formatted)
        ratio = (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0
        
        print(f"# === [JSON 结构压缩] 原始: {original_size} 字符 -> 压缩后: {compressed_size} 字符 (节省 {ratio:.1f}%) ===")
        print(formatted)
    except Exception as e:
        print(f"JSON Parse Error: {e}")

if __name__ == "__main__":
    main()
