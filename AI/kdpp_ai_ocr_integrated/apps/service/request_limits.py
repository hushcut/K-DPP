"""multipart 파싱 전에 독립 AI 서비스의 전체 HTTP 본문을 제한한다."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.service.response_contract import failed_label_response
from apps.text.ocr_image import MAX_IMAGE_BYTES


# 이미지 10MiB와 multipart 경계·헤더·부가 필드 1MiB를 함께 제한한다.
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 1024 * 1024
REPLAY_CHUNK_BYTES = 1024 * 1024


class BodySizeLimitMiddleware:
    """크기 헤더와 실제 수신량을 검사한 후 제한 안의 본문만 전달한다."""

    def __init__(self, app: ASGIApp, *, max_bytes: int, api_version: str):
        self.app = app
        self.max_bytes = max_bytes
        self.api_version = api_version

    async def _reject(self, scope: Scope, receive: Receive, send: Send, *, invalid: bool = False) -> None:
        response = JSONResponse(
            status_code=400 if invalid else 413,
            content=failed_label_response(
                api_version=self.api_version,
                error_code="invalid_request" if invalid else "payload_too_large",
                message=("요청 크기 헤더가 올바르지 않습니다." if invalid else
                         f"전체 요청 본문은 {self.max_bytes // (1024 * 1024)}MiB 이하여야 합니다."),
            ),
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        lengths = set()
        for name, raw in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            value = raw.strip()
            if not value.isdigit():
                await self._reject(scope, receive, send, invalid=True)
                return
            try:
                lengths.add(int(value))
            except ValueError:
                await self._reject(scope, receive, send, invalid=True)
                return
        if len(lengths) > 1:
            await self._reject(scope, receive, send, invalid=True)
            return
        if lengths and next(iter(lengths)) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        # 헤더가 작게 신고돼도 실제 본문을 센다. 초과 본문은 파서에 넘기지 않는다.
        # 빈 청크나 잘게 나뉜 청크도 별도 객체 목록 없이 하나의 제한된 버퍼에 담는다.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        cursor = 0
        complete = False

        async def replay_receive() -> Message:
            nonlocal body, cursor, complete
            if complete:
                return await receive()
            end = min(cursor + REPLAY_CHUNK_BYTES, len(body))
            chunk = bytes(body[cursor:end])
            cursor = end
            more_body = cursor < len(body)
            if not more_body:
                complete = True
                body = bytearray()  # OCR 대기 동안 업로드 버퍼를 보유하지 않는다.
            return {"type": "http.request", "body": chunk, "more_body": more_body}

        await self.app(scope, replay_receive, send)
