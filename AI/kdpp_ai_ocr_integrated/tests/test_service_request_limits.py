"""HTTP 본문 제한·파싱 전 차단·응답 계약의 서비스 회귀 검사."""

import asyncio
from io import BytesIO
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from starlette.datastructures import UploadFile

from apps.service import main as service_main
from apps.service.response_contract import LabelResponseContract


def assert_contract(messages, status_code=413, error_code="payload_too_large"):
    assert messages[0]["status"] == status_code
    payload = json.loads(b"".join(message.get("body", b"") for message in messages[1:]))
    LabelResponseContract.model_validate(payload)
    assert payload["status"] == "failed"
    assert payload["error_code"] == error_code
    assert payload["materials"] == payload["parts"] == {}
    return payload


def run_asgi(app, chunks, *, headers=(), path="/v1/analyze-label", scope_type="http"):
    messages = []
    received = []
    scope = {"type": scope_type, "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "headers": list(headers), "client": ("test", 123),
             "server": ("test", 80), "root_path": ""}
    iterator = iter(chunks)

    async def receive():
        message = next(iterator, {"type": "http.disconnect"})
        received.append(message)
        return message

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    return messages, received


def chunks(*values):
    return [{"type": "http.request", "body": value, "more_body": index < len(values)-1}
            for index, value in enumerate(values)]


def limited(app, maximum=256):
    from apps.service.request_limits import BodySizeLimitMiddleware
    return BodySizeLimitMiddleware(app, max_bytes=maximum, api_version=service_main.API_VERSION)


def test_declared_oversize_rejected_before_read_or_parse(monkeypatch):
    def forbid_parser(*_args, **_kwargs):
        pytest.fail("크기 초과 요청에서 multipart 파서를 실행했습니다.")
    monkeypatch.setattr("starlette.requests.MultiPartParser", forbid_parser)
    maximum = service_main.MAX_IMAGE_BYTES + 1024 * 1024
    messages, received = run_asgi(service_main.app, [], headers=(
        (b"content-length", str(maximum+1).encode()),
        (b"content-type", b"multipart/form-data; boundary=test"),
    ))
    assert_contract(messages)
    assert received == []


def test_lengthless_body_over_global_limit_never_reaches_parser():
    maximum = service_main.MAX_IMAGE_BYTES + 1024 * 1024
    content = b'{"text":"COTTON 100%"}' + b" " * maximum
    messages, _ = run_asgi(service_main.app, chunks(content), headers=(
        (b"content-type", b"application/json"),
    ), path="/v1/parse-text")
    assert_contract(messages)


@pytest.mark.parametrize("headers", [(), ((b"content-length", b"1"),), ((b"content-length", b"0"),)])
def test_actual_chunked_size_is_checked_before_multipart_parser(monkeypatch, headers):
    def forbid_parser(*_args, **_kwargs):
        pytest.fail("크기 초과 요청에서 multipart 파서를 실행했습니다.")
    monkeypatch.setattr("starlette.requests.MultiPartParser", forbid_parser)
    messages, received = run_asgi(limited(service_main.app), chunks(b"x"*128, b"x"*129, b"unused"),
        headers=headers+((b"content-type", b"multipart/form-data; boundary=test"),))
    assert_contract(messages)
    assert len(received) == 2


@pytest.mark.parametrize("values", [[b"-1"], [b"+1"], [b""], [b"no"], [b"1", b"2"], [b"1, 1"]])
def test_invalid_or_conflicting_length_headers_use_safe_contract(values):
    messages, received = run_asgi(limited(service_main.app), [],
        headers=tuple((b"content-length", value) for value in values))
    assert_contract(messages, 400, "invalid_request")
    assert received == []


@pytest.mark.parametrize("values", [(b"",), (b"abcd",), (b"a", b"", b"b", b"", b"cd")])
def test_exact_boundary_and_empty_chunks_replay_body_without_changes(values):
    seen = bytearray()
    async def app(_scope, receive, send):
        while True:
            message = await receive()
            seen.extend(message["body"])
            if not message["more_body"]:
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    messages, _ = run_asgi(limited(app, 4), chunks(*values), headers=((b"content-length", b"0"),))
    assert messages[0]["status"] == 204
    assert seen == b"".join(values)


def test_replay_chunks_are_bounded_and_actual_disconnect_is_forwarded():
    from apps.service.request_limits import REPLAY_CHUNK_BYTES
    content = b"x" * (REPLAY_CHUNK_BYTES*2+1)
    seen = []
    async def app(_scope, receive, _send):
        while True:
            message = await receive()
            seen.append(message)
            if message["type"] == "http.disconnect":
                break
    _, received = run_asgi(limited(app, len(content)), chunks(content))
    assert b"".join(message.get("body", b"") for message in seen) == content
    assert len(seen) == 4
    assert all(len(message.get("body", b"")) <= REPLAY_CHUNK_BYTES for message in seen)
    assert received[-1]["type"] == "http.disconnect"


def test_disconnect_during_upload_does_not_start_app_or_response():
    async def forbid_app(*_args):
        pytest.fail("끊긴 업로드를 앱에 전달했습니다.")
    messages, _ = run_asgi(limited(forbid_app), [
        {"type": "http.request", "body": b"partial", "more_body": True},
        {"type": "http.disconnect"},
    ])
    assert messages == []


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_other_asgi_scopes_are_forwarded(scope_type):
    seen = []
    async def app(scope, _receive, _send):
        seen.append(scope["type"])
    run_asgi(limited(app), [], scope_type=scope_type)
    assert seen == [scope_type]


def test_aggregate_multipart_limit_prevents_parsing_and_ocr(monkeypatch):
    def forbid(*_args, **_kwargs):
        pytest.fail("전체 크기를 초과한 multipart를 처리했습니다.")
    monkeypatch.setattr("starlette.requests.MultiPartParser", forbid)
    monkeypatch.setattr(service_main, "analyze_label_image_bytes", forbid)
    client = TestClient(limited(service_main.app, 1024))
    response = client.post("/v1/analyze-label", files=[
        ("file", ("first.png", b"x"*600, "image/png")),
        ("extra", ("second.png", b"x"*600, "image/png")),
    ])
    assert response.status_code == 413
    assert response.json()["error_code"] == "payload_too_large"


def test_valid_multipart_preserves_image_and_closes_upload(monkeypatch):
    content = BytesIO()
    Image.new("RGB", (80, 60), "white").save(content, format="PNG")
    original = content.getvalue()
    seen = []
    closed = []
    original_close = UploadFile.close
    async def close(file):
        await original_close(file)
        closed.append(file.file.closed)
    def analyze(data, *, declared_content_type):
        seen.append((data, declared_content_type))
        return service_main.analyze_label_text("COTTON 100%")
    monkeypatch.setattr(UploadFile, "close", close)
    monkeypatch.setattr(service_main, "analyze_label_image_bytes", analyze)
    response = TestClient(service_main.app).post("/v1/analyze-label", files={
        "file": ("label.png", original, "image/png"),
    })
    assert response.status_code == 200
    assert seen == [(original, "image/png")]
    assert closed and all(closed)
    LabelResponseContract.model_validate(response.json())


def test_file_limit_remains_stricter_than_total_request_limit(monkeypatch):
    def forbid(*_args, **_kwargs):
        pytest.fail("이미지 제한을 초과한 파일을 OCR에 전달했습니다.")
    monkeypatch.setattr(service_main, "MAX_IMAGE_BYTES", 100)
    monkeypatch.setattr(service_main, "analyze_label_image_bytes", forbid)
    response = TestClient(service_main.app).post("/v1/analyze-label", files={
        "file": ("label.png", b"x"*101, "image/png"),
    })
    assert response.status_code == 413
    assert response.json()["error_code"] == "payload_too_large"


@pytest.mark.parametrize("path", ["/v1/parse-text", "/v1/analyze-label"])
def test_request_size_failures_are_declared_in_openapi(path):
    responses = service_main.app.openapi()["paths"][path]["post"]["responses"]
    for code in ("400", "413"):
        assert responses[code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/LabelResponseContract",
        }
