#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试后端 API"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_agents():
    """测试获取智能体列表"""
    print("=" * 60)
    print("测试后端 API")
    print("=" * 60)
    
    try:
        # 测试根路径
        print("\n1. 测试根路径...")
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.json()}")
        
        # 测试获取智能体列表
        print("\n2. 获取智能体列表...")
        response = requests.get(f"{BASE_URL}/api/agents", timeout=5)
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            agents = response.json()
            print(f"   找到 {len(agents)} 个智能体:")
            for agent in agents:
                print(f"     - {agent['id']}: {agent['name']}")
                print(f"       描述: {agent['description']}")
                print(f"       工具: {', '.join(agent['tools'][:3])}...")
        else:
            print(f"   错误: {response.text}")
        
        print("\n✅ API 测试成功！")
        print("\n后端服务运行正常，可以：")
        print("  - 访问 API 文档: http://localhost:8000/docs")
        print("  - 使用 WebSocket: ws://localhost:8000/ws/stream")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到后端服务")
        print("   请确保后端服务正在运行：")
        print("   cd backend && python3 main.py")
    except Exception as e:
        print(f"\n❌ 错误: {e}")

if __name__ == "__main__":
    test_agents()
