import logging
import os
import asyncio
from dotenv import load_dotenv
from livekit.plugins import azure
from templates import templates

# Load environment variables
load_dotenv(dotenv_path=".env.local")

AZURE_TTS_KEY = os.getenv("AZURE_TTS_SUBSCRIPTION_KEY")
AZURE_TTS_REGION = os.getenv("AZURE_TTS_REGION")

if not AZURE_TTS_KEY or not AZURE_TTS_REGION:
    raise ValueError("Azure TTS credentials are missing! Set them in .env.local")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# Initialize Azure TTS with credentials
azure_tts = azure.TTS(
    voice="en-US-JennyNeural",  # Change if needed
    subscription_key=AZURE_TTS_KEY,
    region=AZURE_TTS_REGION
)

async def test_tts():
    """ Test if Azure TTS is working correctly """
    logger.info("🔍 Testing Azure TTS...")

    test_messages = {
        "english": "This is a test of the English TTS system.",
        "telugu": "ఇది తెలుగు టెక్స్ట్-టు-స్పీచ్ సిస్టమ్ యొక్క పరీక్ష."
    }

    for lang, message in test_messages.items():
        logger.info(f"🔊 Synthesizing {lang} message...")
        audio = azure_tts.synthesize(message)  # No `await`

        if isinstance(audio, bytes):
            logger.info(f"✅ {lang.capitalize()} TTS successful, generated {len(audio)} bytes")
        else:
            logger.error(f"❌ {lang.capitalize()} TTS failed")

if __name__ == "__main__":
    asyncio.run(test_tts())
