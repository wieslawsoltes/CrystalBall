"""Browser API: bounded text streaming and opt-in, server-timed WebRTC calls.

No browser receives the OpenAI project key or an unrestricted relay URL. The
SDP offer contains network information; do not log it. Call IDs, ownership and
expiry are the only realtime state. A single gateway worker is required.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


async def sse_events(response: httpx.Response):
    """Bound both line and stream size before decoding provider-controlled data."""
    pending = bytearray()
    data_lines: list[str] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > 262144:
            raise HTTPException(502, "AI stream too large")
        pending.extend(chunk)
        while b"\n" in pending:
            raw, _, remainder = pending.partition(b"\n")
            pending = bytearray(remainder)
            if len(raw) > 65536:
                raise HTTPException(502, "AI event too large")
            line = raw.rstrip(b"\r").decode("utf-8", errors="strict")
            if not line:
                if data_lines:
                    body = "\n".join(data_lines)
                    data_lines.clear()
                    if body == "[DONE]":
                        return
                    event = json.loads(body)
                    if not isinstance(event, dict):
                        raise ValueError("Expected SSE object")
                    yield event
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
        if len(pending) > 65536:
            raise HTTPException(502, "AI event too large")
    if pending or data_lines:
        raise HTTPException(502, "Truncated AI stream")


def ndjson(event_type: str, **fields) -> bytes:
    return (json.dumps({"type": event_type, **fields}, ensure_ascii=True) + "\n").encode()


@dataclass
class Call:
    unit: str
    provider_id: str
    task: asyncio.Task | None = None


class Calls:
    """Best-effort server hangup with admission fail-closed on failed cleanup.

    TTL is not a guaranteed financial spending cap: provider/network outages and
    abrupt process loss can prevent hangup. Public deployment needs a durable
    call supervisor. This feature is disabled by default for this reason.
    """
    def __init__(self, app: FastAPI):
        self.app = app
        self.active: dict[str, Call] = {}
        self.pending: set[str] = set()
        self.unhealthy = False

    async def hangup(self, handle: str) -> None:
        call = self.active.get(handle)
        if call is None:
            return
        client = self.app.state.upstream.client
        for attempt in range(3):
            try:
                async with client.stream("POST", f"https://api.openai.com/v1/realtime/calls/{call.provider_id}/hangup",
                    headers={"Authorization": "Bearer " + self.app.state.settings.api_key}, timeout=10) as r:
                    if r.status_code in (200, 204, 404, 410):
                        self.active.pop(handle, None)
                        return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.25 * (attempt + 1))
        self.unhealthy = True
        raise HTTPException(502, "Voice cleanup failed; new calls disabled. Restart only after provider-side review")

    async def expire(self, handle: str):
        await asyncio.sleep(self.app.state.settings.realtime_seconds)
        with suppress(HTTPException):
            await self.hangup(handle)

    async def close(self):
        tasks = [c.task for c in self.active.values() if c.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(self.hangup(h) for h in list(self.active)), return_exceptions=True)


def install(app: FastAPI, authenticate, identify, enter_slot, read_bounded, ascii_text, instructions):
    @app.get("/v1/capabilities")
    async def capabilities(_unit: str = Depends(identify)):
        cfg = app.state.settings
        return {"text": True, "push_to_talk": True, "speech": cfg.public_tts,
                "realtime": cfg.realtime_enabled and cfg.public_tts,
                "realtime_seconds": cfg.realtime_seconds, "revision": "B"}

    @app.post("/v1/text")
    async def text(request: Request, unit: str = Depends(authenticate)):
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            raise HTTPException(415, "Expected application/json")
        try:
            async with asyncio.timeout(10):
                question = Question.model_validate_json(await read_bounded(request, 12000))
            if not question.text.strip():
                raise ValueError("Empty question")
        except (ValidationError, ValueError):
            raise HTTPException(422, "Invalid text request") from None
        except TimeoutError:
            raise HTTPException(408, "Upload timeout") from None
        await enter_slot()

        async def generate():
            cfg = app.state.settings
            accumulated = ""
            try:
                async with asyncio.timeout(55):
                    async with app.state.upstream.client.stream(
                        "POST", "https://api.openai.com/v1/responses",
                        headers={"Authorization": "Bearer " + cfg.api_key},
                        json={"model": cfg.text_model, "store": False, "stream": True,
                              "instructions": instructions, "input": question.text,
                              "max_output_tokens": 256,
                              "safety_identifier": hashlib.sha256(unit.encode()).hexdigest()},
                    ) as upstream:
                        if upstream.status_code != 200:
                            yield ndjson("error", message="AI provider unavailable. Check server model/key configuration.")
                            return
                        async for event in sse_events(upstream):
                            kind = event.get("type")
                            if kind == "response.output_text.delta":
                                delta = event.get("delta")
                                if not isinstance(delta, str) or len(accumulated) + len(delta) > 8000:
                                    raise ValueError("Invalid text delta")
                                accumulated += delta
                                # Send only display-safe bounded snapshots. Never forward arbitrary events.
                                if accumulated.strip():
                                    yield ndjson("text", text=ascii_text(accumulated))
                            elif kind == "response.completed":
                                yield ndjson("done", text=ascii_text(accumulated), kind="ai_entertainment")
                                return
                            elif kind in ("error", "response.failed", "response.incomplete"):
                                raise ValueError("Generation failed")
                        raise ValueError("Stream ended before completion")
            except asyncio.CancelledError:
                raise
            except (TimeoutError, httpx.HTTPError, HTTPException, ValueError, UnicodeError):
                yield ndjson("error", message="Generation interrupted. No completed reading is available.")
            finally:
                app.state.slots.release()

        return StreamingResponse(generate(), media_type="application/x-ndjson",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    @app.post("/v1/realtime/call")
    async def realtime(request: Request, unit: str = Depends(authenticate)):
        cfg = app.state.settings
        if not (cfg.realtime_enabled and cfg.public_tts):
            raise HTTPException(403, "Live AI voice is disabled")
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/sdp":
            raise HTTPException(415, "Expected application/sdp")
        calls: Calls = app.state.calls
        if calls.unhealthy or len(calls.active) + len(calls.pending) >= 2:
            raise HTTPException(503, "Voice capacity unavailable")
        if unit in calls.pending or any(c.unit == unit for c in calls.active.values()):
            raise HTTPException(409, "A voice session is already active for this device")
        try:
            async with asyncio.timeout(10):
                offer = (await read_bounded(request, 32768)).decode("utf-8")
            if not offer.startswith("v=0") or "m=audio" not in offer:
                raise ValueError("Invalid SDP")
        except (UnicodeError, ValueError):
            raise HTTPException(422, "Invalid SDP offer") from None
        except TimeoutError:
            raise HTTPException(408, "Upload timeout") from None
        # Recheck after awaiting the upload: concurrent offers must not bypass admission.
        if calls.unhealthy or len(calls.active) + len(calls.pending) >= 2:
            raise HTTPException(503, 'Voice capacity unavailable')
        if unit in calls.pending or any(c.unit == unit for c in calls.active.values()):
            raise HTTPException(409, 'A voice session is already active for this device')
        calls.pending.add(unit)
        try:
            session = {"type": "realtime", "model": cfg.realtime_model,
                       "instructions": instructions + " Tell users your voice is AI-generated. Keep every answer brief.",
                       "max_output_tokens": 256, "audio": {"output": {"voice": "marin"}}}
            async with asyncio.timeout(25):
                async with app.state.upstream.client.stream("POST", "https://api.openai.com/v1/realtime/calls",
                    headers={"Authorization": "Bearer " + cfg.api_key,
                             "OpenAI-Safety-Identifier": hashlib.sha256(unit.encode()).hexdigest()},
                    files={"sdp": (None, offer), "session": (None, json.dumps(session))}) as upstream:
                    if upstream.status_code not in (200, 201):
                        raise HTTPException(502, "Live voice provider rejected the session")
                    provider_id = urlparse(upstream.headers.get("location", "")).path.rstrip("/").split("/")[-1]
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", provider_id):
                        calls.unhealthy = True
                        raise HTTPException(502, "Provider omitted a manageable call ID; live voice disabled")
                    handle = secrets.token_urlsafe(24)
                    calls.active[handle] = Call(unit, provider_id)
                    calls.active[handle].task = asyncio.create_task(calls.expire(handle))
                    answer = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        if len(answer) + len(chunk) > 32768:
                            await calls.hangup(handle)
                            raise HTTPException(502, "Provider SDP exceeds bounds")
                        answer.extend(chunk)
                    if not answer.startswith(b"v=0"):
                        await calls.hangup(handle)
                        raise HTTPException(502, "Invalid provider SDP")
                    return Response(bytes(answer), media_type="application/sdp",
                        headers={"X-Orb-Call": handle, "X-Orb-Duration": str(cfg.realtime_seconds)})
        except (TimeoutError, httpx.HTTPError):
            raise HTTPException(504, "Voice connection timed out") from None
        finally:
            calls.pending.discard(unit)

    @app.delete("/v1/realtime/call/{handle}")
    async def stop_call(handle: str, unit: str = Depends(identify)):
        # Stopping remains possible after the request budget is exhausted.
        call = app.state.calls.active.get(handle)
        if call and call.unit != unit:
            raise HTTPException(404, "Unknown call")
        if call:
            if call.task:
                call.task.cancel()
            await app.state.calls.hangup(handle)
        return Response(status_code=204)
