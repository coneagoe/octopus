"""Test cases for run.sh."""

import os
import stat
import subprocess
import textwrap
from pathlib import Path

# subprocess.run in supported Python versions accepts capture_output and text


def _write_executable(path, content):
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class TestRunSh:
    def test_run_sh_reports_logs_create_failure_without_tee_noise(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )
        (repo_dir / "logs").write_text("not-a-directory", encoding="utf-8")

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        source_askpass = Path(__file__).resolve().parents[1] / "scripts" / "git_askpass.sh"

        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(source_askpass.read_text(encoding="utf-8"), encoding="utf-8")
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
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

        assert result.returncode == 1
        assert "错误：logs 目录不可写" in result.stdout
        assert "tee:" not in result.stderr
        assert "cannot create directory" not in result.stderr
        assert "Permission denied" not in result.stderr

    def test_run_sh_reports_output_create_failure_with_custom_message(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )
        (repo_dir / "logs").mkdir()
        (repo_dir / "output").write_text("not-a-directory", encoding="utf-8")

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        source_askpass = Path(__file__).resolve().parents[1] / "scripts" / "git_askpass.sh"

        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(source_askpass.read_text(encoding="utf-8"), encoding="utf-8")
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
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

        assert result.returncode == 1
        assert "错误：output 目录不可写" in result.stdout
        assert "cannot create directory" not in result.stderr

    def test_run_sh_exits_when_dotenv_missing(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        source_askpass = Path(__file__).resolve().parents[1] / "scripts" / "git_askpass.sh"

        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(source_askpass.read_text(encoding="utf-8"), encoding="utf-8")
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
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

        assert result.returncode == 1
        assert "错误：未找到 .env 文件" in result.stdout

    def test_run_sh_exits_when_git_metadata_missing(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        source_askpass = Path(__file__).resolve().parents[1] / "scripts" / "git_askpass.sh"

        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(source_askpass.read_text(encoding="utf-8"), encoding="utf-8")
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
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

        assert result.returncode == 1
        assert "错误：当前目录缺少 .git，无法执行 Git 提交流程" in result.stdout

    def test_run_sh_continues_when_zhihu_fetch_fails(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)
        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"placeholder\"\n",
            encoding="utf-8",
        )
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

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
            if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then
              echo "https://github.com/coneagoe/octopus.git"
              exit 0
            fi
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

    def test_run_sh_exits_when_github_pat_missing_before_push(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text("MINIMAX_API_KEY=test-key\n", encoding="utf-8")

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
            """,
        )

        _write_executable(
            bin_dir / "git",
            """#!/bin/sh
            exit 0
            """,
        )

        env = os.environ.copy()
        env.pop("GITHUB_PAT", None)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"

        result = subprocess.run(
            ["bash", str(run_sh), "morning"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "错误：缺少 GITHUB_PAT，无法执行 Git push" in result.stdout

    def test_run_sh_exports_git_askpass_for_https_push(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"

        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"placeholder\"\n",
            encoding="utf-8",
        )
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        trace_file = tmp_path / "git-trace.log"

        _write_executable(
            bin_dir / "uv",
            """#!/bin/sh
            exit 0
            """,
        )

        _write_executable(
            bin_dir / "git",
            f"""#!/bin/sh
            if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then
              echo "https://github.com/coneagoe/octopus.git"
              exit 0
            fi
            if [ "$1" = "push" ]; then
              echo "ASKPASS=$GIT_ASKPASS" >> "{trace_file}"
              echo "PROMPT=$GIT_TERMINAL_PROMPT" >> "{trace_file}"
              exit 0
            fi
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

        trace = trace_file.read_text(encoding="utf-8")

        assert result.returncode == 0
        assert "ASKPASS=" in trace
        assert "git_askpass.sh" in trace
        assert "PROMPT=0" in trace

    def test_run_sh_writes_am_output_file_and_commit_message(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"placeholder\"\n",
            encoding="utf-8",
        )
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        trace_file = tmp_path / "trace.log"

        _write_executable(
            bin_dir / "uv",
            f"""#!/bin/sh
            echo "$@" >> "{trace_file}"
            exit 0
            """,
        )
        _write_executable(
            bin_dir / "git",
            f"""#!/bin/sh
            echo "$@" >> "{trace_file}"
            if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then
              echo "https://github.com/coneagoe/octopus.git"
              exit 0
            fi
            exit 0
            """,
        )

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["OCTOPUS_REPORT_DATE"] = "2026-05-13"
        env["OCTOPUS_REPORT_HOUR"] = "08"

        result = subprocess.run(
            ["bash", str(run_sh), "evening"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        trace_lines = trace_file.read_text(encoding="utf-8").splitlines()

        assert result.returncode == 0
        expected_uv = f"run python {scripts_dir / 'summarize.py'} --date 2026-05-13 --output {repo_dir / 'output' / 'daily' / '2026-05-13-AM.md'}"
        assert trace_lines.count(expected_uv) == 1
        expected_commit = "commit -m Daily update: 2026-05-13 AM"
        assert trace_lines.count(expected_commit) == 1
        # ensure no PM artifacts are present
        opposite_uv = f"run python {scripts_dir / 'summarize.py'} --date 2026-05-13 --output {repo_dir / 'output' / 'daily' / '2026-05-13-PM.md'}"
        assert opposite_uv not in trace_lines
        assert "commit -m Daily update: 2026-05-13 PM" not in trace_lines

    def test_run_sh_writes_pm_output_file_and_commit_message(self, tmp_path):
        repo_dir = tmp_path / "repo"
        scripts_dir = repo_dir / "scripts"
        bin_dir = tmp_path / "bin"
        scripts_dir.mkdir(parents=True)
        bin_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / ".env").write_text(
            "MINIMAX_API_KEY=test-key\nGITHUB_PAT=test-pat\n",
            encoding="utf-8",
        )

        source_run_sh = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_sh = scripts_dir / "run.sh"
        run_sh.write_text(source_run_sh.read_text(encoding="utf-8"), encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IEXEC)

        askpass_sh = scripts_dir / "git_askpass.sh"
        askpass_sh.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"placeholder\"\n",
            encoding="utf-8",
        )
        askpass_sh.chmod(askpass_sh.stat().st_mode | stat.S_IEXEC)

        trace_file = tmp_path / "trace.log"

        _write_executable(
            bin_dir / "uv",
            f"""#!/bin/sh
            echo "$@" >> "{trace_file}"
            exit 0
            """,
        )
        _write_executable(
            bin_dir / "git",
            f"""#!/bin/sh
            echo "$@" >> "{trace_file}"
            if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then
              echo "https://github.com/coneagoe/octopus.git"
              exit 0
            fi
            exit 0
            """,
        )

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["OCTOPUS_REPORT_DATE"] = "2026-05-13"
        env["OCTOPUS_REPORT_HOUR"] = "20"

        result = subprocess.run(
            ["bash", str(run_sh), "morning"],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        trace_lines = trace_file.read_text(encoding="utf-8").splitlines()

        assert result.returncode == 0
        expected_uv = f"run python {scripts_dir / 'summarize.py'} --date 2026-05-13 --output {repo_dir / 'output' / 'daily' / '2026-05-13-PM.md'}"
        assert trace_lines.count(expected_uv) == 1
        expected_commit = "commit -m Daily update: 2026-05-13 PM"
        assert trace_lines.count(expected_commit) == 1
        # ensure no AM artifacts are present
        opposite_uv = f"run python {scripts_dir / 'summarize.py'} --date 2026-05-13 --output {repo_dir / 'output' / 'daily' / '2026-05-13-AM.md'}"
        assert opposite_uv not in trace_lines
        assert "commit -m Daily update: 2026-05-13 AM" not in trace_lines
