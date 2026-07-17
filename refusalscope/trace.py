"""Ingest + normalize raw input into a :class:`~refusalscope.model.Trace`.

RefusalScope accepts three input shapes and folds them all into one ``Trace``:

1. A bare response string (no prompt context).
2. A ``{"prompt": ..., "response": ...}`` pair (or ``{"request": ..., "completion": ...}``).
3. An OpenAI-shape object: a chat-completion ``response`` (``choices[].message``),
   optionally bundled with the originating ``request`` (``messages``) so the
   prompt is recovered. A combined ``{"request": {...}, "response": {...}}``
   envelope is also accepted.

Everything is best-effort and offline: unknown keys are preserved into ``meta``.
"""

from __future__ import annotations

import json
from typing import Any

from .model import Trace


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    """Return the content of the most recent ``user`` message, else last msg."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return _content_to_text(msg.get("content"))
    if messages:
        return _content_to_text(messages[-1].get("content"))
    return ""


def _content_to_text(content: Any) -> str:
    """Flatten OpenAI content (str or list of parts) into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                # {"type": "text", "text": "..."} style parts
                if "text" in part:
                    parts.append(str(part["text"]))
                elif part.get("type") == "text" and "content" in part:
                    parts.append(str(part["content"]))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p)
    return str(content)


def _extract_openai_response_text(obj: dict[str, Any]) -> str | None:
    """Pull assistant text from an OpenAI chat-completion response object.

    Falls back to ``message.refusal`` when ``message.content`` is null/empty:
    OpenAI/gpt-4o structured declines (and content-filtered completions) put the
    decline text in the dedicated ``refusal`` field with ``content=null``, so a
    content-only reader would see an empty response and mis-score it as ANSWER.
    """
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    # chat-completions: choices[].message.content
    message = first.get("message")
    if isinstance(message, dict):
        text = _content_to_text(message.get("content"))
        if text.strip():
            return text
        # content is null/empty — fall back to the structured refusal field.
        refusal = message.get("refusal")
        if refusal:
            return _content_to_text(refusal)
        return text
    # legacy completions: choices[].text
    if "text" in first:
        return str(first["text"])
    return None


def _is_openai_response(obj: dict[str, Any]) -> bool:
    return obj.get("object") in {"chat.completion", "text_completion"} or (
        "choices" in obj and isinstance(obj.get("choices"), list)
    )


def _is_openai_request(obj: dict[str, Any]) -> bool:
    return "messages" in obj and isinstance(obj.get("messages"), list)


def _meta_from_openai_response(obj: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key in ("model", "id", "created", "usage", "system_fingerprint", "object"):
        if key in obj:
            meta[key] = obj[key]
    choices = obj.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        fr = choices[0].get("finish_reason")
        if fr is not None:
            meta["finish_reason"] = fr
    return meta


def normalize(data: Any) -> Trace:
    """Normalize an arbitrary loaded object (or string) into a ``Trace``.

    Accepts a ``str`` (treated as a bare response) or a ``dict`` in any of the
    supported shapes. Raises ``ValueError`` only when no response text can be
    found at all.
    """
    # Shape 1: bare response string.
    if isinstance(data, str):
        return Trace(prompt="", response=data, meta={"source_shape": "bare_string"})

    if not isinstance(data, dict):
        raise ValueError(
            f"Cannot normalize a {type(data).__name__}; expected str or object."
        )

    # Combined envelope: {"request": {...}, "response": {...}}. Also accepts
    # {"prompt": ..., "response": <openai obj>} — the natural "here is my prompt
    # plus the response object I got back" shape — by falling back to the
    # top-level prompt aliases when no "request" is supplied. Without this
    # fallback the envelope branch (which recovers the prompt only from
    # data["request"]) would silently drop the prompt to "" and skip the
    # topic_narrowing / length_collapse signals.
    if "response" in data and isinstance(data["response"], dict):
        req = data.get("request")
        resp_obj = data["response"]
        prompt = ""
        messages = None
        from_envelope_request = False
        if isinstance(req, dict) and _is_openai_request(req):
            messages = req["messages"]
            prompt = _last_user_message(messages)
            from_envelope_request = True
        elif isinstance(req, str):
            prompt = req
            from_envelope_request = True
        else:
            # No "request" supplied — recover the prompt from a top-level
            # alias (mirroring the Shape-2 prompt-key list) so the prompt is
            # never silently dropped.
            for k in ("prompt", "ask", "input", "question"):
                if k in data and data[k] is not None:
                    v = data[k]
                    if isinstance(v, list):
                        prompt = _last_user_message(v)
                    elif isinstance(v, str):
                        prompt = v
                    else:
                        prompt = _content_to_text(v)
                    break
        resp_text = _extract_openai_response_text(resp_obj)
        if resp_text is None:
            raise ValueError("Envelope 'response' object had no extractable text.")
        meta = _meta_from_openai_response(resp_obj)
        meta["source_shape"] = (
            "request_response_envelope"
            if from_envelope_request
            else "prompt_response_pair"
        )
        return Trace(prompt=prompt, response=resp_text, messages=messages, meta=meta)

    # Shape 3: a raw OpenAI chat-completion response object.
    if _is_openai_response(data):
        resp_text = _extract_openai_response_text(data)
        if resp_text is None:
            raise ValueError("OpenAI response had no choices/message text.")
        # An OpenAI response may carry the originating messages if the user
        # bundled them; otherwise prompt stays empty.
        prompt = ""
        messages = None
        if _is_openai_request(data):
            messages = data["messages"]
            prompt = _last_user_message(messages)
        meta = _meta_from_openai_response(data)
        meta["source_shape"] = "openai_response"
        return Trace(prompt=prompt, response=resp_text, messages=messages, meta=meta)

    # Shape 2: {prompt, response} pair, with common aliases.
    prompt_keys = ("prompt", "request", "ask", "input", "question")
    response_keys = ("response", "completion", "output", "answer", "reply", "text")
    prompt_val: Any = ""
    response_val: Any = None
    for k in prompt_keys:
        if k in data:
            v = data[k]
            if isinstance(v, list):  # messages list under "prompt"
                prompt_val = _last_user_message(v)
            else:
                prompt_val = _content_to_text(v) if not isinstance(v, str) else v
            break
    for k in response_keys:
        if k in data and data[k] is not None:
            response_val = data[k]
            break

    if response_val is None:
        raise ValueError(
            "No response text found. Provide a bare string, an OpenAI "
            "chat-completion object, or a {prompt, response} pair."
        )
    if isinstance(response_val, dict):  # response is itself an OpenAI object
        rt = _extract_openai_response_text(response_val)
        response_val = rt if rt is not None else json.dumps(response_val)

    meta = {
        k: v
        for k, v in data.items()
        if k not in set(prompt_keys) | set(response_keys)
    }
    meta["source_shape"] = "prompt_response_pair"
    messages = data["messages"] if isinstance(data.get("messages"), list) else None
    return Trace(
        prompt=str(prompt_val),
        response=str(response_val),
        messages=messages,
        meta=meta,
    )


def load_trace(path: str) -> Trace:
    """Load a JSON file from ``path`` and normalize it into a ``Trace``.

    If the file is not valid JSON, the raw file contents are treated as a bare
    response string (shape 1).
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return normalize(raw)
    return normalize(data)
