"""Regression: structured OpenAI declines (message.refusal / content_filter).

A real OpenAI/gpt-4o content-filtered decline arrives with
``message.content = null`` and the decline text in ``message.refusal``, with
``finish_reason = "content_filter"``. A content-only reader sees an empty
response and mis-scores it as ANSWER — a false negative on the exact case
RefusalScope exists to catch. These tests pin the fixed behaviour.
"""

from __future__ import annotations

from refusalscope import classify, normalize
from refusalscope.model import VerdictLabel
from refusalscope.trace import _extract_openai_response_text


def test_extract_falls_back_to_refusal_when_content_null():
    obj = {
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "refusal": "I'm sorry, I can't help with that request.",
                },
                "finish_reason": "content_filter",
            }
        ],
    }
    text = _extract_openai_response_text(obj)
    assert text == "I'm sorry, I can't help with that request."


def test_content_filter_response_is_not_scored_as_answer():
    obj = {
        "object": "chat.completion",
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "refusal": "I'm sorry, I can't assist with that.",
                },
                "finish_reason": "content_filter",
            }
        ],
    }
    trace = normalize(obj)
    # The decline text must be recovered, not left empty.
    assert "can't assist" in trace.response
    assert trace.meta["finish_reason"] == "content_filter"

    verdict = classify(trace)
    # A structured decline must never read as a genuine answer.
    assert verdict.label != VerdictLabel.answer
    assert verdict.is_refusal()


def test_content_filter_signal_fires_even_with_empty_refusal_text():
    # Some providers send content_filter with neither content nor refusal text;
    # the finish_reason alone must still be treated as a hard refusal.
    obj = {
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "content_filter",
            }
        ],
    }
    trace = normalize(obj)
    verdict = classify(trace)
    assert verdict.label == VerdictLabel.hard_refusal
    assert any(s.name == "content_filter" and s.fired for s in verdict.signals)


def test_normal_content_still_wins_over_refusal_field():
    # When content is present it must be used; refusal fallback only triggers on
    # an empty/null content.
    obj = {
        "object": "chat.completion",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Here is the answer you asked for.",
                    "refusal": None,
                },
                "finish_reason": "stop",
            }
        ],
    }
    trace = normalize(obj)
    assert trace.response == "Here is the answer you asked for."


# --------------------------------------------------------------------------- #
# v0.3.0 — envelope path must not drop the prompt
# --------------------------------------------------------------------------- #


def test_prompt_recovered_when_response_is_openai_object():
    # The natural "here is my prompt + the response object I got back" shape.
    # Before v0.3 the envelope branch (entered whenever "response" is a dict)
    # recovered the prompt only from data["request"], so the prompt was silently
    # dropped to "" and topic_narrowing/length_collapse could not fire.
    obj = {
        "object": "chat.completion",
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "A genuine answer about indexes."},
                "finish_reason": "stop",
            }
        ],
    }
    trace = normalize({"prompt": "List three causes of slow queries and how to diagnose each.", "response": obj})
    assert trace.prompt == "List three causes of slow queries and how to diagnose each."
    assert trace.response == "A genuine answer about indexes."
    assert trace.meta["finish_reason"] == "stop"
    # Honest about the shape: no request was supplied, so this is a pair.
    assert trace.meta["source_shape"] == "prompt_response_pair"


def test_request_response_envelope_still_uses_request_prompt():
    # The real {request, response} envelope path is unchanged: the prompt comes
    # from the bundled request, and source_shape stays request_response_envelope.
    envelope = {
        "request": {"messages": [{"role": "user", "content": "Reverse a linked list"}]},
        "response": {
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "Here is the code…"}}],
        },
    }
    trace = normalize(envelope)
    assert trace.prompt == "Reverse a linked list"
    assert trace.messages is not None
    assert trace.meta["source_shape"] == "request_response_envelope"
