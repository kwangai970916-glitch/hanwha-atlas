from __future__ import annotations
import json
from app.ideation.stream import RunStream, STAGE_META


def test_emit_writes_monotonic_jsonl(tmp_path):
    s = RunStream(tmp_path)
    s.emit('Macro PM', 'discovery', 'VIX 16.2 안정', icon='activity')
    s.emit('Bull 리서처', 'sector_debate', '반도체 레인 유망' * 40)  # 길이 초과
    lines = (tmp_path / 'messages.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 2
    m0, m1 = json.loads(lines[0]), json.loads(lines[1])
    assert m0['idx'] == 0 and m1['idx'] == 1
    assert m0['agent'] == 'Macro PM' and m0['stage'] == 'discovery' and m0['icon'] == 'activity'
    assert len(m1['text']) <= 240  # 240자 절단
    assert 'ts' in m0


def test_set_stage_writes_status_with_label_and_step(tmp_path):
    s = RunStream(tmp_path)
    s.set_stage('sector_debate', keywords='AI 반도체')
    st = json.loads((tmp_path / 'status.json').read_text(encoding='utf-8'))
    assert st['stage'] == 'sector_debate'
    assert st['step'] == STAGE_META['sector_debate'][0]
    assert st['stage_label'] == STAGE_META['sector_debate'][1]
    assert st['keywords'] == 'AI 반도체'


def test_write_decision_roundtrip(tmp_path):
    s = RunStream(tmp_path)
    s.write_decision({'engine': 'ideation_committee', 'top_picks': []})
    d = json.loads((tmp_path / 'decision.json').read_text(encoding='utf-8'))
    assert d['engine'] == 'ideation_committee'
