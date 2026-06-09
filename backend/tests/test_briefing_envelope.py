import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sitele"))
import hanwha_report_text as h


def _fake_llm_json(slot):
    import report_schema as rs
    blocks = [{"id": b["id"], "body": ("문단" if b["type"] == "paragraph"
              else ["a", "b", "c"] if b["type"] == "bullets"
              else [{"k": "VIX", "v": "16.1", "tone": "neutral"}])}
              for b in rs.SLOT_BLOCKS[slot]]
    return '{"title":"주도·반응·판단","stance":"RISK-ON","headline":"요약","blocks":' + str(blocks).replace("'", '"') + '}'


def test_envelope_per_slot(monkeypatch):
    for slot in ("premarket", "intraday", "close"):
        monkeypatch.setattr(h.os, "environ", {"ANTHROPIC_API_KEY": ""})
        monkeypatch.setattr(h, "_call_via_codex", lambda *a, **k: _fake_llm_json(slot))
        env = h.generate_report_sections(slot, {"kr_indices": {"kospi": {"close": 2700}}})
        import report_schema as _rs
        assert env["slot"] == slot and len(env["blocks"]) == len(_rs.SLOT_BLOCKS[slot])
        assert env["stance"] == "RISK-ON"
        assert {"title", "key_issue", "news_flow"} <= set(env["legacy"])
        assert env["as_of"]


def test_envelope_fallback_when_no_llm(monkeypatch):
    monkeypatch.setattr(h.os, "environ", {"ANTHROPIC_API_KEY": ""})
    monkeypatch.setattr(h, "_call_via_codex", lambda *a, **k: "")
    env = h.generate_report_sections("close", {})
    import report_schema as _rs
    assert len(env["blocks"]) == len(_rs.SLOT_BLOCKS["close"]) and env["legacy"]["title"]
