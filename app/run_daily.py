import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime
from app.env import load_env
load_env()
from app.pipeline import run_pipeline, PipelineError
from app.publisher import publish_article
from app.config import get_config


def run():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] 开始处理: {date_str}")

    title = f"AI 行业热点新闻 | {date_str}"
    from app.config import set_config
    set_config("title", title)

    try:
        result = run_pipeline(date_str, get_config("max_words"))
    except PipelineError as e:
        print(f"处理失败: {e}")
        return 1

    pub_result = publish_article(date_str, result)
    if pub_result.get("success"):
        print(f"发布成功，草稿ID: {pub_result.get('media_id', '')}")
        return 0
    else:
        print(f"发布失败: {pub_result.get('error', '')}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
