import subprocess
import os
import json
import tempfile
import shutil

SKILL_DIR = os.path.join(os.path.dirname(__file__), "vendor", "baoyu-post-to-wechat")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
BUN = (
    shutil.which("bun")
    or shutil.which("bun.cmd")
    or os.path.expanduser(r"~\AppData\Roaming\npm\bun.cmd")
    or "bun.cmd"
)

def _load_env(env_path):
    env = {}
    if not os.path.exists(env_path):
        return env
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def _extract_error(stderr):
    for line in (stderr or "").splitlines():
        if line.startswith("Error:"):
            return line[len("Error:"):].strip()
    return (stderr or "发布失败")[:200]

def publish_article(date_str, result):
    from app.config import get_config
    from app.markdown import build_markdown
    from app.markdown import format_article
    from app.cover_generator import generate_cover
    cfg = get_config()
    text = build_markdown(result, date_str, cfg.get("title", ""), cfg.get("data_source", ""))
    formatted = format_article(text)
    generate_cover(date_str, cfg.get("title"), cfg.get("author"))
    cover_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "static", "covers", f"{date_str}.png")
    return publish_to_wechat(cfg.get("title"), formatted, cover_path, cfg.get("author"))

def publish_to_wechat(title, content, cover_path, author=""):
    entry = os.path.join(SCRIPTS_DIR, "wechat-api.ts")
    if not os.path.exists(entry):
        return {"success": False, "error": "发布 skill 不存在"}
    tf = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
    tf.write(content)
    tf.close()
    try:
        env = os.environ.copy()
        dot_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env.update(_load_env(dot_env))
        args = [BUN, "run", "wechat-api.ts", tf.name, "--no-cite", "--theme", "default"]
        if title:
            args.extend(["--title", title])
        if author:
            args.extend(["--author", author])
        if cover_path and os.path.exists(cover_path):
            args.extend(["--cover", os.path.abspath(cover_path)])
        result = subprocess.run(
            args,
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env
        )
        if result.returncode != 0:
            return {"success": False, "error": _extract_error(result.stderr)}
        output = result.stdout.strip()
        if output:
            try:
                parsed = json.loads(output)
                if parsed.get("success"):
                    return {"success": True, "media_id": parsed.get("media_id", "")}
                return {"success": False, "error": parsed.get("error", "发布失败")}
            except json.JSONDecodeError:
                return {"success": True, "result": output}
        return {"success": False, "error": _extract_error(result.stderr)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "发布超时"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tf.name)
        except OSError:
            pass
