#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查后端导入是否有错误"""

import sys
from pathlib import Path

# 添加路径
langgraph_path = Path(__file__).parent.parent / "langgraph"
sys.path.insert(0, str(langgraph_path))

print("检查后端导入...")

try:
    print("1. 检查 agents.agent_manager...")
    from agents.agent_manager import AgentManager
    print("   ✅ AgentManager 导入成功")
    
    print("2. 检查 main...")
    import main
    print("   ✅ main.py 导入成功")
    
    print("3. 测试智能体管理器...")
    manager = AgentManager()
    agents = manager.list_agents()
    print(f"   ✅ 找到 {len(agents)} 个智能体:")
    for agent in agents:
        print(f"      - {agent['id']}: {agent['name']}")
    
    print("\n✅ 所有检查通过！")
    
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
