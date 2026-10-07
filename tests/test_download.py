import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sukoon.separation.download import (
    OFFLINE_MESSAGE,
    DownloadError,
    download_file,
    download_preset,
)
from sukoon.separation.models import CHECKSUM_MESSAGE, ModelChecksumError, ModelFile

BODY = bytes(range(256)) * 4096  # 1 MiB
SHA = hashlib.sha256(BODY).hexdigest()


class Server:
    """Serves BODY with Range support; can cut the first response off halfway."""

    def __init__(self, drop_first=False):
        self.drop_first = drop_first
        self.ranges = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start = 0
                header = self.headers.get("range")
                outer.ranges.append(header)
                if header:
                    start = int(header.removeprefix("bytes=").split("-")[0])
                    self.send_response(206)
                    self.send_header("content-range", f"bytes {start}-{len(BODY) - 1}/{len(BODY)}")
                else:
                    self.send_response(200)
                self.send_header("content-length", str(len(BODY) - start))
                self.end_headers()
                if outer.drop_first and len(outer.ranges) == 1:
                    self.wfile.write(BODY[: len(BODY) // 2])
                    self.wfile.flush()
                    self.connection.close()
                    return
                self.wfile.write(BODY[start:])

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/model.onnx"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server()
    yield s
    s.close()


def model(url, sha=SHA, preset="fast"):
    return ModelFile(preset, "UVR-MDX-NET-Voc_FT.onnx", url, len(BODY), sha)


def test_full_download_lands_verified_with_progress(tmp_path, server):
    seen = []
    path = download_file(model(server.url), tmp_path, lambda d, t, r: seen.append((d, t)))
    assert path.read_bytes() == BODY
    assert not (tmp_path / "UVR-MDX-NET-Voc_FT.onnx.part").exists()
    assert seen[-1] == (len(BODY), len(BODY))
    assert [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_dropped_connection_resumes_with_range(tmp_path):
    s = Server(drop_first=True)
    try:
        path = download_file(model(s.url), tmp_path, lambda *a: None)
    finally:
        s.close()
    assert path.read_bytes() == BODY
    assert s.ranges[0] is None
    assert s.ranges[1] == f"bytes={len(BODY) // 2}-"


def test_wrong_hash_deletes_and_fails(tmp_path, server):
    with pytest.raises(ModelChecksumError, match=CHECKSUM_MESSAGE):
        download_file(model(server.url, sha="0" * 64), tmp_path, lambda *a: None)
    assert list(tmp_path.iterdir()) == []


def test_offline_gives_the_retry_message(tmp_path):
    with pytest.raises(DownloadError, match=OFFLINE_MESSAGE):
        download_file(
            model("http://127.0.0.1:1/model.onnx"), tmp_path, lambda *a: None, timeout=1, attempts=1
        )


def test_preset_download_skips_files_already_in_place(tmp_path, server):
    (tmp_path / "UVR-MDX-NET-Voc_FT.onnx").write_bytes(BODY)
    seen = []
    download_preset(tmp_path, "fast", lambda d, t, r: seen.append(d), files=(model(server.url),))
    assert server.ranges == []
    assert seen == [len(BODY)]
