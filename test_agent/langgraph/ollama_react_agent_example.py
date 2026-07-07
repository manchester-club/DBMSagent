#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph create_agent 示例 - 使用本地 Ollama

这个示例展示了如何使用 LangChain 的 create_agent 预构建智能体
与本地安装的 Ollama 模型一起工作。
"""

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

# 定义工具函数
@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气信息。
    
    Args:
        city: 城市名称，例如 '北京'、'上海'、'San Francisco'
    
    Returns:
        该城市的天气描述
    """
    return f"{city} 的天气总是阳光明媚！"


def main():
    """主函数"""
    print("=" * 70)
    print("🤖 LangGraph ReAct Agent 示例 - 使用 Ollama")
    print("=" * 70)
    
    # 创建 Ollama 模型实例
    # 你可以根据本地安装的模型修改模型名称
    # 常见模型: "qwen2.5:7b", "llama3", "llama2", "mistral" 等
    try:
        # 尝试从配置文件获取默认模型
        try:
            from ollama_agent_config import get_default_model
            model_name = get_default_model()
            print(f"📦 使用模型: {model_name}")
        except ImportError:
            model_name = "qwen2.5:7b"  # 默认模型
            print(f"📦 使用默认模型: {model_name}")
        
        # 创建 ChatOllama 实例
        llm = ChatOllama(
            model=model_name,
            temperature=0.7,
        )
        
        # 创建 ReAct Agent
        # create_agent 会自动处理工具调用和推理循环
        agent = create_agent(
            model=llm,  # 使用 ChatOllama 实例
            tools=[get_weather],  # 工具列表
            system_prompt="你是一个有用的助手，可以帮助用户查询天气信息。使用中文回复。"  # 系统提示（参数名从 prompt 改为 system_prompt）
        )
        
        print("\n✅ Agent 创建成功！")
        print("\n" + "-" * 70)
        
        # 运行示例查询
        test_queries = [
            "旧金山的天气怎么样？",
            "what is the weather in sf",
            "北京天气如何？"
        ]
        
        for query in test_queries:
            print(f"\n👤 用户: {query}")
            print("-" * 70)
            
            # 调用 agent
            result = agent.invoke(
                {"messages": [{"role": "user", "content": query}]}
            )
            
            # 显示结果
            print("🤖 智能体回复:")
            # 提取最后一条消息
            if "messages" in result:
                last_message = result["messages"][-1]
                if hasattr(last_message, 'content'):
                    print(last_message.content)
                else:
                    print(str(last_message))
            else:
                print(result)
            
            print("\n" + "=" * 70)
        
        print("\n💡 提示: 你可以修改代码中的查询来测试不同的输入")
        
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        print("\n请确保:")
        print("1. Ollama 已安装并运行")
        print("2. 已安装所需依赖: pip install langgraph langchain-ollama")
        print("3. 模型名称正确（使用 'ollama list' 查看可用模型）")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
