"""
获取 llm（Gemini via OpenRouter）
保持外部接口不变：
- get_deepseek()
- access_model(prompts, model=..., ...)
"""
import time
import json
import requests
from openai import OpenAI  # 保留导入以免你项目其它地方依赖


# =========================
# ❶ 在这里硬编码 OpenRouter API Key（优先使用）
# =========================
DEEPSEEK_API_KEY = ""

# =========================
# ❷ OpenRouter 配置
# =========================
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_GEMINI_MODEL = "google/gemini-3-flash-preview"


def get_deepseek():
    """
    保持函数名不变：返回 OpenRouter 调用所需配置。
    """
    api_key = DEEPSEEK_API_KEY

    # 如果你没硬编码，就尝试从环境变量读（兼容旧项目变量名）
    if not api_key:
        api_key = (
            __import__("os").getenv("OPENROUTER_API_KEY")
            or __import__("os").getenv("DEEPSEEK_API_KEY")
        )

    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY 为空：请在 model.py 中硬编码 OpenRouter Key，"
            "或设置环境变量 OPENROUTER_API_KEY / DEEPSEEK_API_KEY"
        )

    return {
        "base_url": _OPENROUTER_BASE_URL,
        "api_key": api_key,
        "timeout": 300.0,
    }


def access_model(prompts, model="deepseek-reasoner", max_retries=3, retry_delay=5):
    """
    保持函数签名不变。
    - 兼容你原先传入的 deepseek-reasoner/deepseek-chat
    - 实际走 OpenRouter 的 Gemini 模型
    """
    model_alias_map = {
        "deepseek-reasoner": _DEFAULT_GEMINI_MODEL,
        "deepseek-chat": _DEFAULT_GEMINI_MODEL,
    }
    actual_model = model_alias_map.get(model, model)

    print(f"--- 使用 Gemini(OpenRouter) 模型: {actual_model} ---")
    client = get_deepseek()

    url = f"{client['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {client['api_key']}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                wait_time = retry_delay * (2 ** (attempt - 2))
                print(f"⏳ 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

            print(f"📡 正在调用 LLM API (尝试 {attempt}/{max_retries})...")

            # --- 增加调试信息输出 ---
            print(f"📝 Prompt 长度: {len(prompts)} 字符")
            # 只显示前 500 个和最后 500 个字符，避免刷屏，或者直接全部打印（如果用户需要定位原因，全部打印可能更好）
            print("-" * 30 + " Prompt Start " + "-" * 30)
            print(prompts)
            print("-" * 30 + "  Prompt End  " + "-" * 30)
            print(f"⏳ 正在等待 LLM 响应 (超时设置: {client['timeout']}s)...")
            # ----------------------

            payload = {
                "model": actual_model,
                "messages": [{"role": "user", "content": prompts}],
                # 建议：先别开 reasoning，等链路稳定再开
                # "reasoning": {"enabled": True},

                # 关键修复：强制走可用的 provider
                "provider": {
                    "only": ["google-vertex"],
                    "allow_fallbacks": False
                }
            }

            resp = requests.post(
                url=url,
                headers=headers,
                data=json.dumps(payload),
                timeout=client["timeout"],
            )

            try:
                resp_json = resp.json()
            except Exception:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp_json}")

            content = resp_json["choices"][0]["message"].get("content", "")
            if not content or len(content.strip()) == 0:
                raise ValueError(f"LLM 返回了空响应: {resp_json}")

            print(f"✅ LLM 调用成功（尝试 {attempt}/{max_retries}）")
            # --- 增加响应调试信息 ---
            print(f"📄 Response 长度: {len(content)} 字符")
            print("-" * 30 + " Response Start " + "-" * 30)
            print(content[:1000] + ("..." if len(content) > 1000 else ""))
            print("-" * 30 + "  Response End  " + "-" * 30)
            # ----------------------
            return content

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)

            print(f"❌ 调用 Gemini(OpenRouter) API 失败 (尝试 {attempt}/{max_retries})")
            print(f"   错误类型: {error_type}")
            print(f"   错误信息: {error_msg}")

            if attempt == max_retries:
                print(f"\n{'=' * 60}")
                print(f"❌ LLM 调用失败：已尝试 {max_retries} 次，全部失败")
                print(f"{'=' * 60}")

                with open("llm_failure.log", "a", encoding="utf-8") as f:
                    f.write(f"\n{'=' * 60}\n")
                    f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"模型: {actual_model}\n")
                    f.write(f"错误类型: {error_type}\n")
                    f.write(f"错误信息: {error_msg}\n")
                    f.write(f"重试次数: {max_retries}\n")
                    f.write(f"{'=' * 60}\n")

                raise Exception(
                    f"LLM 调用失败（{max_retries}次重试后）: {error_type}: {error_msg}"
                ) from e

            print("🔄 准备重试...")

    raise Exception("LLM 调用失败：未知错误")
