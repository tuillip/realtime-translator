🟦 Realtime Translator (English → Farsi)

A real-time audio captioning system that:

Captures English speech from a microphone or audio input

Streams it to AssemblyAI for live transcription

Translates the text into Farsi using Google Translate

Displays captions on any device on the same network (phones, tablets, etc.)

Designed for use in church services, community events, and small gatherings where live translated captions improve accessibility.

⭐ Features

🔊 Realtime English → Farsi translation

🌐 Local WebSocket caption server – accessible to anyone on the same WiFi

📱 Mobile-friendly frontend that renders clean, right-to-left Farsi text

✂️ Intelligent line breaking (Option C mode)

📡 Supports multiple audio sources (mic, 3.5mm input, Dante, USB interfaces)

🧩 Extensible architecture (add Spanish, Arabic, etc.)

📁 Repository Structure
/backend
   ├── translator_backend.py      # Main Python server (ASR + translation)
   ├── .env.example               # Template for environment variables
   ├── requirements.txt           # Python dependencies

/frontend
   └── caption_farsi.html         # Display page for translated captions

README.md
LICENSE
.gitignore

🔧 Setup Instructions
1. Clone the repository
git clone https://github.com/<your-username>/realtime-translator
cd realtime-translator


(or download ZIP if you prefer the website interface)

2. Create your real .env file

Copy .env.example → .env
Then fill in your keys:

ASSEMBLYAI_API_KEY=your_assemblyai_key_here
GOOGLE_TRANSLATE_API_KEY=your_google_key_here


Do not upload .env to GitHub.

3. Install Python dependencies
pip install -r backend/requirements.txt

4. Run the backend server

From the repo root:

python backend/translator_backend.py


This will:

start the local caption WebSocket server

connect to AssemblyAI

begin listening to audio input

5. Open the caption display on your phone

Look up your computer’s local IP address

Visit:

http://<your-ip>:8765


Example:

http://192.168.1.45:8765


You will see the Farsi captions appear in real time.

🎧 Supported Audio Sources

Laptop microphone

3.5mm TRRS external mic input (with proper adapter)

USB Audio interface (recommended)

Dante / RedNet audio via Dante Virtual Soundcard
(if your Focusrite RedNet device supports it)

🛠 Future Enhancements

Live language switching (Farsi/Spanish/etc)

Multi-screen synchronized captions

Local caching for poor internet connections

Improved word-by-word streaming

Optional Whisper fallback for offline captioning

📄 License

MIT License — free for personal, community, and commercial use.
