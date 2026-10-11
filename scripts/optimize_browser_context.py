#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Cost Optimizer - Browser Session & Xiaohongshu (XHS) API Response Optimizer
专为小红书等平台远程控制设计：
1. 压缩抓包响应与 API 报文（剔除 tracker、xsec_token、冗余多分辨率 CDN 图片等）
2. 提炼核心 Cookies 鉴权 Token（a1, web_session, webId 等）
3. 压缩 CDP/Playwright Accessibility Tree 与视口交互数据
"""

import sys
import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 小红书核心鉴权与状态 Cookies（其余数十个分析/打点 Cookie 均可安全剔除）
XHS_CORE_COOKIES = {
    'a1', 'web_session', 'webId', 'gid', 'load_time', 
    'unread', 'xsec_token', 'sec_poison_id', 'acw_tc', 'customer-sso-ticket'
}

# 小红书 API 常见噪音与追踪字段
XHS_NOISE_KEYS = {
    'track_info', 'trace_id', 'beacon_id', 'exposure_data', 'log_info',
    'xsec_source', 'share_link', 'search_id', 'extra_dump', 'preload_info',
    'request_id', 'traceId', 'ab_test', 'ad_info', 'watermark_info'
}

def clean_xhs_cookie_list(cookies: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Filters large browser cookie dumps down to essential auth keys."""
    cleaned = []
    for c in cookies:
        name = c.get('name', '')
        if name in XHS_CORE_COOKIES or 'session' in name.lower() or 'token' in name.lower() or 'auth' in name.lower():
            val = c.get('value', '')
            cleaned.append({
                'name': name,
                'value': val,
                'domain': c.get('domain', '.xiaohongshu.com'),
                'path': c.get('path', '/')
            })
    return cleaned

def clean_xhs_api_response(data: Any) -> Any:
    """Recursively removes bloated trackers, multi-resolution image arrays, and noise from XHS responses."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if k.lower() in XHS_NOISE_KEYS:
                continue
            # 特殊处理：图片信息列表中只保留一张原图 URL，剥离 10+ 种不同裁剪尺寸
            if k in ('image_list', 'images', 'image_info_list') and isinstance(v, list):
                simplified_images = []
                for img in v:
                    if isinstance(img, dict):
                        url = img.get('url_default') or img.get('url') or img.get('url_origin') or img.get('original') or img.get('url_pre')
                        simplified_images.append({'url': url, 'width': img.get('width'), 'height': img.get('height')})
                    elif isinstance(img, str):
                        simplified_images.append(img)
                cleaned[k] = simplified_images
                continue
                
            cleaned[k] = clean_xhs_api_response(v)
        return cleaned
    elif isinstance(data, list):
        # 如果是长笔记列表，最多保留前 5 条完整样本，其余统计数量
        if len(data) > 8:
            return [clean_xhs_api_response(item) for item in data[:5]] + [f"... [已折叠剩余 {len(data) - 5} 条数据以节省 Token]"]
        return [clean_xhs_api_response(item) for item in data]
    else:
        return data

def optimize_browser_content(raw_str: str) -> str:
    raw_size = len(raw_str)
    
    # 尝试作为 JSON 解析
    try:
        parsed = json.loads(raw_str)
        if isinstance(parsed, list) and all(isinstance(x, dict) and 'name' in x and 'value' in x for x in parsed[:3]):
            # Cookie 数组
            result = clean_xhs_cookie_list(parsed)
            formatted = json.dumps(result, indent=2, ensure_ascii=False)
            header = f"# === [浏览器 Cookie 鉴权瘦身] 原始: {len(parsed)} 个 -> 精简后: {len(result)} 个核心鉴权 Token ===\n"
            return header + formatted
        else:
            # 常见 API 报文 / 网络抓包
            result = clean_xhs_api_response(parsed)
            formatted = json.dumps(result, indent=2, ensure_ascii=False)
            comp_size = len(formatted)
            ratio = (1 - (comp_size / raw_size)) * 100 if raw_size > 0 else 0
            header = f"# === [小红书/浏览器 API 报文瘦身] 原始: {raw_size} 字符 -> 压缩后: {comp_size} 字符 (节省 {ratio:.1f}%) ===\n"
            return header + formatted
    except Exception:
        # 非 JSON 文本（例如控制台网络文本），进行正则去噪
        lines = raw_str.splitlines()
        filtered = [l for l in lines if not any(k in l for k in ('trace_id', 'beacon', 'pixel', 'hm.baidu.com', 'sensorsdata'))]
        output = "\n".join(filtered)
        return f"# === [浏览器会话日志清洗] 原始: {raw_size} 字符 -> 精简后: {len(output)} 字符 ===\n" + output

def main():
    parser = argparse.ArgumentParser(description="Browser Session & Xiaohongshu (XHS) API Response Optimizer")
    parser.add_argument("path", help="JSON/HAR/Cookie file path or '-' for stdin")
    args = parser.parse_args()

    if args.path == "-":
        raw = sys.stdin.read()
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"Error: {p} not found")
            sys.exit(1)
        raw = p.read_text(encoding="utf-8", errors="replace")

    print(optimize_browser_content(raw))

if __name__ == "__main__":
    main()
