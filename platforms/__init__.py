#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - 平台注册与自动发现
"""
import os, sys, importlib, pkgutil, logging

logger = logging.getLogger(__name__)

_platforms = {}  # name -> instance


def discover_platforms():
    """扫描 platforms 目录，自动注册所有平台"""
    global _platforms
    pkg_dir = os.path.dirname(__file__)

    for importer, modname, ispkg in pkgutil.iter_modules([pkg_dir]):
        if modname.startswith('_') or modname == 'base':
            continue
        try:
            module = importlib.import_module(f'platforms.{modname}')
            if hasattr(module, 'get_platform'):
                inst = module.get_platform()
                _platforms[inst.name] = inst
                logger.info(f"已加载平台: {inst.display_name} ({inst.name})")
        except Exception as e:
            logger.warning(f"加载平台 {modname} 失败: {e}")

    return _platforms


def get_platforms():
    """获取所有已注册的平台实例"""
    return dict(_platforms)


def get_platform(name):
    """按名称获取平台实例"""
    return _platforms.get(name)


def get_available_platforms():
    """获取本机可用的平台（安装了且有数据）"""
    return {name: p for name, p in _platforms.items() if p.is_available()}
