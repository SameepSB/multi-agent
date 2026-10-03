from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_exposes_only_loopback_api():
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("    ports:") == 1
    assert "127.0.0.1:${API_PORT:-8080}:8080" in compose
    assert 'expose: ["5001"]' in compose
    assert 'expose: ["5003"]' in compose


def test_azure_api_is_external_but_worker_ingress_is_internal():
    api = (ROOT / "deploy" / "bicep" / "api-app.bicep").read_text(encoding="utf-8")
    worker = (ROOT / "deploy" / "bicep" / "worker-app.bicep").read_text(encoding="utf-8")
    assert "external: true" in api
    assert "external: false" in worker
    assert "allowInsecure: false" in api
    assert "allowInsecure: false" in worker


def test_azure_container_apps_define_process_commands():
    root = ROOT / "deploy" / "bicep"
    main = (root / "main.bicep").read_text(encoding="utf-8")
    api = (root / "api-app.bicep").read_text(encoding="utf-8")
    worker = (root / "worker-app.bicep").read_text(encoding="utf-8")
    assert "command: ['uvicorn']" in api
    assert "travel_comparator.api.main:create_app" in api
    assert "param command array" in worker
    assert "command: command" in worker
    assert "travel_comparator.agents.weather_server:create_app" in main
    assert "travel_comparator.agents.travel_server:create_app" in main


def test_azure_uses_separate_identities_and_api_only_key_vault_secret():
    main = (ROOT / "deploy" / "bicep" / "main.bicep").read_text(encoding="utf-8")
    api = (ROOT / "deploy" / "bicep" / "api-app.bicep").read_text(encoding="utf-8")
    worker = (ROOT / "deploy" / "bicep" / "worker-app.bicep").read_text(encoding="utf-8")
    assert "resource apiIdentity" in main
    assert "resource weatherIdentity" in main
    assert "resource travelIdentity" in main
    assert "apiKeyVaultRead" in main
    assert "secretRef: 'openai-api-key'" in api
    assert "keyVaultUrl: openAiSecretUri" in api
    assert "openai-api-key" not in worker


def test_production_promotion_requires_and_reuses_full_digest():
    workflow = (ROOT / ".github" / "workflows" / "promote-production.yml").read_text(
        encoding="utf-8"
    )
    assert "environment: production" in workflow
    assert "sha256:[0-9a-f]{64}" in workflow
    assert 'image_ref="${registry}/travel-comparator@${IMAGE_DIGEST}"' in workflow
    assert 'docker pull "$image_ref"' in workflow
