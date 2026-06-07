"""Audio Engine — Speech-to-Text (Whisper) and Text-to-Speech (OpenAI TTS)."""

import io
import logging
import tempfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from awren_core.llm import create_llm_client
from awren_core.orm_models import AudioTranscriptionModel

logger = logging.getLogger(__name__)

AUDIO_UPLOAD_DIR = Path("/tmp/awren_audio")
AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_AUDIO_FORMATS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "ogg", "flac"}


class AudioEngine:
    """Handles speech-to-text and text-to-speech using OpenAI Whisper/TTS."""

    def __init__(self, session: Session):
        self._session = session

    def _get_openai_client(self):
        """Create an OpenAI client configured with the DB-stored API key."""
        from openai import OpenAI
        llm = create_llm_client(db_session=self._session)
        api_key = getattr(llm, "api_key", None) or getattr(llm, "openai_api_key", None)
        base_url = getattr(llm, "base_url", None)
        if not api_key:
            from awren_core.settings import get_settings
            env = get_settings()
            api_key = env.openai_api_key
        kwargs = {"api_key": api_key}
        if base_url and "openrouter" not in base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    async def transcribe(self, audio_data: bytes, filename: str = "audio.mp3") -> dict:
        """Transcribe audio to text using Whisper API. Returns transcription + metadata."""
        client = self._get_openai_client()

        # Determine format from filename
        fmt = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"

        # Save to temporary file for the API
        tmp_path = AUDIO_UPLOAD_DIR / f"{uuid4().hex}.{fmt}"
        tmp_path.write_bytes(audio_data)

        try:
            with open(str(tmp_path), "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                )

            result = {
                "text": transcript.text,
                "language": getattr(transcript, "language", "unknown"),
                "duration_seconds": getattr(transcript, "duration", 0),
                "segments": [
                    {
                        "start": s.get("start", 0),
                        "end": s.get("end", 0),
                        "text": s.get("text", ""),
                    }
                    for s in getattr(transcript, "segments", [])
                ] if hasattr(transcript, "segments") else [],
            }

            # Persist transcription
            model = AudioTranscriptionModel(
                id=uuid4(),
                original_filename=filename,
                file_size=len(audio_data),
                duration_seconds=result["duration_seconds"],
                transcription_text=result["text"],
                language=result["language"],
                metadata={"segments_count": len(result["segments"])},
            )
            self._session.add(model)
            self._session.flush()
            result["id"] = str(model.id)

            return result

        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    async def synthesize(self, text: str, voice: str = "alloy", model: str = "tts-1-hd") -> bytes:
        """Synthesize text to speech audio bytes. Returns MP3 audio data."""
        client = self._get_openai_client()
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        return response.content

    async def voice_chat(self, audio_data: bytes, filename: str = "audio.mp3",
                         conversation_id: Optional[str] = None,
                         voice: str = "alloy") -> dict:
        """Full voice interaction: audio → STT → Brain → TTS → audio.
        
        Returns both the transcription, brain response, and synthesized audio.
        """
        # Step 1: Transcribe
        transcription = await self.transcribe(audio_data, filename)
        user_text = transcription["text"]

        # Step 2: Chat with Brain
        from awren_core.services import EventService
        svc = EventService(self._session)
        brain_result = await svc.chat(
            message=user_text,
            conversation_id=conversation_id,
        )

        # Step 3: Synthesize response
        brain_reply = brain_result.get("reply", "I'm sorry, I couldn't process that.")
        audio_bytes = await self.synthesize(brain_reply, voice=voice)

        return {
            "transcription": transcription,
            "brain_reply": brain_reply,
            "conversation_id": brain_result.get("conversation_id"),
            "actions_taken": brain_result.get("actions_taken", []),
            "audio_data": audio_bytes,
            "audio_format": "mp3",
        }


def is_supported_audio(filename: str) -> bool:
    """Check if the file extension is a supported audio format."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in SUPPORTED_AUDIO_FORMATS
