import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .cover import generate_cover


VENDOR_SCRIPTS = Path(__file__).parents[2] / "vendor" / "baoyu-post-to-wechat" / "scripts"


def build_wechat_command(bun: str, article: Path, title: str, cover: str, author: str) -> list[str]:
    command = [bun, "run", "wechat-api.ts", str(article), "--theme", "default"]
    if title: command += ["--title", title]
    if cover: command += ["--cover", cover]
    if author: command += ["--author", author]
    return command


class WeChatPublisher:
    def __init__(self, title: str, cover: str = "", author: str = ""):
        self.title, self.cover, self.author = title, cover, author

    def __call__(self, article: dict) -> str:
        bun = shutil.which("bun") or shutil.which("bun.cmd")
        if not bun or not (VENDOR_SCRIPTS / "wechat-api.ts").is_file():
            raise RuntimeError("微信发布环境不完整：缺少 Bun 或发布脚本")
        cover = article.get("cover_path") or self.cover or str(
            generate_cover(Path(__file__).parents[2] / "static" / "covers", article["date"], self.title)
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as file:
            file.write(article["markdown"])
            path = Path(file.name)
        try:
            result = subprocess.run(build_wechat_command(bun, path, self.title, cover, self.author),
                                    cwd=VENDOR_SCRIPTS, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError((result.stderr or "微信草稿创建失败").strip()[:500])
            payload = json.loads(result.stdout)
            media_id = payload.get("media_id") if payload.get("success") else ""
            if not media_id:
                raise RuntimeError(payload.get("error", "微信未返回草稿回执"))
            return media_id
        finally:
            path.unlink(missing_ok=True)
