from __future__ import annotations

from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from tsr_video_annotation_tool.web import get_browser_bundle_root


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.references.append(attributes["src"])
        if tag == "link" and attributes.get("rel") == "stylesheet" and attributes.get("href"):
            self.references.append(attributes["href"])
        if tag == "img" and attributes.get("src"):
            self.references.append(attributes["src"])


@contextmanager
def _static_server(directory: Path):
    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, format: str, *args) -> None:
            return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    except PermissionError:
        yield "http://static.test/", _read_static_file_url(directory)
        return

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", _read_http_url
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _read_http_url(url: str) -> tuple[int, str]:
    with urlopen(url, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, body


def _read_static_file_url(directory: Path) -> Callable[[str], tuple[int, str]]:
    root = directory.resolve()

    def read(url: str) -> tuple[int, str]:
        parsed = urlparse(url)
        relative_path = parsed.path.lstrip("/") or "index.html"
        asset_path = (root / relative_path).resolve()
        if root != asset_path and root not in asset_path.parents:
            return 404, ""
        if not asset_path.is_file():
            return 404, ""
        return 200, asset_path.read_text(encoding="utf-8")

    return read


def test_tsr_browser_bundle_entry_serves_without_missing_assets() -> None:
    bundle_root = get_browser_bundle_root()
    assert (bundle_root / "index.html").is_file()

    with _static_server(bundle_root) as (base_url, read_url):
        index_url = urljoin(base_url, "index.html")
        index_status, html = read_url(index_url)

        assert index_status == 200
        assert "TSR Video Annotation Tool" in html
        assert "GT Annotation" in html
        assert "Delta Video" in html

        parser = _AssetReferenceParser()
        parser.feed(html)

        assert parser.references
        for reference in parser.references:
            parsed = urlparse(reference)
            assert not parsed.scheme and not parsed.netloc, f"bundle must not depend on network asset: {reference}"

            asset_status, body = read_url(urljoin(index_url, reference))
            assert asset_status == 200, f"missing browser bundle asset: {reference}"
            assert "404" not in body[:120].lower()
