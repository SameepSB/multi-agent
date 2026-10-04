from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_exposes_only_loopback_api():
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("    ports:") == 1
    assert "127.0.0.1:${API_PORT:-8080}:8080" in compose
    assert 'expose: ["5001"]' in compose
    assert 'expose: ["5003"]' in compose


def _terraform(name: str) -> str:
    return (ROOT / "deploy" / "terraform" / name).read_text(encoding="utf-8")


def test_azure_api_is_external_but_worker_ingress_is_internal():
    apps = _terraform("apps.tf")
    assert apps.count("external_enabled           = true") == 1
    assert apps.count("external_enabled           = false") == 1
    assert apps.count("allow_insecure_connections = false") == 2


def test_azure_container_apps_define_process_commands():
    apps = _terraform("apps.tf")
    assert apps.count('command = ["uvicorn"]') == 2
    assert "travel_comparator.api.main:create_app" in apps
    assert "travel_comparator.agents.${each.value.module}:create_app" in apps
    assert 'module = "weather_server"' in apps
    assert 'module = "travel_server"' in apps


def test_azure_uses_separate_identities_and_api_only_key_vault_secret():
    main = _terraform("main.tf")
    apps = _terraform("apps.tf")
    for name in ("api", "weather", "travel"):
        assert f'resource "azurerm_user_assigned_identity" "{name}"' in main
    assert 'resource "azurerm_role_assignment" "api_key_vault_read"' in main
    worker = apps[apps.index('"worker"') : apps.index('resource "azurerm_container_app" "api"')]
    assert "openai-api-key" not in worker
    assert apps.count("openai-api-key") == 2


def test_production_promotion_requires_and_reuses_full_digest():
    workflow = (ROOT / ".github" / "workflows" / "promote-production.yml").read_text(
        encoding="utf-8"
    )
    assert "environment: production" in workflow
    assert "sha256:[0-9a-f]{64}" in workflow
    assert 'image_ref="${registry}/travel-comparator@${IMAGE_DIGEST}"' in workflow
    assert 'docker pull "$image_ref"' in workflow
