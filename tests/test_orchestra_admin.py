"""
tests.test_orchestra_admin — CRUD de la orquesta sobre archivo temporal.

Nunca tocamos el ``config/agents.json`` real. Monkeypatcheamos la ruta
a un ``tmp_path`` para que cada test arranque desde un archivo limpio.
"""

from __future__ import annotations

import json

import pytest

from agent import orchestra_admin


@pytest.fixture
def tmp_agents(tmp_path, monkeypatch):
    """Redirige el path de agents.json a un tmpfile vacío."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"agents": {}}), encoding="utf-8")
    monkeypatch.setattr(orchestra_admin, "_AGENTS_PATH", path)
    # Cada test parte de cero — invalidamos el cache del registry también.
    from agent import registry as reg_mod
    reg_mod.reset_cache()
    yield path


# ── Validación de inputs ───────────────────────────────────────────────────

def test_id_invalido_lanza_valueerror(tmp_agents):
    with pytest.raises(ValueError, match="snake_case"):
        orchestra_admin.upsert_agent("Mal-ID", {"provider": "gemini", "model": "x"})


def test_provider_desconocido_rechazado(tmp_agents):
    with pytest.raises(ValueError, match="provider"):
        orchestra_admin.upsert_agent("foo", {"provider": "skynet", "model": "x"})


def test_temperatura_fuera_de_rango_rechazada(tmp_agents):
    with pytest.raises(ValueError, match="temperature"):
        orchestra_admin.upsert_agent(
            "foo", {"provider": "gemini", "model": "x", "temperature": 5},
        )


def test_falta_provider_o_model_rechazado(tmp_agents):
    with pytest.raises(ValueError, match="provider.*model"):
        orchestra_admin.upsert_agent("foo", {"role": "Sin modelo"})


# ── Create / read ──────────────────────────────────────────────────────────

def test_create_persiste_con_defaults(tmp_agents):
    saved = orchestra_admin.upsert_agent(
        "translator",
        {"provider": "gemini", "model": "gemini-2.5-flash", "role": "Traductor"},
    )
    # Defaults aplicados
    assert saved["enabled"] is True
    assert saved["tools"] == []
    assert saved["temperature"] == 0.5
    assert saved["role"] == "Traductor"

    # En disco también
    disk = json.loads(tmp_agents.read_text(encoding="utf-8"))
    assert "translator" in disk["agents"]


# ── Update parcial ─────────────────────────────────────────────────────────

def test_update_es_patch_parcial(tmp_agents):
    orchestra_admin.upsert_agent(
        "translator",
        {
            "provider": "gemini", "model": "gemini-2.5-flash",
            "system": "Traduces lenguas humanas.", "temperature": 0.4,
        },
    )
    # Solo cambio el modelo; el system y la temperatura deben sobrevivir.
    updated = orchestra_admin.upsert_agent(
        "translator",
        {"model": "gemini-2.5-flash-lite"},
    )
    assert updated["model"] == "gemini-2.5-flash-lite"
    assert updated["system"] == "Traduces lenguas humanas."
    assert updated["temperature"] == 0.4


# ── Delete ─────────────────────────────────────────────────────────────────

def test_delete_quita_agente(tmp_agents):
    orchestra_admin.upsert_agent(
        "tmpguy", {"provider": "gemini", "model": "gemini-2.5-flash"},
    )
    assert orchestra_admin.delete_agent("tmpguy") is True
    assert orchestra_admin.get_agent_spec("tmpguy") is None


def test_delete_director_prohibido(tmp_agents):
    orchestra_admin.upsert_agent(
        "director", {"provider": "gemini", "model": "gemini-2.5-flash"},
    )
    with pytest.raises(ValueError, match="Director"):
        orchestra_admin.delete_agent("director")


def test_delete_inexistente_devuelve_false(tmp_agents):
    assert orchestra_admin.delete_agent("ghost") is False


# ── Integración con registry ───────────────────────────────────────────────

def test_upsert_invalida_cache_del_registry(tmp_agents):
    from agent import registry as reg_mod
    # Apuntamos el registry al mismo path temporal.
    monkey_path = tmp_agents
    real_loader = reg_mod._load_agents_config

    def fake_loader():
        return json.loads(monkey_path.read_text(encoding="utf-8"))
    reg_mod._load_agents_config = fake_loader  # type: ignore[assignment]
    try:
        reg_mod.reset_cache()
        assert reg_mod.list_agents() == []

        orchestra_admin.upsert_agent(
            "writer",
            {"provider": "gemini", "model": "gemini-2.5-flash", "role": "Redactor"},
        )
        # La invalidación se hizo dentro del upsert; la próxima list_agents
        # debe ver el nuevo agente sin que nadie llame a reset_cache aparte.
        ids = {a.id for a in reg_mod.list_agents()}
        assert "writer" in ids
    finally:
        reg_mod._load_agents_config = real_loader  # type: ignore[assignment]
        reg_mod.reset_cache()
