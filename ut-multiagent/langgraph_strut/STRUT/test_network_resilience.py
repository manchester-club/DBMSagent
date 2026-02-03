#!/usr/bin/env python3
"""
网络容错机制测试脚本

用于验证 model.py 中的重试机制是否正常工作
"""

import sys
import time
from unittest.mock import patch, MagicMock
from model import access_model

def test_successful_call():
    """测试：首次调用成功"""
    print("\n" + "="*60)
    print("测试1: 首次调用成功")
    print("="*60)
    
    # 模拟成功的响应
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "测试响应"
    
    with patch('model.get_gemini') as mock_get_gemini:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_gemini.return_value = mock_client
        
        result = access_model("测试提示词", "gemini", max_retries=3)
        
        assert result == "测试响应", "响应内容不匹配"
        assert mock_client.chat.completions.create.call_count == 1, "应该只调用1次"
        
    print("✅ 测试通过：首次调用成功")


def test_retry_once_then_success():
    """测试：第1次失败，第2次成功"""
    print("\n" + "="*60)
    print("测试2: 第1次失败，第2次成功")
    print("="*60)
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "测试响应"
    
    with patch('model.get_gemini') as mock_get_gemini:
        mock_client = MagicMock()
        # 第1次调用失败，第2次成功
        mock_client.chat.completions.create.side_effect = [
            ConnectionError("网络连接失败"),
            mock_response
        ]
        mock_get_gemini.return_value = mock_client
        
        # 加速测试：减少重试延迟
        result = access_model("测试提示词", "gemini", max_retries=3, retry_delay=0.1)
        
        assert result == "测试响应", "响应内容不匹配"
        assert mock_client.chat.completions.create.call_count == 2, "应该调用2次"
        
    print("✅ 测试通过：第1次失败，第2次成功")


def test_all_retries_fail():
    """测试：所有重试都失败"""
    print("\n" + "="*60)
    print("测试3: 所有重试都失败")
    print("="*60)
    
    with patch('model.get_gemini') as mock_get_gemini:
        mock_client = MagicMock()
        # 所有调用都失败
        mock_client.chat.completions.create.side_effect = ConnectionError("网络连接失败")
        mock_get_gemini.return_value = mock_client
        
        try:
            # 加速测试：减少重试次数和延迟
            result = access_model("测试提示词", "gemini", max_retries=2, retry_delay=0.1)
            assert False, "应该抛出异常"
        except Exception as e:
            assert "LLM 调用失败" in str(e), f"异常消息不正确: {e}"
            assert mock_client.chat.completions.create.call_count == 2, "应该调用2次"
    
    print("✅ 测试通过：所有重试都失败，正确抛出异常")


def test_empty_response():
    """测试：检测空响应"""
    print("\n" + "="*60)
    print("测试4: 检测空响应并重试")
    print("="*60)
    
    with patch('model.get_gemini') as mock_get_gemini:
        mock_client = MagicMock()
        
        # 第1次返回空响应，第2次返回正常响应
        mock_response_empty = MagicMock()
        mock_response_empty.choices = [MagicMock()]
        mock_response_empty.choices[0].message.content = ""
        
        mock_response_valid = MagicMock()
        mock_response_valid.choices = [MagicMock()]
        mock_response_valid.choices[0].message.content = "有效响应"
        
        mock_client.chat.completions.create.side_effect = [
            mock_response_empty,
            mock_response_valid
        ]
        mock_get_gemini.return_value = mock_client
        
        result = access_model("测试提示词", "gemini", max_retries=3, retry_delay=0.1)
        
        assert result == "有效响应", "响应内容不匹配"
        assert mock_client.chat.completions.create.call_count == 2, "应该调用2次"
    
    print("✅ 测试通过：空响应被检测并重试")


def test_exponential_backoff():
    """测试：指数退避策略"""
    print("\n" + "="*60)
    print("测试5: 指数退避策略")
    print("="*60)
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "测试响应"
    
    with patch('model.get_gemini') as mock_get_gemini:
        with patch('time.sleep') as mock_sleep:
            mock_client = MagicMock()
            # 前3次失败，第4次成功
            mock_client.chat.completions.create.side_effect = [
                ConnectionError("失败1"),
                ConnectionError("失败2"),
                ConnectionError("失败3"),
                mock_response
            ]
            mock_get_gemini.return_value = mock_client
            
            result = access_model("测试提示词", "gemini", max_retries=4, retry_delay=2)
            
            # 验证 sleep 调用次数和参数（指数退避）
            assert mock_sleep.call_count == 3, f"应该调用 sleep 3次，实际 {mock_sleep.call_count} 次"
            
            # 验证退避时间：2s, 4s, 8s
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            expected_delays = [2, 4, 8]  # 指数退避
            assert sleep_calls == expected_delays, f"退避时间不正确: {sleep_calls} != {expected_delays}"
    
    print("✅ 测试通过：指数退避策略正确")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "🧪 "+"="*58)
    print("🧪 网络容错机制测试套件")
    print("🧪 "+"="*58)
    
    tests = [
        test_successful_call,
        test_retry_once_then_success,
        test_all_retries_fail,
        test_empty_response,
        test_exponential_backoff,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ 测试失败: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"测试结果: ✅ {passed} 通过, ❌ {failed} 失败")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

