import os
import json
import requests

def _load_prompt():
    path = os.path.join(os.path.dirname(__file__), "prompts", "rewrite.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _call_agnes(messages, max_tokens=8000):
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return None, "API 凭证未配置（检查 .env 中的 LLM_API_KEY）"
    base_url = os.environ.get("LLM_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "agnes-2.0-flash")
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_tokens": max_tokens},
                timeout=(10, 60)
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], None
        except Exception as e:
            last_err = str(e)
            if attempt < 2:
                import time
                time.sleep((2 ** attempt) * 2)
    return None, last_err

def rewrite_news(items, max_words=150, progress_callback=None):
    daily_lines = []
    for i, item in enumerate(items, 1):
        daily_lines.append(f"### 条目 {i}")
        daily_lines.append(f"标题：{item['title']}")
        daily_lines.append(f"内容：{item['content']}")
        daily_lines.append(f"链接：{item.get('link', '')}")
        daily_lines.append(f"来源：{item['source']}")
        daily_lines.append("")
    daily_data = "\n".join(daily_lines)

    prompt = _load_prompt().replace("{{MAX_CHARS}}", str(max_words)).replace("{{DAILY_DATA}}", daily_data)

    if progress_callback:
        progress_callback(1, len(items))

    raw, err = _call_agnes([
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"请根据以上要求处理今日的 {len(items)} 条 AI 新闻。"}
    ], max_tokens=8000)
    if err:
        raise RuntimeError(f"API 调用失败: {err}")

    result = _parse_response(raw, items, max_words)

    if progress_callback:
        progress_callback(len(items), len(items))

    return result

def _parse_response(raw, original_items, max_words):
    json_str = raw.strip()
    if json_str.startswith("```"):
        json_str = json_str.split("\n", 1)[1]
        json_str = json_str.rsplit("```", 1)[0]
    json_str = json_str.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        data = _try_repair_json(json_str)

    if data is None:
        return _fallback(original_items, max_words)

    items = []
    for i, orig in enumerate(original_items):
        if i < len(data.get("items", [])):
            entry = data["items"][i]
            items.append({
                "title": entry.get("title", orig["title"]),
                "body": entry.get("rewritten", orig["content"][:max_words]),
                "link": entry.get("link", orig.get("link", "")),
                "source": entry.get("source", orig.get("source", "")),
                "category": orig.get("category", "")
            })
        else:
            items.append({
                "title": orig["title"],
                "body": orig["content"][:max_words],
                "link": orig.get("link", ""),
                "source": orig.get("source", ""),
                "category": orig.get("category", "")
            })

    return {
        "items": items,
        "opening": data.get("todayObservation", ""),
        "closing": data.get("editorComment", "")
    }


def _try_repair_json(s):
    """Attempt to parse truncated JSON by stripping trailing garbage"""
    for _ in range(3):
        brace = s.rfind("}")
        if brace < 0:
            break
        candidate = s[:brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            s = s[:brace]
    return None

def _fallback(original_items, max_words):
    items = []
    for item in original_items:
        items.append({
            "title": item["title"],
            "body": item["content"][:max_words],
            "link": item.get("link", ""),
            "source": item.get("source", ""),
            "category": item.get("category", "")
        })
    return {
        "items": items,
        "opening": "",
        "closing": ""
    }
