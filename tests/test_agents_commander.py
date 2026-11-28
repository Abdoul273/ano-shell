"""Tests unitaires rapides pour le Commandant Katana AI (ano-agents / caelestia-agents)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_BIN = ROOT / "bin" / ("ano-agents" if (ROOT / "bin" / "ano-agents").is_file() else "caelestia-agents")


def _load_agents():
    loader = importlib.machinery.SourceFileLoader("agents_under_test", str(AGENTS_BIN))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _check_gemini_schema(node: dict) -> None:
    assert node.get("type") in {"OBJECT", "STRING", "INTEGER", "NUMBER", "BOOLEAN", "ARRAY"}
    if node["type"] == "OBJECT":
        props = node.get("properties")
        assert isinstance(props, dict) and len(props) > 0, f"OBJECT sans properties : {node}"
        for child in props.values():
            _check_gemini_schema(child)
    elif node["type"] == "ARRAY":
        assert isinstance(node.get("items"), dict), f"ARRAY sans items : {node}"
        _check_gemini_schema(node["items"])


def test_workspace_normalization():
    mod = _load_agents()
    assert mod._norm_ws("2") == "2"
    assert mod._norm_ws("bureau 2") == "2"
    assert mod._norm_ws("deuxième") == "2"
    assert mod._norm_ws("suivant") == "+1"
    assert mod._norm_ws("précédent") == "-1"
    assert mod._norm_ws("special") == "special"


def test_failure_detection():
    mod = _load_agents()
    assert mod._looks_like_failure("Aucune fenêtre ne correspond à '2'.") is True
    assert mod._looks_like_failure("Erreur hypr_orchestrator: introuvable") is True
    assert mod._looks_like_failure("Changement vers le bureau 2 non confirmé.") is True
    assert mod._looks_like_failure("Bureau actif confirmé : 2.") is False
    assert mod._looks_like_failure("Compilation terminée : 0 erreur.") is False


def test_native_tool_declarations_valid_for_gemini():
    mod = _load_agents()
    decls = mod._native_tool_declarations()
    names = {d["name"] for d in decls}
    for required in (
        "hypr_workspace",
        "hypr_windows",
        "shell_control",
        "system_control",
        "run_shell",
        "agent_dispatch",
        "agent_set_model",
        "agent_list_models",
        "agent_send",
        "agent_close",
        "agent_detail",
        "memory_save",
        "memory_search",
    ):
        assert required in names, f"Outil natif manquant : {required}"
    send_decl = next(d for d in decls if d["name"] == "agent_send")
    assert "/set model" not in send_decl["description"]
    for d in decls:
        assert d.get("description")
        if "parameters" in d:
            _check_gemini_schema(d["parameters"])


def test_resolve_agy_models_and_efforts():
    mod = _load_agents()
    catalog = mod._AGY_FALLBACK_MODELS

    # Faute courante + effort en français ("hydrogent en effort moyen")
    r1 = mod.resolve_agent_model("agy", "hydrogent", "moyen", agy_models=catalog)
    assert r1["ok"] is True
    assert r1["display"] == "Gemini 4 Hydrogen (Medium)"
    assert r1["slug"] == "gemini-4-hydrogen-medium"
    assert r1["slash_cmd"] == "/model Gemini 4 Hydrogen (Medium)"

    # Tout dans le champ model
    r2 = mod.resolve_agent_model("agy", "hydrogen en effort moyen", "", agy_models=catalog)
    assert r2["ok"] is True and r2["slash_cmd"] == "/model Gemini 4 Hydrogen (Medium)"

    # Changement d'effort depuis un modèle déjà doté d'un effort entre parenthèses
    r3 = mod.resolve_agent_model("agy", "Gemini 4 Neon (High)", "faible", agy_models=catalog)
    assert r3["ok"] is True and r3["display"] == "Gemini 4 Neon (Low)"

    # XHigh vs modèles sans XHigh (Carbon -> High)
    r4 = mod.resolve_agent_model("agy", "neon", "xhigh", agy_models=catalog)
    assert r4["ok"] is True and r4["display"] == "Gemini 4 Neon (XHigh)"
    r5 = mod.resolve_agent_model("agy", "carbon", "max", agy_models=catalog)
    assert r5["ok"] is True and r5["display"] == "Gemini 4 Carbon (High)"

    # Claude Opus / Orchestrator / Flash
    r6 = mod.resolve_agent_model("agy", "opus", "high", agy_models=catalog)
    assert r6["ok"] is True and r6["display"] == "Claude Opus 5.5 (High)"
    r7 = mod.resolve_agent_model("agy", "orchestrator neon", "", agy_models=catalog)
    assert r7["ok"] is True and r7["display"] == "Orchestrator (Neon)"
    r8 = mod.resolve_agent_model("agy", "flash", "low", agy_models=catalog)
    assert r8["ok"] is True and r8["display"] == "Gemini 3.8 Flash (Low)"

    # Modèle inexistant -> échec propre
    bad = mod.resolve_agent_model("agy", "modele-imaginaire-xyz", "medium", agy_models=catalog)
    assert bad["ok"] is False


def test_parse_agy_models_output():
    mod = _load_agents()
    raw = "\r⠋ Fetching available models...\rgemini-4-hydrogen-medium       Gemini 4 Hydrogen (Medium)\ngemini-4-neon-high             Gemini 4 Neon (High)\n"
    parsed = mod._parse_agy_models_output(raw)
    assert parsed == [
        ("gemini-4-hydrogen-medium", "Gemini 4 Hydrogen (Medium)"),
        ("gemini-4-neon-high", "Gemini 4 Neon (High)"),
    ]


def test_other_engines_model_resolution_and_guardrails():
    mod = _load_agents()
    rc = mod.resolve_agent_model("claude", "opus", "moyen")
    assert rc["ok"] is True and rc["slash_cmd"] == "/model opus" and rc["effort"] == "medium"

    rx = mod.resolve_agent_model("codex", "gpt-5.6-terra", "haut")
    assert rx["ok"] is True and rx["slug"] == "gpt-5.6-terra" and rx["effort"] == "high"

    rp = mod.resolve_agent_model("copilot", "gpt-5.6-sol", "high")
    assert rp["ok"] is True and rp["slash_cmd"] == "/model gpt-5.6-sol"

    # Antigravity App (GUI Electron) : honnête (ne prétend pas avoir changé le menu déroulant)
    ag_res = mod.set_agent_model("hydrogen", effort="moyen", kind="antigravity")
    assert ag_res["ok"] is False
    assert "Gemini 4 Hydrogen (Medium)" in ag_res["detail"]


def test_sanitize_schema_handles_empty_objects_and_arrays():
    mod = _load_agents()
    bad_obj = mod._sanitize_schema({"type": "object", "properties": {}, "additionalProperties": True})
    assert bad_obj["type"] == "STRING"
    arr = mod._sanitize_schema({"type": "array"})
    assert arr["type"] == "ARRAY" and arr["items"]["type"] == "STRING"


def test_run_shell_blocks_catastrophic_commands():
    mod = _load_agents()
    ok, msg = mod.tool_run_shell("rm -rf /")
    assert ok is False
    assert "bloquée" in msg.lower()


def test_standalone_memory_roundtrip(tmp_path, monkeypatch):
    mod = _load_agents()
    monkeypatch.setattr(mod, "ANO_DIR", tmp_path / "absent-ano")
    monkeypatch.setattr(mod, "CHAT_HISTORY", tmp_path / "chat.json")
    ok, _ = mod.ano_memory_save("editeur", "Neovim", "preferences")
    assert ok is True
    found = mod.ano_memory_search("Neovim")
    assert "Neovim" in found


def test_models_catalog_structure_and_efforts(monkeypatch):
    mod = _load_agents()
    monkeypatch.setattr(mod, "list_agy_models", lambda force_refresh=False: list(mod._AGY_FALLBACK_MODELS))

    cat = mod.list_models_catalog("agy")
    assert cat["kind"] == "agy"
    assert cat["canApplyLive"] is True
    assert "high" in cat["efforts"]
    neon = next(g for g in cat["groups"] if g["base"] == "Gemini 4 Neon")
    assert "high" in neon["variants"] and "xhigh" in neon["variants"]

    ag_gui = mod.list_models_catalog("antigravity")
    assert ag_gui["canApplyLive"] is False

    cl = mod.list_models_catalog("claude")
    assert [g["slug"] for g in cl["groups"]] == ["opus", "sonnet", "haiku"]


def test_clean_terminal_screen_strips_ansi_and_caps_lines():
    mod = _load_agents()
    raw = "\x1b[32mOK\x1b[0m ligne 1\r\n\x1b]0;titre\x07ligne 2\n\n\n"
    txt, count = mod._clean_terminal_screen(raw, max_lines=50)
    assert txt == "OK ligne 1\nligne 2"
    assert count == 2


def test_git_file_diff_and_untracked_and_traversal_guard(tmp_path):
    import subprocess

    mod = _load_agents()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)

    f = tmp_path / "demo.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "demo.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)

    # Modification suivie + nouveau fichier non suivi
    f.write_text("a = 1\nb = 42\nc = 3\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("bonjour\nligne 2\n", encoding="utf-8")

    entries = mod.git_status_entries(str(tmp_path))
    paths = {e["path"] for e in entries}
    assert "demo.py" in paths and "notes.txt" in paths

    d_tracked = mod.git_file_diff(str(tmp_path), "demo.py")
    assert d_tracked["ok"] is True
    assert d_tracked["added"] >= 2 and d_tracked["removed"] >= 1
    assert any(ln["kind"] == "add" and "b = 42" in ln["text"] for ln in d_tracked["lines"])

    d_untracked = mod.git_file_diff(str(tmp_path), "notes.txt")
    assert d_untracked["ok"] is True and d_untracked["untracked"] is True
    assert d_untracked["added"] == 2

    d_escape = mod.git_file_diff(str(tmp_path), "../etc/passwd")
    assert d_escape["ok"] is False


def test_agent_detail_targeted_skips_full_snapshot(tmp_path, monkeypatch):
    mod = _load_agents()

    def _boom(_state):
        raise AssertionError("snapshot() ne doit pas être appelé en mode ciblé")

    monkeypatch.setattr(mod, "snapshot", _boom)
    det = mod.agent_detail("agy:inexistant", kind="agy", cwd=str(tmp_path), pid=0)
    assert det["id"] == "agy:inexistant"
    assert isinstance(det["events"], list) and isinstance(det["gitFiles"], list)
