import shutil
import subprocess
from pathlib import Path


def test_publish_finalization_polling_runs_the_real_browser_script():
    node = shutil.which("node")
    assert node, "Node.js is required for the browser behavior regression test"
    script = Path(__file__).with_name("browser_publish_finalizing_test.js")

    result = subprocess.run([node, str(script)], capture_output=True, encoding="utf-8", errors="replace", timeout=10)

    assert result.returncode == 0, result.stderr or result.stdout
