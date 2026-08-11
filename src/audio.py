import io
import wave
import threading
import time
from typing import Optional, Callable

try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
MAX_DURATION = 60


class VoiceRecorder:

    def __init__(self):
        self._recording = False
        self._frames = []
        self._thread: Optional[threading.Thread] = None
        self._start_time = 0.0

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def duration(self) -> float:
        if self._recording:
            return time.time() - self._start_time
        return 0.0

    def start(self) -> bool:
        if not AUDIO_AVAILABLE:
            return False
        if self._recording:
            return False
        self._frames = []
        self._recording = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> Optional[bytes]:
        if not self._recording:
            return None
        self._recording = False
        if self._thread:
            self._thread.join(timeout=2)
        if not self._frames:
            return None
        return self._encode_wav()

    def cancel(self):
        self._recording = False
        self._frames = []

    def _record_loop(self):
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE) as stream:
                while self._recording:
                    if self.duration > MAX_DURATION:
                        self._recording = False
                        break
                    data, _ = stream.read(1024)
                    self._frames.append(data.copy())
        except Exception:
            self._recording = False

    def _encode_wav(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            for frame in self._frames:
                wf.writeframes(frame.tobytes())
        return buf.getvalue()


def play_audio(wav_data: bytes):
    if not AUDIO_AVAILABLE:
        return
    try:
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            data = wf.readframes(wf.getnframes())
            audio = np.frombuffer(data, dtype=np.int16)
            sd.play(audio, samplerate=wf.getframerate())
            sd.wait()
    except Exception:
        pass
