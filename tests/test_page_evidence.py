import hashlib
import json
from report import ConversionReport, write_report
import convert


def test_report_binds_original_and_output(tmp_path):
    source = tmp_path / 'a.pdf'; source.write_bytes(b'original')
    out = tmp_path / 'a.md'; out.write_text('text')
    r = ConversionReport(source=str(source), output=str(out), method='marker')
    write_report(tmp_path / 'report.json', r)
    assert r.source_sha256 == hashlib.sha256(b'original').hexdigest()
    assert r.output_sha256 == hashlib.sha256(b'text').hexdigest()


def test_marker_mapping_distinguishes_read_and_inferred(tmp_path, monkeypatch):
    p = tmp_path / 'a.md'; p.write_text('fixture')
    monkeypatch.setattr(convert, '_marker_page_locators', lambda text: ([(i, 'body') for i in range(10, 21)], {10:'1',11:'2',12:'3',18:'9',19:'10',20:'11'}))
    r = ConversionReport(source='x', output=str(p), method='marker')
    convert._rewrite_marker_page_locators(p, r)
    assert r.page_map[0]['method'] == 'observed'
    assert r.page_map[3]['method'] == 'inferred'
    assert r.page_map[3]['page_printed'] == '4'
