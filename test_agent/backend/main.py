#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI 后端服务器
提供 REST API 和 WebSocket 接口
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import asyncio
import time
import time

from agents.agent_manager import AgentManager

app = FastAPI(title="LangGraph 智能体 API")

# CORS 配置（允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite 和 React 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化智能体管理器
agent_manager = AgentManager()


# ============================================================================
# 数据模型
# ============================================================================

class ChatRequest(BaseModel):
    agent_id: str
    message: str
    thread_id: Optional[str] = None


class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    tools: List[str]


# ============================================================================
# REST API
# ============================================================================

@app.get("/")
async def root():
    """根路径"""
    return {"message": "LangGraph 智能体 API", "version": "1.0.0"}


@app.get("/api/agents", response_model=List[AgentInfo])
async def list_agents():
    """获取所有可用智能体"""
    agents = agent_manager.list_agents()
    return agents


@app.get("/api/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    """获取特定智能体的信息"""
    agent = agent_manager.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")
    
    return {
        "id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "tools": agent.tools
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """非流式聊天接口（用于测试）"""
    try:
        messages = []
        async for event in agent_manager.stream_chat(
            request.agent_id,
            request.message,
            request.thread_id
        ):
            messages.append(event)
            if event.get("type") == "done":
                break
        
        return {"events": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket API (流式输出)
# ============================================================================

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """WebSocket 流式输出接口（支持连续交互）"""
    await websocket.accept()
    
    # 存储当前会话信息
    current_agent_id = None
    current_thread_id = None
    
    try:
        # 循环接收消息，保持连接打开
        while True:
            try:
                # 接收消息（包含 agent_id 和 message）
                data = await websocket.receive_json()
                agent_id = data.get("agent_id")
                message = data.get("message")
                thread_id = data.get("thread_id")
                
                # 如果提供了 agent_id，更新当前智能体
                if agent_id:
                    current_agent_id = agent_id
                    # 验证智能体是否存在
                    agent = agent_manager.get_agent(agent_id)
                    if agent is None:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"智能体 {agent_id} 不存在"
                        })
                        continue
                    # 初始化智能体
                    agent.initialize()
                
                # 如果没有当前智能体，返回错误
                if not current_agent_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "请先指定 agent_id"
                    })
                    continue
                
                # 如果没有消息，跳过
                if not message:
                    continue
                
                # 使用当前或新的 thread_id
                if thread_id:
                    current_thread_id = thread_id
                elif not current_thread_id:
                    current_thread_id = f"thread_{int(time.time() * 1000)}"
                
                # 流式执行并发送事件
                async for event in agent_manager.stream_chat(
                    current_agent_id, 
                    message, 
                    current_thread_id
                ):
                    try:
                        await websocket.send_json(event)
                        
                        # 如果遇到错误，继续处理下一条消息
                        if event.get("type") == "error":
                            break
                        # done 事件后继续等待下一条消息
                        if event.get("type") == "done":
                            break
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"发送事件失败: {str(e)}"
                        })
                        break
                        
            except WebSocketDisconnect:
                print("客户端断开连接")
                break
            except Exception as e:
                print(f"处理消息错误: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"处理消息失败: {str(e)}"
                })
                # 继续等待下一条消息，不关闭连接
        
    except WebSocketDisconnect:
        print("客户端断开连接")
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    # 使用 reload=False 避免警告，或使用 import string
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
