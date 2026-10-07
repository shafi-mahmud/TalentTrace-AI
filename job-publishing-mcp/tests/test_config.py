import pytest

from conftest import SYNTHETIC_WEBHOOK
from talenttrace_job_publishing.config import PublishingConfigurationError, Settings, load_settings


def test_missing_webhook_is_safe():
    with pytest.raises(PublishingConfigurationError, match="not configured"):
        Settings(_env_file=None).require_webhook()


def test_secret_is_masked(settings):
    assert SYNTHETIC_WEBHOOK not in repr(settings)
    assert SYNTHETIC_WEBHOOK not in str(settings)
    assert SYNTHETIC_WEBHOOK not in settings.model_dump_json()


@pytest.mark.parametrize("url", [
    SYNTHETIC_WEBHOOK.replace("https:", "http:"),
    SYNTHETIC_WEBHOOK.replace("discord.com", "example.com"),
    SYNTHETIC_WEBHOOK.replace("discord.com", "discord.com.example.com"),
    SYNTHETIC_WEBHOOK.replace("discord.com", "user:pass@discord.com"),
    SYNTHETIC_WEBHOOK.replace("discord.com", "discord.com:443"),
    SYNTHETIC_WEBHOOK.replace("/api/webhooks/", "/api/other/"),
    SYNTHETIC_WEBHOOK + "?wait=true", SYNTHETIC_WEBHOOK + "#secret",
    SYNTHETIC_WEBHOOK + "\n", "your_discord_webhook_url_here",
])
def test_invalid_webhook_is_rejected_without_echo(url):
    with pytest.raises(PublishingConfigurationError) as error:
        Settings(_env_file=None, discord_webhook_url=url)
    assert url not in str(error.value)
    assert "synthetic_token" not in repr(error.value)


def test_environment_wins_over_local_example_file(monkeypatch, tmp_path):
    sample = tmp_path / "sample.env"
    sample.write_text("DISCORD_WEBHOOK_URL=invalid_placeholder\n", encoding="utf-8")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", SYNTHETIC_WEBHOOK)
    assert Settings(_env_file=sample).require_webhook().get_secret_value() == SYNTHETIC_WEBHOOK


def test_load_configuration_failure_is_sanitized(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "invalid_secret_value")
    with pytest.raises(PublishingConfigurationError) as error:
        load_settings()
    assert "invalid_secret_value" not in str(error.value)
