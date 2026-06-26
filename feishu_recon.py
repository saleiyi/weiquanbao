#!/usr/bin/env python3
"""飞书页面 DOM 探查 — 输出到文件"""
import sys, os, time, json
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

out = open(r'D:\浏览器下载\weiquanbao\feishu_dom.txt', 'w', encoding='utf-8')

CP = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Default")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r'D:\浏览器下载\weiquanbao\.feishu_profile', headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto("https://www.feishu.cn/messenger", wait_until="domcontentloaded", timeout=30000)
    print("登录后按回车...", flush=True)
    input()
    time.sleep(5)

    # 收集所有类名
    info = page.evaluate("""() => {
        const cls = new Set(), roles = new Set(), btns = [], texts = [];
        document.querySelectorAll('*').forEach(el => {
            const c = el.className;
            if (c && typeof c === 'string') c.split(/\\s+/).forEach(x => { if(x && x.length>2) cls.add(x); });
            const r = el.getAttribute('role');
            if (r) roles.add(r);
            const t = (el.innerText||'').trim().slice(0,50);
            if (el.tagName==='BUTTON' && t) btns.push(t);
            if (el.children.length===0 && t.length>2) texts.push(t);
        });
        return {classes:[...cls].sort(), roles:[...roles].sort(), buttons:btns.slice(0,30), texts:texts.slice(0,50)};
    }""")

    out.write("=== 关键类名 ===\n")
    for kw in ['conversation','chat','message','session','sidebar','list','item','title','name','content','contact','conv']:
        for c in info['classes']:
            if kw in c.lower():
                out.write(f"  .{c}\n")

    out.write(f"\n=== 角色 ===\n")
    for r in info['roles']:
        out.write(f"  role='{r}'\n")

    out.write(f"\n=== 按钮 ===\n")
    for b in info['buttons']:
        out.write(f"  '{b}'\n")

    out.write(f"\n=== 纯文本 (前50) ===\n")
    for t in info['texts']:
        out.write(f"  '{t}'\n")

    # 看看会话列表区域
    conv_html = page.evaluate("""() => {
        // 找可能包含会话列表的元素
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const txt = (el.innerText||'').trim();
            if (txt.includes('搜索') && txt.includes('消息') && el.children.length > 3) {
                return el.innerHTML.slice(0, 2000);
            }
        }
        return 'not found';
    }""")
    out.write(f"\n=== 会话列表区域 HTML ===\n{conv_html}\n")

    out.close()
    print("完成 -> feishu_dom.txt", flush=True)
    input("按回车退出...")
    ctx.close()
