"""Tests for Surveyor0.asurvey() ergonomic method."""

import asyncio

import pynng
import pytest


@pytest.mark.asyncio
async def test_asurvey_multiple_respondents():
    """asurvey() collects responses from multiple respondents."""
    addr = "inproc://test-asurvey-multi"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=500, survey_time=500
    ) as surveyor, pynng.Respondent0(
        dial=addr, recv_timeout=1000, send_timeout=1000
    ) as r1, pynng.Respondent0(
        dial=addr, recv_timeout=1000, send_timeout=1000
    ) as r2:
        await asyncio.sleep(0.05)  # let pipes establish

        async def respond(respondent, reply):
            msg = await respondent.arecv()
            await respondent.asend(reply)

        task1 = asyncio.create_task(respond(r1, b"resp1"))
        task2 = asyncio.create_task(respond(r2, b"resp2"))

        responses = await surveyor.asurvey(b"question")

        await task1
        await task2

        assert len(responses) == 2
        assert set(responses) == {b"resp1", b"resp2"}


@pytest.mark.asyncio
async def test_asurvey_no_respondents():
    """asurvey() returns empty list when no respondents reply."""
    addr = "inproc://test-asurvey-none"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=100, survey_time=100
    ) as surveyor:
        responses = await surveyor.asurvey(b"anyone?")
        assert responses == []


@pytest.mark.asyncio
async def test_asurvey_timeout_override():
    """asurvey() timeout parameter overrides recv_timeout for collection."""
    addr = "inproc://test-asurvey-timeout"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=5000, survey_time=100
    ) as surveyor:
        original_timeout = surveyor.recv_timeout
        responses = await surveyor.asurvey(b"quick?", timeout=100)
        assert responses == []
        # recv_timeout should be restored
        assert surveyor.recv_timeout == original_timeout


@pytest.mark.asyncio
async def test_asurvey_preserves_recv_timeout_on_error():
    """asurvey() restores recv_timeout even if asend() raises."""
    addr = "inproc://test-asurvey-restore"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=5000, send_timeout=100
    ) as surveyor:
        original_timeout = surveyor.recv_timeout
        # Passing a str instead of bytes triggers a ValueError in asend()
        with pytest.raises(ValueError):
            await surveyor.asurvey("not bytes", timeout=200)
        assert surveyor.recv_timeout == original_timeout


@pytest.mark.asyncio
async def test_asurvey_max_responses():
    """asurvey() stops collecting after max_responses is reached."""
    addr = "inproc://test-asurvey-max"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=500, survey_time=500
    ) as surveyor, pynng.Respondent0(
        dial=addr, recv_timeout=1000, send_timeout=1000
    ) as r1, pynng.Respondent0(
        dial=addr, recv_timeout=1000, send_timeout=1000
    ) as r2:
        await asyncio.sleep(0.05)  # let pipes establish

        async def respond(respondent, reply):
            msg = await respondent.arecv()
            await respondent.asend(reply)

        task1 = asyncio.create_task(respond(r1, b"resp1"))
        task2 = asyncio.create_task(respond(r2, b"resp2"))

        responses = await surveyor.asurvey(b"question", max_responses=1)

        # Cancel remaining tasks to avoid warnings
        task1.cancel()
        task2.cancel()
        for t in (task1, task2):
            try:
                await t
            except asyncio.CancelledError:
                pass

        assert len(responses) == 1


@pytest.mark.asyncio
async def test_asurvey_uses_socket_recv_timeout():
    """asurvey() without timeout arg uses the socket's recv_timeout."""
    addr = "inproc://test-asurvey-default-timeout"
    with pynng.Surveyor0(
        listen=addr, recv_timeout=100, survey_time=100
    ) as surveyor:
        # Should complete quickly using the socket's recv_timeout
        responses = await surveyor.asurvey(b"hello?")
        assert responses == []
