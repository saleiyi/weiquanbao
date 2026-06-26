#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - Web API (多平台版)
"""
import os, sys, logging, json, mimetypes
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import ai_analyzer
from platforms import discover_platforms, get_platforms, get_available_platforms
from scheduler import get_sync_state, setup_scheduler

logger = logging.getLogger(__name__)

app = FastAPI(title="维权宝 - 聊天记录导出工具", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    # 静态文件不缓存，开发阶段方便调试
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

# Scheduler (lazy)
_scheduler = None

# Platform instances (lazy loaded)
_platforms = {}


@app.on_event("startup")
async def startup():
    global _scheduler
    # 发现所有平台
    global _platforms
    _platforms = discover_platforms()
    logger.info(f"发现 {len(_platforms)} 个平台: {list(_platforms.keys())}")

    # 初始化 AI 分析引擎
    ai_analyzer.configure(
        api_key=config.AI_API_KEY,
        api_base=config.AI_API_BASE,
        model=config.AI_MODEL,
    )
    logger.info(f"AI 分析引擎: {'已启用' if ai_analyzer.is_ai_available() else '规则模式（未配置 API Key）'}")

    _scheduler = setup_scheduler(app)
    _scheduler.start()
    logger.info("Scheduler started")


@app.on_event("shutdown")
async def shutdown():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()


# --- Static files ---

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h1>维权宝</h1><p>前端页面未找到</p>")


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- API: 平台管理 ---

@app.get("/api/platforms")
async def api_platforms():
    """获取所有平台状态"""
    result = {}
    for name, p in _platforms.items():
        result[name] = {
            "name": name,
            "display_name": p.display_name,
            "available": p.is_available(),
        }
    return {"platforms": result}


@app.post("/api/platforms/{name}/discover")
async def api_platform_discover(name: str):
    """发现并解密指定平台的数据"""
    p = _platforms.get(name)
    if not p:
        raise HTTPException(status_code=404, detail=f"Platform '{name}' not found")
    try:
        success = p.discover()
        return {"platform": name, "success": success}
    except Exception as e:
        logger.error(f"Discover {name} failed: {e}")
        return {"platform": name, "success": False, "error": str(e)}


@app.get("/api/platforms/{name}/conversations")
async def api_platform_conversations(
    name: str,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    keyword: str = Query(None),
):
    """获取指定平台的会话列表"""
    p = _platforms.get(name)
    if not p:
        raise HTTPException(status_code=404, detail=f"Platform '{name}' not found")

    if not p.is_available():
        return {"platform": name, "total": 0, "conversations": [], "error": "平台不可用"}

    try:
        convs = p.get_conversations(keyword=keyword)
    except Exception as e:
        logger.error(f"获取 {name} 会话失败: {e}")
        return {"platform": name, "total": 0, "conversations": [], "error": str(e)}

    total = len(convs)
    convs = convs[offset:offset + limit]

    return {
        "platform": name,
        "total": total,
        "conversations": [
            {
                "cid": c.cid,
                "title": c.title,
                "type": c.type,
                "platform": c.platform,
                "member_count": c.member_count,
                "unread_count": c.unread_count,
                "is_top": c.is_top,
                "last_modify": int(c.last_time * 1000) if c.last_time else None,
            }
            for c in convs
        ],
    }


@app.get("/api/platforms/{name}/conversations/{cid}/messages")
async def api_platform_messages(
    name: str,
    cid: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """获取指定平台某个会话的消息"""
    p = _platforms.get(name)
    if not p:
        raise HTTPException(status_code=404, detail=f"Platform '{name}' not found")

    try:
        msgs = p.get_messages(cid, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"获取 {name}/{cid} 消息失败: {e}")
        return {"platform": name, "cid": cid, "total": 0, "messages": [], "error": str(e)}

    return {
        "platform": name,
        "cid": cid,
        "total": len(msgs),
        "messages": [
            {
                "mid": m.mid,
                "sender_name": m.sender_name,
                "sender_id": m.sender_id,
                "content": m.content,
                "msg_type": m.msg_type,
                "timestamp": int(m.timestamp * 1000) if m.timestamp else None,
            }
            for m in msgs
        ],
    }


@app.get("/api/platforms/{name}/search")
async def api_platform_search(
    name: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """搜索指定平台的消息"""
    p = _platforms.get(name)
    if not p:
        raise HTTPException(status_code=404, detail=f"Platform '{name}' not found")

    try:
        msgs = p.search_messages(q, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"搜索 {name} 失败: {e}")
        return {"platform": name, "query": q, "total": 0, "messages": [], "error": str(e)}

    return {
        "platform": name,
        "query": q,
        "total": len(msgs),
        "messages": [
            {
                "mid": m.mid,
                "cid": m.cid,
                "sender_name": m.sender_name,
                "content": m.content,
                "msg_type": m.msg_type,
                "timestamp": int(m.timestamp * 1000) if m.timestamp else None,
            }
            for m in msgs
        ],
    }


@app.get("/api/platforms/{name}/stats")
async def api_platform_stats(name: str):
    p = _platforms.get(name)
    if not p:
        raise HTTPException(status_code=404, detail=f"Platform '{name}' not found")
    try:
        return p.get_stats()
    except Exception as e:
        return {"error": str(e)}


# --- API: 跨平台搜索 ---

@app.get("/api/search/all")
async def api_search_all(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """跨平台搜索所有消息"""
    results = []
    for name, p in _platforms.items():
        if p.is_available():
            try:
                msgs = p.search_messages(q, limit=limit)
                for m in msgs:
                    results.append({
                        "platform": name,
                        "mid": m.mid,
                        "cid": m.cid,
                        "sender_name": m.sender_name,
                        "content": m.content[:200],
                        "timestamp": int(m.timestamp * 1000) if m.timestamp else None,
                    })
            except Exception as e:
                logger.warning(f"跨平台搜索 {name} 失败: {e}")
    return {"query": q, "total": len(results), "messages": results}


# --- API: 导出 ---

@app.post("/api/export")
async def api_export(body: dict):
    """导出选中的会话为 JSON + 附件"""
    platform = body.get("platform")
    cids = body.get("cids", [])
    since_time = body.get("since_time")

    if not cids:
        raise HTTPException(status_code=400, detail="No conversations selected")

    try:
        if platform == "dingtalk":
            from dt_exporter import export_by_cids
            export_dir = export_by_cids(cids, since_time=since_time)
        elif platform == "wechat":
            from wechat_exporter import export_by_cids
            wechat_platform = _platforms.get("wechat")
            wxid = getattr(wechat_platform, '_wxid', None)
            decrypted_dir = getattr(wechat_platform, '_decrypted_dir', None)
            export_dir = export_by_cids(cids, wxid=wxid, decrypted_dir=decrypted_dir)
        else:
            # 通用导出（飞书、QQ 等）
            p = _platforms.get(platform)
            if not p:
                raise HTTPException(status_code=404, detail=f"Platform '{platform}' not found")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = os.path.join(config.EXPORT_DIR, f"{platform}_export_{timestamp}")
            os.makedirs(export_dir, exist_ok=True)

            export_data = {
                "export_time": datetime.now().isoformat(),
                "platform": platform,
                "total_conversations": len(cids),
                "conversations": [],
            }

            total_msgs = 0
            for cid in cids:
                try:
                    convs = p.get_conversations()
                    title = cid
                    conv_type = "single"
                    for c in convs:
                        if c.cid == cid:
                            title = c.title
                            conv_type = c.type
                            break

                    msgs = p.get_messages(cid, limit=10000)
                    export_data["conversations"].append({
                        "conversation_id": cid,
                        "title": title,
                        "type": conv_type,
                        "message_count": len(msgs),
                        "messages": [
                            {
                                "mid": m.mid,
                                "sender_name": m.sender_name,
                                "sender_id": m.sender_id,
                                "content": m.content,
                                "msg_type": m.msg_type,
                                "timestamp": int(m.timestamp * 1000) if m.timestamp else None,
                            }
                            for m in msgs
                        ],
                    })
                    total_msgs += len(msgs)
                except Exception as e:
                    logger.warning(f"导出会话 {cid} 失败: {e}")

            json_path = os.path.join(export_dir, "export.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            logger.info(f"{platform} 导出完成: {len(cids)} 会话, {total_msgs} 条消息")

        return {
            "status": "success",
            "platform": platform,
            "count": len(cids),
            "export_dir": export_dir,
        }
    except Exception as e:
        logger.error(f"导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


@app.post("/api/import")
async def api_import(body: dict):
    """导入外部聊天记录文件"""
    platform = body.get("platform", "")
    file_path = body.get("file_path", "")

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"文件不存在: {file_path}")

    # 自动检测平台
    if not platform:
        ext = file_path.lower().rsplit('.', 1)[-1] if '.' in file_path else ''
        if ext == 'json':
            # 检查是否是 qq-chat-exporter 格式
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if 'chatInfo' in data or 'messages' in data:
                    platform = 'qq'
            except Exception:
                pass
        elif ext == 'txt':
            # 检查是否是 QQ 导出格式
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    head = f.read(500)
                if '消息记录' in head or '消息对象' in head:
                    platform = 'qq'
                else:
                    platform = 'wechat'
            except Exception:
                platform = 'wechat'
        elif ext == 'csv':
            platform = 'wechat'

    if not platform:
        raise HTTPException(status_code=400, detail="无法自动检测平台，请手动指定")

    p = _platforms.get(platform)
    if not p:
        raise HTTPException(status_code=404, detail=f"平台 '{platform}' 不存在")

    if hasattr(p, 'import_exported_file'):
        try:
            success = p.import_exported_file(file_path)
            return {"platform": platform, "success": success, "file": file_path}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"导入失败: {e}")
    else:
        raise HTTPException(status_code=400, detail=f"平台 '{platform}' 不支持文件导入")


@app.post("/api/ai/analyze")
async def api_ai_analyze(body: dict):
    """AI 维权分析（结构化结果）"""
    conversation = body.get("conversation", "")
    messages = body.get("messages", "")
    platform = body.get("platform", "")

    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    result = ai_analyzer.analyze(conversation, messages, platform)
    return {"result": result}


@app.get("/api/ai/config")
async def api_ai_config():
    """获取 AI 配置"""
    return {
        "available": ai_analyzer.is_ai_available(),
        "api_base": ai_analyzer.AI_API_BASE,
        "model": ai_analyzer.AI_MODEL,
        "has_key": bool(ai_analyzer.AI_API_KEY),
    }


@app.post("/api/ai/config")
async def api_ai_config_update(body: dict):
    """更新 AI 配置"""
    api_key = body.get("api_key", "")
    api_base = body.get("api_base", "")
    model = body.get("model", "")

    ai_analyzer.configure(api_key=api_key, api_base=api_base, model=model)

    return {
        "available": ai_analyzer.is_ai_available(),
        "api_base": ai_analyzer.AI_API_BASE,
        "model": ai_analyzer.AI_MODEL,
        "has_key": bool(ai_analyzer.AI_API_KEY),
    }


@app.get("/api/export/list")
async def api_export_list():
    """列出所有导出目录"""
    exports = []
    export_base = config.EXPORT_DIR
    if os.path.isdir(export_base):
        for name in sorted(os.listdir(export_base), reverse=True):
            full = os.path.join(export_base, name)
            if os.path.isdir(full):
                json_path = os.path.join(full, "export.json")
                has_json = os.path.exists(json_path)
                size = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, files in os.walk(full)
                    for f in files
                )
                exports.append({
                    "name": name,
                    "path": full,
                    "has_json": has_json,
                    "size": size,
                    "size_str": _format_size(size),
                })
    return {"exports": exports}


@app.get("/api/export/{name}/download")
async def api_export_download(name: str):
    """下载导出的 JSON 文件"""
    json_path = os.path.join(config.EXPORT_DIR, name, "export.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(json_path, filename=f"{name}.json", media_type="application/json")


@app.get("/api/export/{name}/json")
async def api_export_json(name: str):
    """读取导出的 JSON 内容"""
    json_path = os.path.join(config.EXPORT_DIR, name, "export.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Export not found")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")


# --- API: 附件服务 ---

@app.get("/api/attachments/{path:path}")
async def api_attachments(path: str):
    """提供本地附件文件（图片、音频、文件等）"""
    # 附件路径基于钉钉数据目录
    data_dir = config.DINGTALK_DATA_DIR
    if not data_dir:
        raise HTTPException(status_code=404, detail="数据目录未配置")

    file_path = os.path.join(data_dir, path)
    # 安全检查：防止路径穿越
    real_path = os.path.realpath(file_path)
    real_data_dir = os.path.realpath(data_dir)
    if not real_path.startswith(real_data_dir):
        raise HTTPException(status_code=403, detail="禁止访问")

    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 推断 MIME 类型
    mime_type, _ = mimetypes.guess_type(real_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(real_path, media_type=mime_type)


# --- API: 旧版兼容接口（保留钉钉直接访问） ---

@app.get("/api/conversations")
async def api_conversations_legacy(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    keyword: str = Query(None),
):
    """兼容旧版 - 默认用钉钉"""
    p = _platforms.get("dingtalk")
    if not p:
        raise HTTPException(status_code=404, detail="DingTalk platform not loaded")

    try:
        convs = p.get_conversations(keyword=keyword)
    except Exception as e:
        return {"total": 0, "conversations": [], "error": str(e)}

    total = len(convs)
    convs = convs[offset:offset + limit]

    return {
        "total": total,
        "conversations": [
            {
                "cid": c.cid,
                "title": c.title,
                "type": c.type,
                "member_count": c.member_count,
                "unread_count": c.unread_count,
                "is_top": c.is_top,
                "last_modify": int(c.last_time * 1000) if c.last_time else None,
            }
            for c in convs
        ],
    }


@app.get("/api/config")
async def api_config():
    return {
        "user_uid": config.USER_UID,
        "platforms": list(_platforms.keys()),
        "data_dir": config.DATA_DIR,
        "export_dir": config.EXPORT_DIR,
    }


@app.get("/api/sync/status")
async def api_sync_status():
    return get_sync_state()


@app.post("/api/sync/trigger")
async def api_sync_trigger(full: bool = Query(False)):
    import threading
    from scheduler import do_sync
    state = get_sync_state()
    if state.get("is_syncing"):
        raise HTTPException(status_code=409, detail="Sync already in progress")

    thread = threading.Thread(target=do_sync, kwargs={"full": full}, daemon=True)
    thread.start()
    return {"status": "started", "full": full}


def _format_size(size):
    """Format bytes to human-readable size."""
    if not size:
        return "0B"
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
