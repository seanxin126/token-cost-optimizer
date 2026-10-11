#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Cost Optimizer - DOM & Web Page Interactive Skeleton Pruner
专为小红书等复杂单页应用（SPA）及远程浏览器自动化控制打造。
剔除 SVG、内联样式、混淆类名、隐藏节点、广告脚本，提取精简的高价值可交互元素树（Interactive Selector Tree），
实现 90%~98% 的 HTML / DOM Token 压缩。
"""

import sys
import re
import argparse
from pathlib import Path
from html.parser import HTMLParser

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 核心保留属性（用于精确定位和交互）
KEEP_ATTRS = {
    'id', 'name', 'type', 'placeholder', 'role', 'aria-label', 'href', 
    'value', 'data-testid', 'data-v-', 'title', 'alt', 'tabindex', 'action'
}

# 必须完全剥离并跳过子内容的标签
STRIP_BLOCK_TAGS = {
    'script', 'style', 'svg', 'noscript', 'iframe', 'canvas', 'symbol', 'defs'
}

# Void elements (HTML 自闭合空元素，无对应 endtag)
VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 
    'link', 'meta', 'param', 'source', 'track', 'wbr'
}

# 核心交互标签
INTERACTIVE_TAGS = {
    'button', 'input', 'textarea', 'select', 'option', 'a', 'form', 'label'
}

class DOMPruner(HTMLParser):
    def __init__(self, mode='interactive', max_text_len=60):
        super().__init__()
        self.mode = mode
        self.max_text_len = max_text_len
        self.interactive_elements = []
        self.skip_stack = 0
        self.tag_counter = 0

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        
        # 处理需要剥离的区块标签
        if tag_lower in STRIP_BLOCK_TAGS:
            self.skip_stack += 1
            return

        if self.skip_stack > 0:
            return

        attr_dict = dict(attrs)
        style_val = attr_dict.get('style', '').lower()
        
        # 过滤隐藏的非交互容器（但如果是文件上传 input 等，允许保留）
        if ('display: none' in style_val or 'visibility: hidden' in style_val) and tag_lower not in INTERACTIVE_TAGS:
            if tag_lower not in VOID_TAGS:
                self.skip_stack += 1
            return

        self.tag_counter += 1
        
        # 筛选关键属性
        filtered_attrs = {}
        for k, v in attr_dict.items():
            k_lower = k.lower()
            if k_lower in KEEP_ATTRS:
                if v and len(v) > 80:
                    v = v[:77] + '...'
                filtered_attrs[k_lower] = v
            elif k_lower == 'class':
                # 提取有语义的 class，去除混淆 hash
                classes = v.split()
                meaningful = [c for c in classes if not re.match(r'^(css|styled|jsx|v-|sc-)[0-9a-zA-Z_-]{5,}$', c)]
                if meaningful:
                    filtered_attrs['class'] = ' '.join(meaningful[:3])

        is_interactive = (
            tag_lower in INTERACTIVE_TAGS or 
            'role' in filtered_attrs or 
            'data-testid' in filtered_attrs or
            'onclick' in attr_dict or
            'cursor: pointer' in style_val or
            any(k in filtered_attrs.get('class', '').lower() for k in ('btn', 'button', 'tab', 'nav-item', 'active', 'card', 'item'))
        )

        if is_interactive:
            element_info = {
                'index': self.tag_counter,
                'tag': tag_lower,
                'attrs': filtered_attrs,
                'text': ''
            }
            self.interactive_elements.append(element_info)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in STRIP_BLOCK_TAGS:
            if self.skip_stack > 0:
                self.skip_stack -= 1

    def handle_data(self, data):
        if self.skip_stack > 0 or not self.interactive_elements:
            return

        clean_text = ' '.join(data.split())
        if clean_text:
            if len(clean_text) > self.max_text_len:
                clean_text = clean_text[:self.max_text_len - 3] + '...'
            # 将文本附加到最近的一个交互元素中
            if not self.interactive_elements[-1]['text']:
                self.interactive_elements[-1]['text'] = clean_text

def prune_dom_content(html_text: str, mode: str = 'interactive') -> str:
    raw_size = len(html_text)
    
    # 预处理：快速剔除庞大的 base64 数据和内联 svg
    html_text = re.sub(r'data:[a-zA-Z0-9/+\-.;=]+;base64,[a-zA-Z0-9+/=]+', 'data:...[base64]', html_text)
    html_text = re.sub(r'<svg[\s\S]*?<\/svg>', '', html_text, flags=re.IGNORECASE)
    # v2 新增（2026-09-30）：HTML 注释（模板/条件注释经常很大）直接剔除
    html_text = re.sub(r'<!--[\s\S]*?-->', '', html_text)
    # v2 新增：超长内联 style 属性只留前 40 字符示意（selector 用 id/class，不依赖它）
    html_text = re.sub(r'style="[^"]{80,}"',
                       lambda m: 'style="' + m.group(0)[7:47] + '..."', html_text)
    
    parser = DOMPruner(mode=mode)
    try:
        parser.feed(html_text)
    except Exception as e:
        return f"# [DOM Parser Fallback - Error: {e}]\n" + html_text[:2000]

    lines = []
    lines.append(f"# === [DOM 精简交互树 (Interactive Action Map)] ===")
    lines.append(f"# 提取到 {len(parser.interactive_elements)} 个关键可操作/输入节点 (已剥离所有 SVG、脚本与噪音)\n")

    for item in parser.interactive_elements:
        tag = item['tag']
        attrs_str = " ".join([f'{k}="{v}"' for k, v in item['attrs'].items()])
        text_str = f" text=\"{item['text']}\"" if item['text'] else ""
        
        # 推荐 selector
        selector = tag
        if 'id' in item['attrs']:
            selector = f"#{item['attrs']['id']}"
        elif 'data-testid' in item['attrs']:
            selector = f"[{tag} data-testid=\"{item['attrs']['data-testid']}\"]"
        elif 'placeholder' in item['attrs']:
            selector = f"[{tag} placeholder=\"{item['attrs']['placeholder']}\"]"
        elif 'name' in item['attrs']:
            selector = f"[{tag} name=\"{item['attrs']['name']}\"]"
        elif 'aria-label' in item['attrs']:
            selector = f"[{tag} aria-label=\"{item['attrs']['aria-label']}\"]"
        elif 'class' in item['attrs']:
            c_first = item['attrs']['class'].split()[0]
            selector = f"{tag}.{c_first}"

        lines.append(f"[{item['index']:02d}] <{tag} {attrs_str}>{text_str} -> Selector: `{selector}`")

    output_str = "\n".join(lines)
    comp_size = len(output_str)
    ratio = (1 - (comp_size / raw_size)) * 100 if raw_size > 0 else 0
    
    header = f"# === [HTML/DOM 极限压缩] 原始: {raw_size} 字符 -> 压缩后: {comp_size} 字符 (节省 {ratio:.1f}%) ===\n"
    return header + output_str

def main():
    parser = argparse.ArgumentParser(description="DOM & Web Page Interactive Skeleton Pruner for Browser Automation")
    parser.add_argument("path", help="HTML or DOM file path (or '-' to read from stdin)")
    parser.add_argument("--mode", choices=["interactive", "compact"], default="interactive", help="Pruning mode")
    args = parser.parse_args()

    if args.path == "-":
        content = sys.stdin.read()
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"Error: {p} not found")
            sys.exit(1)
        content = p.read_text(encoding="utf-8", errors="replace")

    result = prune_dom_content(content, mode=args.mode)
    print(result)

if __name__ == "__main__":
    main()
