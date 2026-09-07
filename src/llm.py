"""LLM calls via stdlib urllib. Providers: openrouter, groq, gemini. No key printed."""
import json
import os
import time
import urllib.request

from src.config import get_settings


def _post(url: str, payload: dict, headers: dict, timeout: int = 120,
          retries: int = 3) -> dict:
    import time as _time
    import urllib.error

    # User-Agent thường: api.groq.com (Cloudflare) cấm signature
    # Python-urllib mặc định -> 403/1010 (đã gặp thật).
    headers = {"User-Agent": "Groq/Python", **headers}
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=headers
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            data["_latency_s"] = round(time.time() - t0, 2)
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503) and attempt < retries - 1:
                # Free-tier RPM window ~60s: backoff ngắn hơn vô dụng (đã đo).
                _time.sleep(30 * (attempt + 1))
                continue
            raise
    raise last  # pragma: no cover


def _keys(*names: str) -> list[str]:
    """Env keys in priority order, skipping empties. Secrets never logged."""
    return [v for v in (os.getenv(n, "") for n in names) if v]


def _try_groq(messages: list[dict], max_tokens: int, temperature: float) -> tuple[str, dict]:
    last_err: Exception | None = None
    # qwen3.8 trả content trực tiếp; gpt-oss là reasoning model (nghĩ trong
    # message.reasoning, content rỗng) -> chỉ dùng dự phòng.
    models = [m.strip() for m in
              os.getenv("GEN_MODELS_GROQ",
                        os.getenv("GEN_MODEL", "qwen/qwen3.8-27b,openai/gpt-oss-120b")).split(",")
              if m.strip()]
    for key in _keys("GROQ_API_KEY", "GROQ_API_KEY_2"):
        for model in models:
            try:
                data = _post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    {"model": model, "messages": messages,
                     "max_tokens": max_tokens, "temperature": temperature},
                    {"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                    retries=2,
                )
                text = data["choices"][0]["message"]["content"] or ""
                if not text.strip():
                    raise ValueError(f"{model} returned empty content (reasoning model)")
                return text, {"provider": "groq", "model": model,
                              "latency_s": data.get("_latency_s")}
            except Exception as e:
                last_err = e
                continue
    raise last_err  # type: ignore[misc]


def _try_gemini(messages: list[dict], max_tokens: int, temperature: float) -> tuple[str, dict]:
    keys = _keys("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3")
    models = [m.strip() for m in
              os.getenv("GEN_MODELS", os.getenv("GEN_MODEL", "gemini-3.5-flash")).split(",")
              if m.strip()]
    last_err: Exception | None = None
    for key in keys:
        for model in models:
            prompt = "\n\n".join(m.get("content", "") for m in messages)
            # 3.5 thinking ngầm ăn hết output budget -> tắt hẳn.
            # 3.6 không nhận thinkingConfig (400) -> không gửi.
            gen_cfg = ({"maxOutputTokens": max_tokens, "temperature": temperature,
                        "thinkingConfig": {"thinkingBudget": 0}}
                       if "3.5" in model else
                       {"maxOutputTokens": max_tokens, "temperature": temperature})
            try:
                data = _post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                    {"contents": [{"parts": [{"text": prompt}]}],
                     "generationConfig": gen_cfg},
                    {"Content-Type": "application/json"},
                    retries=2,
                )
                text = "".join(
                    part.get("text", "")
                    for part in data["candidates"][0]["content"].get("parts", [])
                )
                return text, {"provider": "gemini", "model": model,
                              "latency_s": data.get("_latency_s"),
                              "finish": data["candidates"][0].get("finishReason")}
            except Exception as e:
                last_err = e
                continue
    raise last_err  # type: ignore[misc]


def _try_openrouter(messages: list[dict], max_tokens: int,
                    temperature: float) -> tuple[str, dict]:
    s = get_settings()
    key = os.getenv("OPENROUTER_API_KEY", "")
    data = _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {"model": s["gen_model"], "messages": messages,
         "max_tokens": max_tokens, "temperature": temperature},
        {"Authorization": "Bearer " + key, "Content-Type": "application/json",
         "HTTP-Referer": "https://localhost", "X-Title": "tcb-chatbot"},
    )
    return data["choices"][0]["message"]["content"], {
        "provider": "openrouter", "model": s["gen_model"],
        "latency_s": data.get("_latency_s")}


_PROVIDERS = {"gemini": _try_gemini, "groq": _try_groq, "openrouter": _try_openrouter}


def chat_complete(messages: list[dict], max_tokens: int = 1024,
                  temperature: float = 0.1) -> tuple[str, dict]:
    """Provider chain qua PROVIDER (vd 'gemini,groq'): thử từng cái theo thứ tự."""
    s = get_settings()
    chain = [p.strip() for p in s["provider"].split(",") if p.strip() in _PROVIDERS]
    if not chain:
        chain = ["openrouter"]
    last_err: Exception | None = None
    for pname in chain:
        try:
            return _PROVIDERS[pname](messages, max_tokens, temperature)
        except Exception as e:
            last_err = e
            continue
    raise last_err  # type: ignore[misc]
