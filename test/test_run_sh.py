"""Test cases for run.sh."""

import os
import stat
import subprocess
import textwrap
from pathlib import Path


def _write_executable(path, content):
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class TestRunSh:
    def test_run_sh_continues_when_zhihu_fetch_fails(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        trace_file = tmp_path / "trace.log"

        _write_executable(
            bin_dir / "uv",
            f"""#!/bin/sh
            echo "$@" >> "{trace_file}"
            case "$@" in
              *fetch_zhihu.py*) exit 1 ;;
              *) exit 0 ;;
            esac
            """,
        )

        _write_executable(
            bin_dir / "git",
            """#!/bin/sh
            exit 0
            """,
        )

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"

        result = subprocess.run(
            ["bash", str(run_sh), "morning"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        trace_lines = trace_file.read_text(encoding="utf-8").splitlines()

        assert result.returncode == 0
        assert "警告：知乎采集失败，继续执行后续流程" in result.stdout
        assert any("fetch_rss.py" in line for line in trace_lines)
        assert any("fetch_zhihu.py" in line for line in trace_lines)
        assert any("fetch_web.py" in line for line in trace_lines)
        assert any("fetch_feishu.py" in line for line in trace_lines)
        assert any("fetch_email.py" in line for line in trace_lines)
        assert any("summarize.py" in line for line in trace_lines)
