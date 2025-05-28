#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
from typing import Dict, List, Optional


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file="config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "connections": {},
            "last_connection": "",
            "window_settings": {
                "width": 1200,
                "height": 800,
                "maximized": False
            },
            "parse_settings": {
                "sql_types": ["INSERT", "UPDATE", "DELETE"],
                "only_dml": True,
                "flashback": False,
                "no_pk": False,
                "stop_never": False,
                "back_interval": 1.0
            }
        }
    
    def save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            raise Exception(f"保存配置文件失败: {str(e)}")
    
    def add_connection(self, name: str, connection_info: Dict):
        """
        添加数据库连接配置
        
        Args:
            name: 连接名称
            connection_info: 连接信息字典
        """
        if "connections" not in self.config:
            self.config["connections"] = {}
        
        self.config["connections"][name] = {
            "host": connection_info.get("host", "127.0.0.1"),
            "port": connection_info.get("port", 3306),
            "user": connection_info.get("user", "root"),
            "password": connection_info.get("password", ""),
            "charset": connection_info.get("charset", "utf8")
        }
        self.save_config()
    
    def remove_connection(self, name: str):
        """
        删除数据库连接配置
        
        Args:
            name: 连接名称
        """
        if "connections" in self.config and name in self.config["connections"]:
            del self.config["connections"][name]
            if self.config.get("last_connection") == name:
                self.config["last_connection"] = ""
            self.save_config()
    
    def get_connection(self, name: str) -> Optional[Dict]:
        """
        获取数据库连接配置
        
        Args:
            name: 连接名称
            
        Returns:
            连接配置字典或None
        """
        return self.config.get("connections", {}).get(name)
    
    def get_all_connections(self) -> Dict:
        """获取所有数据库连接配置"""
        return self.config.get("connections", {})
    
    def set_last_connection(self, name: str):
        """
        设置最后使用的连接
        
        Args:
            name: 连接名称
        """
        self.config["last_connection"] = name
        self.save_config()
    
    def get_last_connection(self) -> str:
        """获取最后使用的连接名称"""
        return self.config.get("last_connection", "")
    
    def set_window_settings(self, width: int, height: int, maximized: bool = False):
        """
        设置窗口配置
        
        Args:
            width: 窗口宽度
            height: 窗口高度
            maximized: 是否最大化
        """
        if "window_settings" not in self.config:
            self.config["window_settings"] = {}
        
        self.config["window_settings"].update({
            "width": width,
            "height": height,
            "maximized": maximized
        })
        self.save_config()
    
    def get_window_settings(self) -> Dict:
        """获取窗口配置"""
        return self.config.get("window_settings", {
            "width": 1200,
            "height": 800,
            "maximized": False
        })
    
    def set_parse_settings(self, settings: Dict):
        """
        设置解析配置
        
        Args:
            settings: 解析配置字典
        """
        if "parse_settings" not in self.config:
            self.config["parse_settings"] = {}
        
        self.config["parse_settings"].update(settings)
        self.save_config()
    
    def get_parse_settings(self) -> Dict:
        """获取解析配置"""
        return self.config.get("parse_settings", {
            "sql_types": ["INSERT", "UPDATE", "DELETE"],
            "only_dml": True,
            "flashback": False,
            "no_pk": False,
            "stop_never": False,
            "back_interval": 1.0
        })
    
    def update_connection(self, name: str, connection_info: Dict):
        """
        更新数据库连接配置
        
        Args:
            name: 连接名称
            connection_info: 新的连接信息
        """
        if "connections" not in self.config:
            self.config["connections"] = {}
        
        if name in self.config["connections"]:
            self.config["connections"][name].update(connection_info)
            self.save_config()
    
    def connection_exists(self, name: str) -> bool:
        """
        检查连接是否存在
        
        Args:
            name: 连接名称
            
        Returns:
            是否存在
        """
        return name in self.config.get("connections", {})
    
    def get_connection_names(self) -> List[str]:
        """获取所有连接名称列表"""
        return list(self.config.get("connections", {}).keys())
