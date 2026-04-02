#!/usr/bin/env python3
"""
explore_wechat.py — WeChat Windows UI Explorer
===============================================
Refactored to use wechat_utils.py for common interactions.
Focuses on UI exploration and tree snapshots.
"""

import sys
import json
import argparse
import datetime
import time
from pathlib import Path
import wechat_utils as utils

def snapshot_tree(ctrl, depth=0, max_depth=5, results=None) -> list:
    """Recursively traverse UIA tree."""
    if results is None:
        results = []
    if depth > max_depth:
        return results

    try:
        node = {
            'depth': depth,
            'class_name': ctrl.class_name(),
            'control_type': ctrl.element_info.control_type,
            'title': ctrl.window_text()[:80],
            'auto_id': ctrl.element_info.automation_id,
            'rect': {
                'left': ctrl.rectangle().left,
                'top': ctrl.rectangle().top,
                'right': ctrl.rectangle().right,
                'bottom': ctrl.rectangle().bottom,
            },
        }
        results.append(node)
    except Exception as e:
        results.append({'depth': depth, 'error': str(e)})
        return results

    try:
        for child in ctrl.children():
            snapshot_tree(child, depth + 1, max_depth, results)
    except Exception:
        pass

    return results


def print_snapshot(nodes: list, indent_char='  '):
    """Format snapshot_tree results."""
    for node in nodes:
        if 'error' in node:
            print(f"{indent_char * node['depth']}[ERROR] {node['error']}")
            continue
        d = node['depth']
        ct = node.get('control_type', '?')
        cn = node.get('class_name', '')
        title = node.get('title', '')
        auto_id = node.get('auto_id', '')
        rect = node.get('rect', {})
        size = f"{rect.get('right',0)-rect.get('left',0)}x{rect.get('bottom',0)-rect.get('top',0)}"
        parts = [f"[{ct}]"]
        if cn:
            parts.append(f"class={cn!r}")
        if title:
            parts.append(f"title={title!r}")
        if auto_id:
            parts.append(f"auto_id={auto_id!r}")
        parts.append(f"size={size}")
        print(f"{indent_char * d}{' '.join(parts)}")


def do_snapshot(win, label='current', max_depth=5):
    """Execute snapshot and save to JSON."""
    print(f'\n[Snapshot] Tree (max_depth={max_depth}, label={label})...')
    nodes = snapshot_tree(win, max_depth=max_depth)
    print_snapshot(nodes)

    ts = datetime.datetime.now().strftime('%H%M%S')
    out_path = utils.DEBUG_DIR / f'snapshot_{label}_{ts}.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    print(f'\n[Snapshot] Saved to: {out_path}')
    return nodes


def explore_nav_sections(win):
    """Explore nav sections and snapshot each view."""
    print('\n=== Exploration: Nav Sections ===')
    toolbar = utils.get_nav_toolbar(win)
    if not toolbar:
        print('[Exploration] Nav toolbar not found.')
        return

    sections = [utils.NAV_CHAT_TITLE, utils.NAV_CONTACTS_TITLE, '收藏', '视频号', '搜一搜']
    for section in sections:
        print(f'\n--- Exploring view: {section!r} ---')
        ok = utils.click_nav_button(toolbar, section)
        if ok:
            time.sleep(0.5)
            do_snapshot(win, label=f'view_{section}', max_depth=4)
        else:
            utils.screenshot_save(f'view_{section}_failed')


def main():
    parser = argparse.ArgumentParser(description='WeChat Windows UI Explorer')
    parser.add_argument('--snapshot', action='store_true', help='Take UI tree snapshot')
    parser.add_argument('--explore', action='store_true', help='Explore nav sections')
    parser.add_argument('--send', metavar='NAME', help='Search friend and send message')
    parser.add_argument('--message', metavar='MSG', default='Hello from explorer!', help='Message content')
    parser.add_argument('--depth', type=int, default=5, help='Snapshot max depth')
    args = parser.parse_args()

    print('=' * 60)
    print('WeChat Windows UI Explorer')
    print('=' * 60)

    win = utils.get_main_window()
    if not win:
        print('Could not find WeChat main window.')
        sys.exit(1)

    if args.snapshot:
        do_snapshot(win, label='main', max_depth=args.depth)
        return

    if args.explore:
        do_snapshot(win, label='initial', max_depth=3)
        explore_nav_sections(win)
        return

    if args.send:
        print(f'\nTarget: {args.send!r} Message: {args.message!r}')
        if utils.open_chat(win, args.send):
            if utils.send_message(win, args.message):
                print(f'\n[Success] Sent message to {args.send!r}.')
            else:
                print(f'\n[Failure] Failed to send message.')
        else:
            print(f'\n[Failure] Could not open chat with {args.send!r}.')
    else:
        # Default behavior: snapshot
        do_snapshot(win, label='default', max_depth=args.depth)


if __name__ == '__main__':
    main()
