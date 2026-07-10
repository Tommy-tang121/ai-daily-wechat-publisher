import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime
from app.env import load_env
load_env()
from app.pipeline import run_pipeline, PipelineError
from app.publisher import publish_article
from app.config import get_config


def _log(msg):
    log_path = os.path.join(os.path.dirname(__file__), "logs", "scheduled.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")
    print(msg)


def run():
    date_str = datetime.now().strftime("%Y-%m-%d")
    _log(f"[{datetime.now()}] 开始处理: {date_str}")

    title = f"AI 行业热点新闻 | {date_str}"
    from app.config import set_config
    set_config("title", title)

    try:
        result = run_pipeline(date_str, get_config("max_words"))
    except Exception as e:
        _log(f"处理失败 ({type(e).__name__}): {e}")
        import traceback
        _log(traceback.format_exc())
        return 1

    pub_result = publish_article(date_str, result)
    if pub_result.get("success"):
        _log(f"发布成功，草稿ID: {pub_result.get('media_id', '')}")
        return 0
    else:
        _log(f"发布失败: {pub_result.get('error', '')}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:
        _log(f"未捕获异常 ({type(e).__name__}): {e}")
        import traceback
        _log(traceback.format_exc())
        sys.exit(1)
