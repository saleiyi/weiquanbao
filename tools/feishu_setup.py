#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书一键配置向导
引导用户完成飞书应用创建和授权
"""
import os, sys, json, webbrowser, time, subprocess, shutil

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".colleague-skill", "feishu_config.json")


def find_npx():
    for name in ["npx.cmd", "npx"]:
        path = shutil.which(name)
        if path:
            return path
    for p in [r"D:\Program Files\nodejs\npx.cmd", r"C:\Program Files\nodejs\npx.cmd"]:
        if os.path.exists(p):
            return p
    return None


def run_lark_cli(args, timeout=60):
    npx = find_npx()
    if not npx:
        return None
    cmd = [npx, "@larksuite/cli@latest"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True)
        if result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout}
        return {"returncode": result.returncode, "stderr": result.stderr}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("  飞书聊天记录导出 - 一键配置向导")
    print("=" * 60)

    # 检查是否已配置
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.loads(open(CONFIG_PATH, encoding='utf-8').read())
            if cfg.get('app_id') and cfg.get('app_secret'):
                print(f"\n✅ 已有配置: {CONFIG_PATH}")
                print(f"   App ID: {cfg['app_id'][:8]}...")
                choice = input("\n是否重新配置？(y/N): ").strip().lower()
                if choice != 'y':
                    print("\n跳过配置，直接测试登录...")
                    test_login()
                    return
        except Exception:
            pass

    print("""
📋 配置步骤：

  第1步：创建飞书应用（只需一次）
  第2步：获取 App ID 和 App Secret
  第3步：配置 lark-cli
  第4步：扫码登录

""")

    # 第1步：打开飞书开放平台
    print("━" * 40)
    print("第1步：创建飞书应用")
    print("━" * 40)
    print("""
请在浏览器中完成以下操作：

1. 打开 https://open.feishu.cn/app
2. 点击「创建企业自建应用」
3. 填写应用名称（如：维权宝备份工具）
4. 创建完成后，进入应用详情页
5. 在「凭证与基础信息」页面找到：
   - App ID
   - App Secret
""")
    input("完成上述操作后，按回车继续...")

    # 第2步：输入凭证
    print("\n" + "━" * 40)
    print("第2步：输入应用凭证")
    print("━" * 40)

    app_id = input("\n请输入 App ID: ").strip()
    app_secret = input("请输入 App Secret: ").strip()

    if not app_id or not app_secret:
        print("❌ App ID 和 App Secret 不能为空")
        return

    # 保存配置
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    config = {"app_id": app_id, "app_secret": app_secret}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 配置已保存到: {CONFIG_PATH}")

    # 第3步：配置 lark-cli
    print("\n" + "━" * 40)
    print("第3步：配置 lark-cli")
    print("━" * 40)
    print("\n正在配置 lark-cli...")

    npx = find_npx()
    if npx:
        # 设置 app credentials
        result = run_lark_cli(["config", "set", "--app-id", app_id, "--app-secret", app_secret])
        if result and "error" not in result:
            print("✅ lark-cli 配置成功")
        else:
            print("⚠️  lark-cli 配置可能需要手动完成")
    else:
        print("⚠️  npx 未找到，请确保已安装 Node.js")

    # 第4步：登录
    print("\n" + "━" * 40)
    print("第4步：扫码登录")
    print("━" * 40)
    print("\n即将打开浏览器进行飞书授权登录...")
    input("按回车继续...")

    test_login()


def test_login():
    """测试登录状态"""
    print("\n正在登录飞书...")
    print("请在弹出的浏览器中扫码授权\n")

    result = run_lark_cli(["auth", "login", "--recommend"], timeout=120)

    if result and "error" not in result:
        print("\n✅ 登录成功！")
        print("\n现在可以重启维权宝使用飞书功能了：")
        print("  python main.py")
    else:
        print("\n❌ 登录失败，请重试")
        print("   或手动运行: npx @larksuite/cli@latest auth login --recommend")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消配置")
    except Exception as e:
        print(f"\n❌ 配置出错: {e}")
        import traceback
        traceback.print_exc()
