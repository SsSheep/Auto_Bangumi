"""AB_WEBUI_PORT 环境变量优先级：每次启动生效，覆盖配置文件端口。"""

from module.conf import resolve_webui_port, settings


def test_env_overrides_config(monkeypatch):
    monkeypatch.setattr(settings.program, "webui_port", 7892)
    monkeypatch.setenv("AB_WEBUI_PORT", "9000")
    assert resolve_webui_port() == 9000


def test_falls_back_to_config_without_env(monkeypatch):
    monkeypatch.setattr(settings.program, "webui_port", 7893)
    monkeypatch.delenv("AB_WEBUI_PORT", raising=False)
    assert resolve_webui_port() == 7893


def test_invalid_env_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(settings.program, "webui_port", 7892)
    monkeypatch.setenv("AB_WEBUI_PORT", "not-a-number")
    assert resolve_webui_port() == 7892
