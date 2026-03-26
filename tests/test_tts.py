import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from piassistant.config import Settings
from piassistant.services.tts import TTSService, TTSUnavailableError, _pcm_to_wav
from piassistant.api.app import create_app
from piassistant.brain.agent import Agent
from piassistant.services.base import ServiceRegistry


# --- TTSService unit tests ---


@pytest.fixture
def settings_no_backends():
    return Settings(
        anthropic_api_key="test",
        tts_kokoro_url="",
        tts_piper_enabled=False,
    )


@pytest.fixture
def settings_kokoro():
    return Settings(
        anthropic_api_key="test",
        tts_kokoro_url="http://macmini.local:8880",
        tts_kokoro_voice="af_nova",
        tts_piper_enabled=False,
    )


@pytest.fixture
def settings_piper(tmp_path):
    model = tmp_path / "voice.onnx"
    model.write_text("fake")
    return Settings(
        anthropic_api_key="test",
        tts_kokoro_url="",
        tts_piper_enabled=True,
        tts_piper_model=str(model),
    )


class TestTTSServiceHealth:
    @pytest.mark.asyncio
    async def test_health_no_backends(self, settings_no_backends):
        svc = TTSService(settings_no_backends)
        await svc.initialize()
        health = await svc.health_check()
        assert health["healthy"] is False
        assert health["backends"] == []

    @pytest.mark.asyncio
    async def test_health_kokoro_configured(self, settings_kokoro):
        svc = TTSService(settings_kokoro)
        await svc.initialize()
        # Kokoro health check tries to reach the server — mock it
        with patch("piassistant.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            health = await svc.health_check()
            assert "kokoro" in health["backends"]
            assert health["healthy"] is True


class TestTTSServiceSynthesize:
    @pytest.mark.asyncio
    async def test_synthesize_empty_text(self, settings_kokoro):
        svc = TTSService(settings_kokoro)
        await svc.initialize()
        with pytest.raises(ValueError, match="Empty text"):
            await svc.synthesize("")

    @pytest.mark.asyncio
    async def test_synthesize_kokoro_calls_api(self, settings_kokoro):
        svc = TTSService(settings_kokoro)
        await svc.initialize()

        fake_wav = b"RIFF" + b"\x00" * 100
        with patch("piassistant.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.content = fake_wav
            mock_resp.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await svc.synthesize("Hello world")
            assert result == fake_wav

            # Verify correct API call
            call_args = mock_client.post.call_args
            assert "/v1/audio/speech" in call_args[0][0]
            body = call_args[1]["json"]
            assert body["input"] == "Hello world"
            assert body["voice"] == "af_nova"

    @pytest.mark.asyncio
    async def test_synthesize_no_backends_raises(self, settings_no_backends):
        svc = TTSService(settings_no_backends)
        await svc.initialize()
        with pytest.raises(TTSUnavailableError):
            await svc.synthesize("Hello")

    @pytest.mark.asyncio
    async def test_kokoro_failure_falls_through_to_piper(self, settings_kokoro):
        """When kokoro fails and piper is also not available, raises TTSUnavailableError."""
        svc = TTSService(settings_kokoro)
        await svc.initialize()

        with patch("piassistant.services.tts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            with pytest.raises(TTSUnavailableError):
                await svc.synthesize("Hello")


class TestPCMToWav:
    def test_wav_header(self):
        pcm = b"\x00" * 100
        wav = _pcm_to_wav(pcm, sample_rate=22050, channels=1, sample_width=2)
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "
        assert wav[36:40] == b"data"
        # data chunk size should match PCM size
        import struct
        data_size = struct.unpack_from("<I", wav, 40)[0]
        assert data_size == 100
        # Total file = header (44) + data (100)
        assert len(wav) == 144


# --- API route tests ---


@pytest.fixture
def tts_app():
    settings = Settings(anthropic_api_key="test")
    registry = ServiceRegistry()
    tts = TTSService(settings)
    registry.register(tts)
    agent = MagicMock(spec=Agent)
    agent.process = AsyncMock(return_value="ok")
    agent.reset = MagicMock()
    return create_app(registry, agent, settings)


@pytest_asyncio.fixture
async def tts_client(tts_app):
    transport = ASGITransport(app=tts_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestVoiceEndpoints:
    @pytest.mark.asyncio
    async def test_voice_config(self, tts_client):
        r = await tts_client.get("/api/voice/config")
        assert r.status_code == 200
        data = r.json()
        assert "available" in data
        assert "backends" in data

    @pytest.mark.asyncio
    async def test_speak_no_backends_returns_503(self, tts_client):
        r = await tts_client.post("/api/voice/speak", json={"text": "hello"})
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_speak_empty_text_returns_400(self, tts_client):
        r = await tts_client.post("/api/voice/speak", json={"text": ""})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_speak_returns_audio(self, tts_client):
        fake_wav = b"RIFF" + b"\x00" * 100
        with patch.object(TTSService, "synthesize", new_callable=AsyncMock, return_value=fake_wav):
            r = await tts_client.post("/api/voice/speak", json={"text": "hello"})
            assert r.status_code == 200
            assert r.headers["content-type"] == "audio/wav"
            assert r.content == fake_wav

    @pytest.mark.asyncio
    async def test_config_includes_tts_available(self, tts_client):
        r = await tts_client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert "tts_available" in data

    @pytest.mark.asyncio
    async def test_speak_stream_returns_audio_mpeg(self, tts_client):
        fake_mp3 = b"\xff\xfb\x90\x00" + b"\x00" * 100

        async def fake_stream(text):
            yield fake_mp3

        with patch.object(TTSService, "synthesize_stream", side_effect=fake_stream):
            r = await tts_client.post("/api/voice/speak", json={"text": "hello", "stream": True})
            assert r.status_code == 200
            assert r.headers["content-type"] == "audio/mpeg"
            assert len(r.content) > 0

    @pytest.mark.asyncio
    async def test_speak_stream_empty_text_returns_400(self, tts_client):
        r = await tts_client.post("/api/voice/speak", json={"text": "", "stream": True})
        assert r.status_code == 400
