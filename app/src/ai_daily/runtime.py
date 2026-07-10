import json
import os
from pathlib import Path

from .content import Content
from .daily_run import DailyRun
from .publishing import WeChatPublisher
from .storage import Store


DEFAULT_SETTINGS = {"title": "AI 行业热点新闻", "author": "", "max_words": 150}


def load_environment(app_dir: Path) -> None:
    """Load the new app/.env, then legacy root/.env only when absent."""
    candidates = [app_dir.parent / ".env", app_dir / ".env"]
    existing_keys = set(os.environ)
    loaded = {}
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                loaded[key.strip()] = value.strip()
    for key, value in loaded.items():
        if key not in existing_keys:
            os.environ[key] = value


class AihotSource:
    def __call__(self, date: str) -> list[dict]:
        import requests
        response = requests.get(
            f"https://aihot.virxact.com/api/public/daily/{date}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36", "Accept": "application/json"},
            timeout=20,
        )
        response.raise_for_status()
        items = []
        for section in response.json().get("sections", []):
            for item in section.get("items", []):
                link = item.get("permalink") or item.get("sourceUrl")
                if link:
                    items.append({"title": item.get("title", ""), "summary": item.get("summary", ""),
                                  "source": item.get("sourceName", ""), "source_url": link,
                                  "category": section.get("label", "行业动态")})
        return items


class OpenAiCompatibleLlm:
    def __call__(self, messages: list[dict]) -> str:
        import requests
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 LLM_API_KEY")
        base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {"model": os.environ.get("LLM_MODEL", "gpt-4o-mini"), "messages": messages, "max_tokens": 8000}
        response = requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=(15, 120))
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def build_runner(app_dir: Path, preview_only: bool = False) -> DailyRun:
    load_environment(app_dir)
    settings = DEFAULT_SETTINGS.copy()
    legacy = app_dir / "data" / "config.json"
    if legacy.is_file():
        settings.update(json.loads(legacy.read_text(encoding="utf-8")))
    publisher = (lambda article: (_ for _ in ()).throw(RuntimeError("预览模式禁止创建微信草稿"))) if preview_only else WeChatPublisher(settings["title"], author=settings["author"])
    return DailyRun(Store(app_dir / "data" / "ai_daily.db"), Content(AihotSource(), OpenAiCompatibleLlm()), publisher)
