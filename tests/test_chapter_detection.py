"""Chapter Detection: spine != chapter; logical titles only; TOC regenerated."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub

from src.epub.generator import generate_epub
from src.models.blocks import BlockType, ContentBlock
from src.parsers.epub_parser import (
    _assign_chapters,
    _guess_title,
    _is_technical_filename,
    _looks_like_chapter_title,
    _title_from_blocks,
    detect_chapters,
    parse_epub,
)


def test_technical_filenames_detected():
    assert _is_technical_filename("P001.xhtml")
    assert _is_technical_filename("p002")
    assert _is_technical_filename("p-005")
    assert _is_technical_filename("p-006.xhtml")
    assert _is_technical_filename("item001.xhtml")
    assert _is_technical_filename("item12")
    assert _is_technical_filename("chap_01.xhtml")
    assert _is_technical_filename("chap_0004")
    assert _is_technical_filename("chap_0004.xhtml")
    assert _is_technical_filename("section1")
    assert _is_technical_filename("page-12")
    assert not _is_technical_filename("第一章")
    assert not _is_technical_filename("第一話　試著把青梅竹馬變成炮友")
    assert not _is_technical_filename("Chapter One")
    assert not _is_technical_filename("prologue")
    assert not _is_technical_filename("尾聲")
    assert not _is_technical_filename("幕間　佐倉花戀①")


def test_looks_like_chapter_title_patterns():
    assert _looks_like_chapter_title("第一話　試著把青梅竹馬變成炮友")
    assert _looks_like_chapter_title("第二話　試著讓青梅竹馬隔著窗戶自慰")
    assert _looks_like_chapter_title("幕間　佐倉花戀①")
    assert _looks_like_chapter_title("第七話　試著和青梅竹馬無套做愛")
    assert _looks_like_chapter_title("尾聲")
    assert _looks_like_chapter_title("追加SS　試著和青梅竹馬拍影片")
    assert _looks_like_chapter_title("第一章 黎明")
    assert not _looks_like_chapter_title("p-005")
    assert not _looks_like_chapter_title("這是很長的正文段落" * 5)
    assert not _looks_like_chapter_title("第一話正文續頁")
    assert not _looks_like_chapter_title("幕間正文")


def test_guess_title_ignores_technical_fallback():
    soup = BeautifulSoup("<html><body><p>Only body text.</p></body></html>", "lxml")
    assert _guess_title(soup, "P001.xhtml") is None
    assert _guess_title(soup, "item001.xhtml") is None
    assert _guess_title(soup, "p-005.xhtml") is None
    assert _guess_title(soup, "chap_0004.xhtml") is None


def test_guess_title_prefers_heading():
    soup = BeautifulSoup(
        "<html><body><h1>第一章 黎明</h1><p>正文</p></body></html>", "lxml"
    )
    assert _guess_title(soup, "P001.xhtml") == "第一章 黎明"


def test_title_from_blocks_heading():
    blocks = [
        ContentBlock(id="h0", type=BlockType.HEADING, order=0, text="第二章", level=1),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="內容"),
    ]
    assert _title_from_blocks(blocks) == "第二章"


def test_assign_chapters_never_uses_p001():
    blocks_a = [
        ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=0, text="續寫文字"),
    ]
    blocks_b = [
        ContentBlock(id="h0", type=BlockType.HEADING, order=0, text="第一章", level=1),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="開始"),
    ]
    chapters = _assign_chapters(
        [
            (None, blocks_a),
            ("第一章", blocks_b),
        ]
    )
    for ch in chapters:
        assert "P00" not in ch.title
        assert not _is_technical_filename(ch.title)
        assert not ch.title.startswith("Chapter ")
    assert any(ch.title == "第一章" for ch in chapters)


def test_multiple_chapters_inside_one_spine_slice():
    blocks = [
        ContentBlock(id="t1", type=BlockType.PARAGRAPH, order=0, text="第一話　開端"),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="正文甲"),
        ContentBlock(id="t2", type=BlockType.PARAGRAPH, order=2, text="第二話　繼續"),
        ContentBlock(id="p2", type=BlockType.PARAGRAPH, order=3, text="正文乙"),
        ContentBlock(id="t3", type=BlockType.PARAGRAPH, order=4, text="幕間　插曲"),
        ContentBlock(id="p3", type=BlockType.PARAGRAPH, order=5, text="幕間正文"),
    ]
    chapters = detect_chapters(blocks)
    assert len(chapters) == 3
    assert chapters[0].title.startswith("第一話")
    assert chapters[1].title.startswith("第二話")
    assert chapters[2].title.startswith("幕間")
    assert len(chapters) != 1


def test_one_chapter_spans_multiple_spine_slices():
    flat = [
        ContentBlock(id="t1", type=BlockType.HEADING, order=0, text="第一章", level=1),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="第一頁正文"),
        ContentBlock(id="p2", type=BlockType.PARAGRAPH, order=2, text="第二頁續寫"),
        ContentBlock(id="p3", type=BlockType.PARAGRAPH, order=3, text="第三頁續寫"),
    ]
    chapters = detect_chapters(flat)
    assert len(chapters) == 1
    assert chapters[0].title == "第一章"
    assert len(chapters[0].blocks) == 4


def test_spine_count_not_equal_chapter_count():
    raw = [
        (None, [ContentBlock(id="a", type=BlockType.PARAGRAPH, order=0, text="封面文字")]),
        ("第一話　標題甲", [
            ContentBlock(id="b", type=BlockType.PARAGRAPH, order=0, text="第一話　標題甲"),
            ContentBlock(id="c", type=BlockType.PARAGRAPH, order=1, text="甲正文"),
        ]),
        (None, [ContentBlock(id="d", type=BlockType.PARAGRAPH, order=0, text="甲正文續")]),
        ("第二話　標題乙", [
            ContentBlock(id="e", type=BlockType.PARAGRAPH, order=0, text="第二話　標題乙"),
            ContentBlock(id="f", type=BlockType.PARAGRAPH, order=1, text="乙正文"),
        ]),
        (None, [ContentBlock(id="g", type=BlockType.PARAGRAPH, order=0, text="乙續")]),
    ]
    spine_count = len(raw)
    chapters = _assign_chapters(raw)
    assert spine_count == 5
    assert len(chapters) == 2
    assert chapters[0].title.startswith("第一話")
    assert chapters[1].title.startswith("第二話")


def test_detect_light_novel_episode_titles():
    titles = [
        "第一話　試著把青梅竹馬變成炮友",
        "第二話　試著讓青梅竹馬隔著窗戶自慰",
        "幕間　佐倉花戀①",
        "第三話　試著把青梅竹馬帶進汽車旅館",
        "第七話　試著和青梅竹馬無套做愛",
        "尾聲",
        "追加SS　試著和青梅竹馬拍影片",
    ]
    flat = []
    for i, t in enumerate(titles):
        flat.append(ContentBlock(id=f"t{i}", type=BlockType.PARAGRAPH, order=len(flat), text=t))
        flat.append(ContentBlock(id=f"p{i}", type=BlockType.PARAGRAPH, order=len(flat), text=f"正文段落 {i}"))
    chapters = detect_chapters(flat)
    assert len(chapters) == len(titles)
    for ch, expected in zip(chapters, titles):
        assert ch.title == expected
        assert not _is_technical_filename(ch.title)


def test_toc_labels_as_soft_signal_not_copied():
    flat = [
        ContentBlock(id="p0", type=BlockType.PARAGRAPH, order=0, text="第一話　真實標題"),
        ContentBlock(id="p1", type=BlockType.PARAGRAPH, order=1, text="正文"),
    ]
    toc = ["第一話　真實標題", "幽靈目錄項永不出現"]
    chapters = detect_chapters(flat, toc_labels=toc)
    titles = [c.title for c in chapters]
    assert "第一話　真實標題" in titles
    assert "幽靈目錄項永不出現" not in titles


def _write_epub(path: Path, documents, nav_labels=None) -> None:
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("Test Novel")
    book.set_language("zh")
    book.add_author("Test Author")
    items = []
    for file_name, body in documents:
        ch = epub.EpubHtml(title=file_name, file_name=file_name, lang="zh")
        ch.set_content(
            f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{body}</body></html>'
        )
        book.add_item(ch)
        items.append(ch)
    book.spine = ["nav"] + items
    if nav_labels:
        book.toc = tuple(
            epub.Link(items[i].file_name, label, f"toc{i}")
            for i, label in enumerate(nav_labels)
            if i < len(items)
        )
    else:
        book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


def test_parse_epub_p001_not_title(tmp_path: Path):
    path = tmp_path / "novel.epub"
    _write_epub(
        path,
        [
            ("P001.xhtml", "<p>這是延續段落，沒有標題。</p>"),
            ("P002.xhtml", "<h1>第一章</h1><p>正文開始。</p>"),
            ("item001.xhtml", "<p>又一段。</p>"),
        ],
    )
    result = parse_epub(path, assets_dir=tmp_path / "assets")
    titles = [ch.title for ch in result.book.chapters]
    for t in titles:
        assert "P001" not in t
        assert "P002" not in t
        assert "item001" not in t.lower()
        assert not _is_technical_filename(t)
        assert not t.startswith("Chapter ")
    assert any("第一章" in t for t in titles)
    assert len(result.book.chapters) == 1


def test_parse_epub_page_labels_not_chapters(tmp_path: Path):
    """Exact user failure case: p-005 / p-006 / chap_0004 must not become titles."""
    path = tmp_path / "paged.epub"
    _write_epub(
        path,
        [
            ("p-005.xhtml", "<p>第一話　試著開始</p><p>第一頁正文</p>"),
            ("p-006.xhtml", "<p>第一話正文續頁</p>"),
            ("p-007.xhtml", "<p>第二話　下一章</p><p>第二話正文</p>"),
            ("chap_0004.xhtml", "<p>第二話再續</p>"),
        ],
    )
    result = parse_epub(path, assets_dir=tmp_path / "assets")
    chapters = result.book.chapters
    assert len(chapters) == 2
    assert chapters[0].title.startswith("第一話")
    assert chapters[1].title.startswith("第二話")
    for ch in chapters:
        assert "p-005" not in ch.title.lower()
        assert "p-006" not in ch.title.lower()
        assert "p-007" not in ch.title.lower()
        assert "chap_0004" not in ch.title.lower()
        assert not ch.title.startswith("Chapter ")
        assert not _is_technical_filename(ch.title)
    assert len(chapters) != 4


def test_generated_toc_uses_logical_titles(tmp_path: Path):
    path = tmp_path / "ln.epub"
    _write_epub(
        path,
        [
            ("p-001.xhtml", "<p>第一話　試著把青梅竹馬變成炮友</p><p>正文一</p>"),
            ("p-002.xhtml", "<p>續頁</p>"),
            ("p-003.xhtml", "<p>幕間　佐倉花戀①</p><p>幕間正文</p>"),
            ("p-004.xhtml", "<p>尾聲</p><p>結尾</p>"),
        ],
    )
    result = parse_epub(path, assets_dir=tmp_path / "assets")
    out = tmp_path / "normalized.epub"
    generate_epub(result.book, out)
    gen = epub.read_epub(str(out))
    item_doc = getattr(epub, "ITEM_DOCUMENT", 9)
    docs = list(gen.get_items_of_type(item_doc))
    content_docs = [d for d in docs if "nav" not in (d.get_name() or "").lower()]
    assert len(content_docs) == len(result.book.chapters)
    titles = [ch.title for ch in result.book.chapters]
    assert any("第一話" in t for t in titles)
    assert any("幕間" in t for t in titles)
    assert any("尾聲" in t for t in titles)
    for t in titles:
        assert not _is_technical_filename(t)
        assert not t.startswith("Chapter ")
    for d in content_docs:
        ht = (getattr(d, "title", None) or "").strip()
        if not ht:
            continue
        assert not _is_technical_filename(ht), f"technical title leaked: {ht!r}"
        assert "p-00" not in ht.lower()
        assert not ht.lower().startswith("chap_")
        assert not ht.startswith("Chapter ")


def test_user_case_light_novel_toc_titles(tmp_path: Path):
    """Source TOC has real logical titles; body has titles as paragraphs across page files."""
    titles = [
        "第一話　試著把青梅竹馬變成炮友",
        "第二話　試著讓青梅竹馬隔著窗戶自慰",
        "幕間　佐倉花戀①",
        "第三話　試著把青梅竹馬帶進汽車旅館",
        "第七話　試著和青梅竹馬無套做愛",
        "尾聲",
        "追加SS　試著和青梅竹馬拍影片",
    ]
    documents = []
    page = 1
    for t in titles:
        documents.append(
            (f"p-{page:03d}.xhtml", f"<p>{t}</p><p>本章開頭正文。</p>")
        )
        page += 1
        documents.append(
            (f"p-{page:03d}.xhtml", f"<p>本章續頁內容。</p>")
        )
        page += 1
    path = tmp_path / "real_ln.epub"
    _write_epub(path, documents, nav_labels=titles)
    result = parse_epub(path, assets_dir=tmp_path / "assets")
    chapters = result.book.chapters
    assert len(chapters) == len(titles)
    assert len(chapters) != len(documents)
    for ch, expected in zip(chapters, titles):
        assert ch.title == expected
        assert not _is_technical_filename(ch.title)
        assert not ch.title.startswith("Chapter ")
    out = tmp_path / "out.epub"
    generate_epub(result.book, out)
    gen = epub.read_epub(str(out))
    for link in gen.toc or []:
        label = getattr(link, "title", "") or ""
        assert not _is_technical_filename(label)
        assert "p-" not in label.lower()
        assert "chap_" not in label.lower()
