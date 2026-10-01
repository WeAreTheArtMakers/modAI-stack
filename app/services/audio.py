from abc import ABC, abstractmethod
class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes) -> str: ...
class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes: ...
"""Future pipeline: microphone -> WebSocket -> VAD -> STT -> LLM -> TTS."""

