import os
import asyncio
import json
import time
import threading
from urllib.parse import urlencode
from datetime import datetime
import traceback

import numpy as np
import sounddevice as sd
import websockets
import aiohttp
from dotenv import load_dotenv

# ======================================================
# Environment / Config
# ======================================================

load_dotenv()

AAI_KEY = os.getenv("ASSEMBLYAI_API_KEY") or ""
GOOGLE_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY") or ""

if not AAI_KEY:
    raise RuntimeError("Missing ASSEMBLYAI_API_KEY in .env")
if not GOOGLE_KEY:
    raise RuntimeError("Missing GOOGLE_TRANSLATE_API_KEY in .env")

RATE = 16000
CHUNK_MS = 100
BLOCK = int(RATE * CHUNK_MS / 1000)

AAI_URL = "wss://streaming.assemblyai.com/v3/ws?" + urlencode({
    "sample_rate": RATE,
    "encoding": "pcm_s16le",
})

MAX_DISPLAY_LINES = 6
MAX_CHARS_PER_LINE = 35


# ======================================================
# Google Translation
# ======================================================

class GoogleTranslator:
    def __init__(self, key):
        self.key = key
        self.url = f"https://translation.googleapis.com/language/translate/v2?key={key}"
        self._session = None

    async def session(self):
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def en_to_fa(self, text):
        text = text.strip()
        if not text:
            return ""
        s = await self.session()
        payload = {
            "q": text,
            "source": "en",
            "target": "fa",
            "format": "text",
        }
        async with s.post(self.url, json=payload, timeout=10) as r:
            data = await r.json()
            return data["data"]["translations"][0]["translatedText"]

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


translator = GoogleTranslator(GOOGLE_KEY)


# ======================================================
# Caption State & Helpers
# ======================================================

def wrap_fa(text, max_chars=35):
    words = text.split()
    lines = []
    current = []
    length = 0

    for w in words:
        extra = len(w) + (1 if current else 0)
        if length + extra > max_chars and current:
            lines.append(" ".join(current))
            current = [w]
            length = len(w)
        else:
            current.append(w)
            length += extra

    if current:
        lines.append(" ".join(current))

    return lines


class CaptionState:
    """The backend is the SINGLE source of truth for committed lines."""
    def __init__(self, max_lines):
        self.lines = []      # finalized, wrapped lines
        self.max_lines = max_lines
        self.lock = asyncio.Lock()

    async def commit_final_phrase(self, fa_text):
        chunks = wrap_fa(fa_text, MAX_CHARS_PER_LINE)
        if not chunks:
            return

        async with self.lock:
            self.lines.extend(chunks)

            if len(self.lines) > self.max_lines:
                excess = len(self.lines) - self.max_lines
                self.lines = self.lines[excess:]

            await broadcast_state(self.lines)


caption_state = CaptionState(MAX_DISPLAY_LINES)


clients = set()

async def broadcast_state(lines):
    """Broadcast the ENTIRE caption list to every connected client."""
    if not clients:
        return
    payload = json.dumps({"type": "state", "lines": lines}, ensure_ascii=False)
    await asyncio.gather(
        *(c.send(payload) for c in list(clients)),
        return_exceptions=True
    )


# ======================================================
# Caption WebSocket Server (Browser → Backend)
# ======================================================

async def caption_server():
    async def handler(ws):
        print("Caption client connected.")
        clients.add(ws)
        try:
            # send current state to new client
            async with caption_state.lock:
                if caption_state.lines:
                    await ws.send(
                        json.dumps(
                            {"type": "state", "lines": caption_state.lines},
                            ensure_ascii=False,
                        )
                    )
            await ws.wait_closed()
        finally:
            clients.discard(ws)
            print("Caption client disconnected.")

    server = await websockets.serve(
        handler, "0.0.0.0", 8765,
        ping_interval=20, ping_timeout=20
    )
    print("Caption WS server at ws://127.0.0.1:8765")
    return server


# ======================================================
# Audio + AssemblyAI Stream
# ======================================================

audio_q = asyncio.Queue()

async def run_stream():
    loop = asyncio.get_running_loop()

    # ----------- audio thread -----------
    def audio_thread():
        print("Audio thread starting…")
        try:
            with sd.InputStream(
                samplerate=RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK
            ) as stream:
                print("Microphone active.")
                while True:
                    data, overflow = stream.read(BLOCK)
                    pcm = (data[:, 0] * 32767).astype(np.int16).tobytes()
                    loop.call_soon_threadsafe(audio_q.put_nowait, pcm)
        except Exception as e:
            print("Audio thread error:", e)
            loop.call_soon_threadsafe(audio_q.put_nowait, None)

    threading.Thread(target=audio_thread, daemon=True).start()

    print("Connecting to AssemblyAI…")

    async with websockets.connect(
        AAI_URL,
        extra_headers=[("Authorization", AAI_KEY)],
        ping_interval=5,
        ping_timeout=20,
    ) as ws:

        print("Connected to AssemblyAI.")

        async def audio_sender():
            try:
                while True:
                    pcm = await audio_q.get()
                    if pcm is None:
                        break
                    await ws.send(pcm)
            except Exception:
                print("[Sender exit]")
                traceback.print_exc()

        async def receiver():
            try:
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)

                    if msg.get("type") in ("Turn", "FinalTranscript"):
                        transcript = msg.get("transcript") or msg.get("text") or ""
                        transcript = transcript.strip()
                        is_final = bool(msg.get("end_of_turn") or msg.get("type") == "FinalTranscript")

                        # ignore empty
                        if not transcript:
                            continue

                        if is_final:
                            print("[FINAL EN]", transcript)
                            fa = await translator.en_to_fa(transcript)
                            print("[FINAL FA]", fa)
                            await caption_state.commit_final_phrase(fa)

                        else:
                            # PARTIAL = real-time active update
                            # translate partial quickly (lightweight on small text)
                            try:
                                fa = await translator.en_to_fa(transcript)
                            except:
                                fa = transcript
                            payload = json.dumps(
                                {"type": "active", "text": fa},
                                ensure_ascii=False
                            )
                            # send to all browsers
                            await asyncio.gather(
                                *(c.send(payload) for c in list(clients)),
                                return_exceptions=True
                            )

            except Exception:
                print("[Receiver exit]")
                traceback.print_exc()

        await asyncio.gather(
            asyncio.create_task(audio_sender()),
            asyncio.create_task(receiver())
        )


# ======================================================
# Main Loop
# ======================================================

async def main():
    await caption_server()

    try:
        while True:
            # clear audio queue
            while not audio_q.empty():
                audio_q.get_nowait()
                audio_q.task_done()

            try:
                await run_stream()
            except Exception as e:
                print("Stream error, retrying in 3 seconds:", e)
                await asyncio.sleep(3)

    finally:
        await translator.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
