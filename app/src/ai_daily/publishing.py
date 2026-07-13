import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from .cover import generate_cover


VENDOR_SCRIPTS = Path(__file__).parents[2] / "vendor" / "baoyu-post-to-wechat" / "scripts"


def build_wechat_command(bun: str, article: Path, title: str, cover: str, author: str) -> list[str]:
    command = [bun, "run", "wechat-api.ts", str(article), "--no-cite", "--theme", "default"]
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
        title = article.get("title") or self.title
        cover = article.get("cover_path") or self.cover or str(
            generate_cover(Path(__file__).parents[2] / "static" / "runtime-covers", article["date"], title)
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as file:
            file.write(article["markdown"])
            path = Path(file.name)
        try:
            result = subprocess.run(build_wechat_command(bun, path, title, cover, self.author),
                                    cwd=VENDOR_SCRIPTS, capture_output=True, text=True, encoding="utf-8", timeout=120)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout or "微信草稿创建失败").strip()[-500:])
            payload = json.loads(result.stdout)
            media_id = payload.get("media_id") if payload.get("success") else ""
            if not media_id:
                raise RuntimeError(payload.get("error", "微信未返回草稿回执"))
            return media_id
        finally:
            path.unlink(missing_ok=True)

    def delete_draft(self, media_id: str) -> None:
        app_id = os.environ.get("WECHAT_APP_ID")
        app_secret = os.environ.get("WECHAT_APP_SECRET")
        if not app_id or not app_secret:
            raise RuntimeError("微信公众号删除草稿失败：发布凭据未配置")
        try:
            token_response = requests.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret},
                timeout=(15, 30),
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError("微信公众号获取访问令牌失败") from None
        access_token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
        if not access_token:
            code = token_payload.get("errcode") if isinstance(token_payload, dict) else None
            suffix = f"（错误码 {code}）" if code is not None else ""
            raise RuntimeError(f"微信公众号获取访问令牌失败{suffix}")
        try:
            delete_response = requests.post(
                "https://api.weixin.qq.com/cgi-bin/draft/delete",
                params={"access_token": access_token},
                json={"media_id": media_id},
                timeout=(15, 30),
            )
            delete_response.raise_for_status()
            delete_payload = delete_response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError("微信公众号删除草稿失败") from None
        if isinstance(delete_payload, dict) and delete_payload.get("errcode") == 40007 and "invalid media_id" in str(delete_payload.get("errmsg", "")).lower():
            return
        if not isinstance(delete_payload, dict) or delete_payload.get("errcode") != 0:
            code = delete_payload.get("errcode") if isinstance(delete_payload, dict) else None
            suffix = f"（错误码 {code}）" if code is not None else ""
            raise RuntimeError(f"微信公众号删除草稿失败{suffix}")
