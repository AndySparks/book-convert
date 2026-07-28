"""The never-dangle asset invariant (issue #34).

*The output never contains a reference to a file that does not exist.*

It was broken for a year in the place it mattered most. Marker writes its
figures as `_page_64_Figure_7.jpeg` beside the markdown in its scratch
directory; sourceconvert harvested `*.png` and `*.jpg` out of that directory —
never `*.jpeg` — and then deleted it, leaving every reference marker had
already written pointing at nothing. 1,140 dead references across 49 sources
downstream; ~92% of every converted source that should show a figure showed
none, with `quality_score: 1.0` on all of them.

These tests hold the invariant from both directions: the figures are written
by default, and when they are not written the references go with them. No
real marker run is involved — `fixtures.patch_marker` reproduces marker's
output *shape*, which is the only part of marker this behaviour depends on.
"""
import json
import shutil

import pytest

import assets
import convert
from tests import fixtures

pandoc_only = pytest.mark.skipif(
    shutil.which("pandoc") is None, reason="pandoc not installed"
)


def sidecar(md_path):
    return json.loads(
        md_path.with_suffix(".report.json").read_text(encoding="utf-8")
    )


# --- reference parsing -----------------------------------------------------


def test_iter_image_refs_finds_bare_and_pathed_targets():
    refs = assets.iter_image_refs(
        "intro\n\n![](_page_64_Figure_7.jpeg)\n\n![A cap](images/x.png)\n"
    )
    assert [r.target for r in refs] == ["_page_64_Figure_7.jpeg", "images/x.png"]
    assert [r.alt for r in refs] == ["", "A cap"]
    assert [r.line for r in refs] == [3, 5]


def test_iter_image_refs_handles_titles_and_angle_brackets():
    refs = assets.iter_image_refs('![a](x.png "A title")\n![b](<y z.png>)')
    assert [r.target for r in refs] == ["x.png", "y z.png"]


def test_remote_targets_are_not_local():
    assert not assets.is_local_target("https://example.com/x.png")
    assert not assets.is_local_target("data:image/png;base64,AAAA")
    assert not assets.is_local_target("//cdn.example.com/x.png")
    assert assets.is_local_target("_page_64_Figure_7.jpeg")
    assert assets.is_local_target("Book_images/x.png")


def test_strip_leaves_remote_references_alone(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("![](https://example.com/x.png)\n![](missing.png)\n")
    text, stripped = assets.strip_dangling_refs(md.read_text(), md)
    assert stripped == ["missing.png"]
    assert "https://example.com/x.png" in text
    assert "![](missing.png)" not in text


def test_strip_leaves_references_whose_file_exists(tmp_path):
    (tmp_path / "there.png").write_bytes(fixtures._ONE_PIXEL_PNG)
    md = tmp_path / "doc.md"
    md.write_text("![](there.png)\n![](gone.png)\n")
    text, stripped = assets.strip_dangling_refs(md.read_text(), md)
    # Selectivity: the sweep fired once, on exactly the one bad reference.
    assert stripped == ["gone.png"]
    assert "![](there.png)" in text


def test_rewrite_matches_on_basename_not_on_a_slash():
    """The old rewrite regex required a `/` in the target. Marker's bare
    `![](_page_64_Figure_7.jpeg)` has none, so it was never rewritten even
    on the path where the files had been found."""
    text, n = assets.rewrite_asset_refs(
        "![](_page_64_Figure_7.jpeg) and ![](sub/dir/other.png)",
        {"_page_64_Figure_7.jpeg": "_page_64_Figure_7.jpeg",
         "other.png": "other.png"},
        "Book_images",
    )
    assert n == 2
    assert "](Book_images/_page_64_Figure_7.jpeg)" in text
    assert "](Book_images/other.png)" in text


def test_harvest_collects_jpeg_not_just_jpg(tmp_path):
    """The one-character gap that caused issue #34."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    for name in ("a.jpeg", "b.JPG", "c.png", "d.md", "e.txt"):
        (scratch / name).write_bytes(b"x")
    found = {p.name for p in assets.collect_asset_files(scratch)}
    assert found == {"a.jpeg", "b.JPG", "c.png"}


def test_harvest_does_not_overwrite_on_a_name_collision(tmp_path):
    scratch = tmp_path / "scratch"
    (scratch / "one").mkdir(parents=True)
    (scratch / "two").mkdir()
    (scratch / "one" / "img.png").write_bytes(b"first")
    (scratch / "two" / "img.png").write_bytes(b"second")
    dest = tmp_path / "out_images"
    mapping = assets.harvest_assets(
        assets.collect_asset_files(scratch), dest
    )
    # Both files survived, under distinct names. Neither was overwritten.
    assert len(list(dest.iterdir())) == 2
    assert {p.read_bytes() for p in dest.iterdir()} == {b"first", b"second"}
    # References are matched by basename, so a shared basename is ambiguous
    # by construction: first one wins, and it points at a file that exists.
    assert mapping == {"img.png": "img.png"}
    assert (dest / "img.png").exists()


# --- marker: the backend that broke the invariant --------------------------


def test_marker_with_no_flags_writes_the_figures_it_references(tmp_path, monkeypatch):
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert)

    report = convert.convert_with_marker(pdf, out)
    md = out / f"{pdf.stem}.md"

    # The acceptance bar: zero dangling references.
    assert assets.count_dangling_refs(md) == 0

    # And the figures are actually there, not merely un-referenced.
    asset_dir = out / f"{pdf.stem}_images"
    assert sorted(p.name for p in asset_dir.iterdir()) == [
        "_page_3_Figure_1.jpeg", "_page_7_Figure_1.jpeg"
    ]
    assert report.extracted_assets == 2
    assert report.dangling_refs_stripped == 0

    # References were repointed into the asset directory.
    text = md.read_text(encoding="utf-8")
    assert f"]({pdf.stem}_images/_page_3_Figure_1.jpeg)" in text
    assert "](_page_3_Figure_1.jpeg)" not in text


def test_marker_that_loses_its_assets_does_not_dangle(tmp_path, monkeypatch):
    """The exact issue #34 shape: references emitted, files never written."""
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert, write_images=False)

    report = convert.convert_with_marker(pdf, out)
    md = out / f"{pdf.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert report.dangling_refs_stripped == 2
    assert report.assets == []
    # The sidecar says so out loud, rather than reporting quality 1.0 in
    # silence the way it did for a year.
    assert any("stripped 2 image reference" in w for w in report.warnings)
    # No image reference survives. The filename does, inside an HTML comment
    # that renders as nothing — a dropped figure should be recoverable by a
    # human reading the file, not silent.
    text = md.read_text(encoding="utf-8")
    assert assets.iter_image_refs(text) == []
    assert text.count("sourceconvert: image omitted") == 2


def test_marker_with_extraction_disabled_does_not_dangle(tmp_path, monkeypatch):
    """Route 2 explicitly: extraction off, and still zero dangling refs."""
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    # A marker that emits references anyway despite being told not to
    # extract. Real marker drops them; we do not depend on that.
    fixtures.patch_marker(monkeypatch, convert, emit_refs=True)

    report = convert.convert_with_marker(pdf, out, extract_images=False)
    md = out / f"{pdf.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert report.dangling_refs_stripped == 2
    assert not (out / f"{pdf.stem}_images").exists()
    # The surrounding prose is untouched; only the reference goes.
    assert "the one the rest of the chapter argues from" in md.read_text()


def test_reconverting_does_not_accumulate_stale_assets(tmp_path, monkeypatch):
    """The asset directory belongs to the current run, not to its ancestors."""
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()

    fixtures.patch_marker(monkeypatch, convert, pages=(3, 7))
    convert.convert_with_marker(pdf, out)
    fixtures.patch_marker(monkeypatch, convert, pages=(4,))
    report = convert.convert_with_marker(pdf, out)

    asset_dir = out / f"{pdf.stem}_images"
    assert [p.name for p in asset_dir.iterdir()] == ["_page_4_Figure_1.jpeg"]
    assert len(report.assets) == 1
    assert assets.count_dangling_refs(out / f"{pdf.stem}.md") == 0


def test_extraction_disabled_is_passed_through_to_marker(tmp_path, monkeypatch):
    pdf = fixtures.build_text_pdf(tmp_path, pages=1)
    out = tmp_path / "out"
    out.mkdir()
    seen = {}

    real_patch = fixtures.patch_marker

    def capture(monkeypatch_, module, **kw):
        real_patch(monkeypatch_, module, **kw)
        inner = module.subprocess.Popen

        def wrapper(cmd, *a, **k):
            seen["cmd"] = list(cmd)
            return inner(cmd, *a, **k)

        monkeypatch_.setattr(module.subprocess, "Popen", wrapper)

    capture(monkeypatch, convert)
    convert.convert_with_marker(pdf, out, extract_images=False)
    assert "--disable_image_extraction" in seen["cmd"]

    capture(monkeypatch, convert)
    convert.convert_with_marker(pdf, out)
    assert "--disable_image_extraction" not in seen["cmd"]


# --- pymupdf ---------------------------------------------------------------


def test_pymupdf_extracts_figures_by_default(tmp_path):
    pdf = fixtures.build_figure_pdf(tmp_path)
    out = tmp_path / "out"
    out.mkdir()

    report = convert.convert_with_pymupdf(pdf, out)
    md = out / f"{pdf.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert report.extracted_assets >= 1
    assert (out / f"{pdf.stem}_assets").is_dir()
    assert report.dangling_refs_stripped == 0


def test_pymupdf_with_extraction_disabled_emits_no_references(tmp_path):
    pdf = fixtures.build_figure_pdf(tmp_path)
    out = tmp_path / "out"
    out.mkdir()

    report = convert.convert_with_pymupdf(pdf, out, extract_images=False)
    md = out / f"{pdf.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert not (out / f"{pdf.stem}_assets").exists()
    assert report.assets == []


# --- the population the invariant must not touch ---------------------------


def test_text_only_conversion_is_unaffected(tmp_path):
    pdf = fixtures.build_text_pdf(tmp_path, pages=3)
    out = tmp_path / "out"
    out.mkdir()

    report = convert.convert_with_pymupdf(pdf, out)
    md = out / f"{pdf.stem}.md"
    text = md.read_text(encoding="utf-8")

    assert "Lorem ipsum dolor sit amet." in text
    assert "sourceconvert: image omitted" not in text
    assert report.assets == []
    assert report.dangling_refs_stripped == 0
    assert report.extracted_assets == 0
    assert sidecar(md)["assets"] == []


@pandoc_only
def test_epub_with_figures_has_no_dangling_references(tmp_path):
    """Pandoc references the epub's internal media for images it never
    writes, so an epub dangles by construction. The epub path takes route 2
    to the invariant: the references are stripped, not extracted."""
    epub = fixtures.build_figure_epub(tmp_path)
    out = tmp_path / "out"
    out.mkdir()

    report = convert.convert_with_pandoc(epub, out)
    md = out / f"{epub.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert report.dangling_refs_stripped == 2
    # The prose around them is untouched.
    text = md.read_text(encoding="utf-8")
    assert "She names the work before anyone touches it." in text
    assert "in words they can repeat." in text


@pandoc_only
def test_epub_without_figures_is_unaffected(tmp_path):
    epub = fixtures.build_semantic_epub(tmp_path)
    out = tmp_path / "out"
    out.mkdir()

    report = convert.convert_with_pandoc(epub, out)
    md = out / f"{epub.stem}.md"

    assert assets.count_dangling_refs(md) == 0
    assert report.dangling_refs_stripped == 0
    assert "sourceconvert: image omitted" not in md.read_text(encoding="utf-8")


# --- the manifest ----------------------------------------------------------


def test_manifest_shape(tmp_path, monkeypatch):
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert)

    convert.convert_with_marker(pdf, out)
    data = sidecar(out / f"{pdf.stem}.md")

    assert len(data["assets"]) == 2
    entry = data["assets"][0]
    assert set(entry) == {"path", "bytes", "references"}
    assert entry["path"] == f"{pdf.stem}_images/_page_3_Figure_1.jpeg"
    assert entry["bytes"] > 0
    assert len(entry["references"]) == 1
    ref = entry["references"][0]
    assert set(ref) == {"target", "alt", "line"}
    assert ref["target"] == entry["path"]
    # The count the issue asked for: assets vs references, checkable.
    assert data["extracted_assets"] == len(data["assets"]) == 2
    assert data["dangling_refs_stripped"] == 0


def test_manifest_records_an_asset_nothing_references(tmp_path, monkeypatch):
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert)
    convert.convert_with_marker(pdf, out)

    # An extracted-but-orphaned asset is information, not noise: it is the
    # signature of a reference that went missing somewhere upstream.
    asset_dir = out / f"{pdf.stem}_images"
    (asset_dir / "orphan.png").write_bytes(fixtures._ONE_PIXEL_PNG)
    report = convert.ConversionReport(
        source=str(pdf), output=str(out / f"{pdf.stem}.md"), method="marker"
    )
    convert._finalize_assets(report, asset_dir=asset_dir)

    orphan = [a for a in report.assets if a["path"].endswith("orphan.png")]
    assert len(orphan) == 1
    assert orphan[0]["references"] == []


def test_manifest_round_trip_relocates_every_asset(tmp_path, monkeypatch):
    """A consumer files the conversion elsewhere using ONLY the manifest.

    Nothing below looks at a filename, a suffix, or a `_page_N_Figure_M`
    pattern — which is the point. Marker can rename its output tomorrow and
    this consumer keeps working.
    """
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert)
    convert.convert_with_marker(pdf, out)

    md = out / f"{pdf.stem}.md"
    manifest = sidecar(md)["assets"]
    assert manifest

    # --- the consumer ---
    vault = tmp_path / "vault"
    (vault / "attachments").mkdir(parents=True)
    text = md.read_text(encoding="utf-8")
    for i, entry in enumerate(manifest):
        src = md.parent / entry["path"]
        new_name = f"source-figure-{i + 1}{src.suffix}"
        shutil.copy(src, vault / "attachments" / new_name)
        for ref in entry["references"]:
            text = text.replace(
                f"]({ref['target']})", f"](attachments/{new_name})"
            )
    filed = vault / "source.md"
    filed.write_text(text, encoding="utf-8")
    # --- end consumer ---

    assert assets.count_dangling_refs(filed) == 0
    refs = [r for r in assets.iter_image_refs(filed.read_text())
            if assets.is_local_target(r.target)]
    assert len(refs) == len(manifest)
    assert all(r.target.startswith("attachments/") for r in refs)


def test_manifest_line_numbers_survive_the_cleanup_pass(tmp_path, monkeypatch):
    """Cleanup rewrites the markdown after the backend built the manifest.
    A line number that describes the pre-cleanup text is a lie."""
    pdf = fixtures.build_text_pdf(tmp_path, pages=2)
    out = tmp_path / "out"
    out.mkdir()
    fixtures.patch_marker(monkeypatch, convert)

    report = convert._apply_cleanup(convert.convert_with_marker(pdf, out))
    md = out / f"{pdf.stem}.md"
    lines = md.read_text(encoding="utf-8").splitlines()

    for entry in report.assets:
        for ref in entry["references"]:
            assert ref["target"] in lines[ref["line"] - 1]
