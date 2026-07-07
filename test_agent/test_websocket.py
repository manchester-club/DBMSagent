#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 WebSocket 流式输出"""

import asyncio
import websockets
import json

async def test_websocket():
    """测试 WebSocket 连接和流式输出"""
    print("=" * 60)
    print("测试 WebSocket 流式输出")
    print("=" * 60)
    
    uri = "ws://localhost:8000/ws/stream"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("\n✅ WebSocket 连接成功")
            
            # 发送初始消息（指定 agent_id）
            initial_message = {
                "agent_id": "coverage_multi_agent",
                "message": "测试：查询函数 date_pli 的代码上下文",
                "thread_id": "test_thread_001"
            }
            
            print(f"\n📤 发送消息: {initial_message['message']}")
            await websocket.send(json.dumps(initial_message))
            
            # 接收流式响应
            print("\n📥 接收响应:")
            print("-" * 60)
            
            event_count = 0
            received_types = set()
            
            try:
                async for message in websocket:
                    data = json.loads(message)
                    event_type = data.get("type", "unknown")
                    received_types.add(event_type)
                    event_count += 1
                    
                    if event_type == "dispatch":
                        print(f"[DISPATCH] {data.get('content', '')}")
                    elif event_type == "think":
                        agent = data.get("agent", "AGENT")
                        content = data.get("content", "")[:100]  # 只显示前100个字符
                        print(f"[{agent}] {content}...")
                    elif event_type == "tool":
                        agent = data.get("agent", "AGENT")
                        tool_name = data.get("tool_name", "unknown")
                        status = data.get("status", "")
                        args = data.get("args", {})
                        result = data.get("result", "")
                        
                        print(f"[{agent}] 🔧 {tool_name} ({status})")
                        if args:
                            print(f"   参数: {json.dumps(args, ensure_ascii=False)[:100]}...")
                        if result:
                            result_preview = str(result)[:100] if len(str(result)) > 100 else str(result)
                            print(f"   结果: {result_preview}...")
                    elif event_type == "error":
                        print(f"❌ 错误: {data.get('message', '')}")
                        break
                    elif event_type == "done":
                        print("\n✅ 执行完成")
                        break
                    
                    # 限制接收事件数量，避免无限等待
                    if event_count > 50:
                        print("\n⚠️  已接收 50 个事件，停止接收")
                        break
                
                print("-" * 60)
                print(f"\n📊 统计:")
                print(f"   总事件数: {event_count}")
                print(f"   事件类型: {', '.join(sorted(received_types))}")
                print("\n✅ WebSocket 测试成功！")
                
            except websockets.exceptions.ConnectionClosed:
                print("\n⚠️  WebSocket 连接已关闭")
            except Exception as e:
                print(f"\n❌ 接收消息时出错: {e}")
                
    except websockets.exceptions.InvalidURI:
        print("\n❌ 无效的 WebSocket URI")
    except ConnectionRefusedError:
        print("\n❌ 无法连接到后端服务")
        print("   请确保后端服务正在运行：")
        print("   cd backend && python3 main.py")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
