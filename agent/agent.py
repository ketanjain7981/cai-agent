import logging
import json
import asyncio

from livekit import rtc
from livekit.agents.llm import ChatMessage, ChatImage

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, deepgram, silero, turn_detector

# Load environment variables
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

def prewarm(proc: JobProcess):
    """Prewarm function to load voice activity detection (VAD) model."""
    proc.userdata["vad"] = silero.VAD.load()

async def get_video_track(room: rtc.Room, max_retries=10, delay=1.5):
    """Find and return the first available remote video track in the room with retries."""
    for attempt in range(max_retries):
        for participant_id, participant in room.remote_participants.items():
            for track_id, track_publication in participant.track_publications.items():
                if track_publication.track and isinstance(
                    track_publication.track, rtc.RemoteVideoTrack
                ):
                    logger.info(
                        f"Found video track {track_publication.track.sid} "
                        f"from participant {participant_id}"
                    )
                    return track_publication.track
        logger.info(f"⏳ Waiting for video track... Attempt {attempt + 1}/{max_retries}")
        await asyncio.sleep(delay)
    raise ValueError("No remote video track found in the room after retries")

async def get_latest_image(room: rtc.Room):
    """Capture and return a single frame from the video track."""
    video_stream = None
    try:
        video_track = await get_video_track(room) #wait for video track
        video_stream = rtc.VideoStream(video_track)
        async for event in video_stream:
            logger.debug("Captured latest video frame")
            return event.frame
    except Exception as e:
        logger.error(f"Failed to get latest image: {e}")
        return None
    finally:
        if video_stream:
            await video_stream.aclose()

async def wait_for_metadata(participant, max_retries=10, delay=1.5):
    """Waits for metadata to be available for a participant."""
    for attempt in range(max_retries):
        if participant.metadata:
            try:
                metadata = json.loads(participant.metadata)
                bot_name = metadata.get("botName", "Assistant")
                logger.info(f"✅ Metadata found for {participant.identity}, Bot Name: {bot_name}")
                return bot_name
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse metadata for {participant.identity}: {e}")
        
        logger.info(f"⏳ Waiting for metadata... Attempt {attempt + 1}/{max_retries}")
        await asyncio.sleep(delay)

    logger.warning(f"⚠️ Metadata not found after {max_retries} retries. Using default bot name.")
    return "Assistant"

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice assistant."""
    
    async def before_llm_cb(assistant: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        """Callback before LLM generates a response, capturing video frames."""
        latest_image = await get_latest_image(ctx.room)
        if latest_image:
            image_content = [ChatImage(image=latest_image)]
            chat_ctx.messages.append(ChatMessage(role="user", content=image_content))
            logger.debug("Added latest frame to conversation context")

    logger.info(f"🔗 Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)

    participant = await ctx.wait_for_participant()
    logger.info(f"🎙️ Starting voice assistant for participant {participant.identity}")

    # Fetch participant metadata (bot name)
    bot_name = await wait_for_metadata(participant)
    logger.info(f"🆔 Bot is now identified as: {bot_name}")

    # Use the bot name dynamically in the system message
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            f"You are an AI assistant specialized in providing expert feedback in one of three domains. "
            f"The specific persona you will adopt is defined below:\n\n"
            f"<prompt>\n{bot_name}\nBased on the persona specified above, you will act as one of the following experts:\n\n"
            f"1. Code Reviewer:\n   - Expert in analyzing code quality, readability, and structure\n"
            f"   - Proficient in identifying logical errors and suggesting optimizations\n"
            f"   - Knowledgeable about best practices across various programming languages\n"
            f"   - Focused on improving code efficiency and maintainability\n\n"
            f"2. UI/UX Design Reviewer:\n   - Skilled in evaluating user interface aesthetics and functionality\n"
            f"   - Expert in assessing user experience flow and intuitiveness\n"
            f"   - Proficient in identifying design inconsistencies and suggesting improvements\n"
            f"   - Focused on enhancing usability, accessibility, and visual appeal\n\n"
            f"3. Presentation Reviewer:\n   - Experienced in evaluating presentation content and structure\n"
            f"   - Expert in assessing clarity of message and effectiveness of delivery\n"
            f"   - Proficient in identifying areas for improving audience engagement\n"
            f"   - Focused on enhancing overall presentation impact and memorability\n\n"
            f"Your role is to provide helpful reviews and guidance within your area of expertise. "
            f"Engage with users in a friendly, conversational style that encourages detailed input. "
            f"Remember to maintain your chosen persona throughout the entire conversation.\n\n"
            f"When responding to user input, follow these guidelines:\n"
            f"1. Provide only one answer or ask one question at a time.\n"
            f"2. Limit your response to no more than 30 words.\n"
            f"3. Use only plain text without any special characters or symbols.\n"
            f"4. Ensure your response is clear and simple, as it will be converted to voice via text-to-speech.\n\n"
            f"Your final output should consist only of the response spoken response\n</prompt>"
        ),
    )

    # Initialize the voice assistant agent
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=deepgram.TTS(),
        turn_detector=turn_detector.EOUModel(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
        chat_ctx=initial_ctx,
        before_llm_cb=before_llm_cb,
    )

    agent.start(ctx.room, participant)

    greeting_message = f"Hey, I'm {bot_name}. How can I help you today?"
    await agent.say(greeting_message, allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )