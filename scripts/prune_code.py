#!/usr/bin/env python3
"""
Token Cost Optimizer - Code Skeleton & AST Pruner
提取 Python / 通用代码的类、函数签名、类型注解与 Docstring，剔除庞大函数体，以极低 Token 把握代码架构。
"""

import os
import sys
import ast
from pathlib import Path

# 确保 Windows 终端 UTF-8 兼容输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def prune_python_ast(source_code: str) -> str:
    """使用 Python AST 提取代码骨架"""
    try:
        tree = ast.parse(source_code)
    except Exception as e:
        return f"# [AST Parse Warning: {e}]\n" + "\n".join(source_code.splitlines()[:50])

    lines = []
    
    # 模块 docstring
    docstring = ast.get_docstring(tree)
    if docstring:
        lines.append(f'"""\n{docstring.strip()}\n"""\n')
        
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            lines.append(f"import {', '.join(names)}")
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            lines.append(f"from {node.module or ''} import {', '.join(names)}")
        elif isinstance(node, ast.ClassDef):
            lines.append(f"\nclass {node.name}:")
            class_doc = ast.get_docstring(node)
            if class_doc:
                lines.append(f'    """{class_doc.strip()}"""')
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    args = [a.arg for a in item.args.args]
                    lines.append(f"    {prefix} {item.name}({', '.join(args)}):")
                    fn_doc = ast.get_docstring(item)
                    if fn_doc:
                        lines.append(f'        """{fn_doc.strip()}"""')
                    lines.append("        ...")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            args = [a.arg for a in node.args.args]
            lines.append(f"\n{prefix} {node.name}({', '.join(args)}):")
            fn_doc = ast.get_docstring(node)
            if fn_doc:
                lines.append(f'    """{fn_doc.strip()}"""')
            lines.append("    ...")
            
    return "\n".join(lines)

def main():
    if len(sys.argv) < 2:
        print("Usage: python prune_code.py <file_path>")
        sys.exit(1)
        
    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: {file_path} not found")
        sys.exit(1)
        
    content = file_path.read_text(encoding="utf-8", errors="replace")
    original_size = len(content)
    
    if file_path.suffix == ".py":
        pruned = prune_python_ast(content)
    else:
        # 通用语言简易正则行过滤
        pruned_lines = [
            line for line in content.splitlines()
            if any(line.strip().startswith(kw) for kw in ["class ", "function ", "def ", "interface ", "type ", "export ", "public ", "private "])
        ]
        pruned = "\n".join(pruned_lines)
        
    pruned_size = len(pruned)
    ratio = (1 - (pruned_size / original_size)) * 100 if original_size > 0 else 0
    
    print(f"# === [Token 压缩结果] 原始大小: {original_size} 字符 -> 压缩后: {pruned_size} 字符 (节省 {ratio:.1f}%) ===")
    print(pruned)

if __name__ == "__main__":
    main()
