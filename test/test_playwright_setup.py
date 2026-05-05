"""Test cases for Playwright Chromium setup helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestPlaywrightSetup:
    def test_is_chromium_ready_returns_true_when_launch_succeeds(self, monkeypatch):
        from scripts import playwright_setup

        events = []

        class FakeBrowser:
            def close(self):
                events.append("browser-close")

        class FakeChromium:
            def launch(self, headless=True):
                events.append(("launch", headless))
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()

        class FakeManager:
            def __enter__(self):
                events.append("enter")
                return FakePlaywright()

            def __exit__(self, exc_type, exc, tb):
                events.append("exit")

        monkeypatch.setattr(playwright_setup, "sync_playwright", lambda: FakeManager())

        ready, message = playwright_setup.is_chromium_ready()

        assert ready is True
        assert message == ""
        assert events == ["enter", ("launch", True), "browser-close", "exit"]

    def test_is_chromium_ready_returns_false_with_actionable_message(self, monkeypatch):
        from scripts import playwright_setup

        class FakeManager:
            def __enter__(self):
                class FakeChromium:
                    def launch(self, headless=True):
                        raise RuntimeError("Executable doesn't exist at /tmp/chromium")

                class FakePlaywright:
                    chromium = FakeChromium()

                return FakePlaywright()

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(playwright_setup, "sync_playwright", lambda: FakeManager())

        ready, message = playwright_setup.is_chromium_ready()

        assert ready is False
        assert "Chromium 浏览器未安装" in message
        assert "uv run python scripts/playwright_setup.py --install-if-missing" in message

    def test_main_installs_when_missing_and_returns_zero(self, monkeypatch, capsys):
        from scripts import playwright_setup

        monkeypatch.setattr(
            playwright_setup,
            "is_chromium_ready",
            lambda: (False, "Chromium 浏览器未安装，请先执行 setup"),
        )

        calls = []

        def fake_run(cmd, check):
            calls.append((cmd, check))

        monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)

        exit_code = playwright_setup.main(["--install-if-missing"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert calls == [([sys.executable, "-m", "playwright", "install", "chromium"], True)]
        assert "开始安装 Playwright Chromium" in captured.out

    def test_main_returns_nonzero_when_install_fails(self, monkeypatch, capsys):
        from scripts import playwright_setup

        monkeypatch.setattr(
            playwright_setup,
            "is_chromium_ready",
            lambda: (False, "Chromium 浏览器未安装，请先执行 setup"),
        )

        def fake_run(cmd, check):
            raise playwright_setup.subprocess.CalledProcessError(returncode=1, cmd=cmd)

        monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)

        exit_code = playwright_setup.main(["--install-if-missing"])
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "安装 Chromium 失败" in captured.out
