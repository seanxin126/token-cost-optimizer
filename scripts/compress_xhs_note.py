#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Cost Optimizer - Xiaohongshu Note & Creator Pipeline Token Optimizer
专为小红书发帖/创作自动化设计：
1. 评估并优化小红书笔记标题、正文与 Tag 矩阵的 Token 密度
2. 自动提炼 SEO 关键词，去除非必要冗余符号
3. 检查小红书平台字符上限与违禁词/风控敏感词预检
"""

import sys
import re
import argparse
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 小红书高频敏感词与易限流词汇表
SENSITIVE_WORDS = [
    '最', '第一', '绝对', '独家', '顶级', '万能', '保准', '包过',
    '微信', '加v', '私聊', '淘宝', '拼多多', '购买链接', '外链'
]

def optimize_note(title: str, content: str, tags: list = None) -> dict:
    tags = tags or []
    
    # 标题优化（限 20 字以内）
    clean_title = re.sub(r'[\s_]+', ' ', title).strip()
    title_warning = ""
    if len(clean_title) > 20:
        title_warning = f"⚠️ 标题超出小红书 20 字限制 (当前: {len(clean_title)} 字)"
        
    # 正文冗余清洗（合并连续换行与重复表情符）
    clean_content = re.sub(r'\n{3,}', '\n\n', content)
    clean_content = re.sub(r'([!！?？~～.。]){3,}', r'\1\1', clean_content)
    
    # 敏感词扫描
    found_sensitive = []
    for word in SENSITIVE_WORDS:
        if word in clean_title or word in clean_content:
            found_sensitive.append(word)
            
    # 标签矩阵清洗
    clean_tags = []
    for t in tags:
        t_clean = t.strip().lstrip('#')
        if t_clean and t_clean not in clean_tags:
            clean_tags.append(t_clean)
            
    # 估算 Token
    total_chars = len(clean_title) + len(clean_content) + sum(len(t) for t in clean_tags)
    est_tokens = max(1, int(total_chars / 1.6))
    
    return {
        "title": clean_title,
        "title_len": len(clean_title),
        "title_warning": title_warning,
        "content": clean_content,
        "content_len": len(clean_content),
        "tags": clean_tags[:8], # 小红书推荐 5~8 个 tag
        "sensitive_alerts": found_sensitive,
        "estimated_tokens": est_tokens
    }

def main():
    parser = argparse.ArgumentParser(description="Xiaohongshu Note & Creator Pipeline Token Optimizer")
    parser.add_argument("--title", default="", help="Note title")
    parser.add_argument("--content", default="", help="Note content text")
    parser.add_argument("--file", help="File containing note content")
    parser.add_argument("--tags", help="Comma-separated tags")
    args = parser.parse_args()

    content = args.content
    if args.file:
        p = Path(args.file)
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")

    tags = [t.strip() for t in args.tags.split(',')] if args.tags else []
    
    res = optimize_note(args.title, content, tags)
    
    print("\n# === [小红书创作文案与 Token 评估] ===")
    print(f"📌 标题: {res['title']} ({res['title_len']}/20 字) {res['title_warning']}")
    print(f"📝 正文字数: {res['content_len']} 字符 | 预估消耗: {res['estimated_tokens']} Tokens")
    if res['sensitive_alerts']:
        print(f"🚨 敏感/风控词预警: {', '.join(res['sensitive_alerts'])}")
    if res['tags']:
        print(f"🏷️ 精炼标签: {' '.join(['#' + t for t in res['tags']])}")
    print("\n--- [清洗后正文预览] ---")
    print(res['content'][:400] + ("..." if len(res['content']) > 400 else ""))

if __name__ == "__main__":
    main()
