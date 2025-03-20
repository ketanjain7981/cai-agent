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
from livekit.plugins import openai, silero, turn_detector, azure
from templates import templates    

# Load environment variables
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

def prewarm(proc: JobProcess):
    """Prewarm function to load voice activity detection (VAD) model."""
    proc.userdata["vad"] = silero.VAD.load()

async def get_video_track(room: rtc.Room):
    """Find and return the first available remote video track in the room."""
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
    raise ValueError("No remote video track found in the room")

async def get_latest_image(room: rtc.Room):
    """Capture and return a single frame from the video track."""
    video_stream = None
    try:
        video_track = await get_video_track(room)
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
            width = latest_image.width
            height = latest_image.height
            logger.debug(f"Captured image: width={width}, height={height}")
            image_content = [ChatImage(image=latest_image)]
            chat_ctx.messages.append(ChatMessage(role="user", content=[*image_content, "Please analyze the image I just shared."]))
            logger.debug("Added latest frame to conversation context")
        else:
            logger.warning("No image captured.")

    logger.info(f"🔗 Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)

    participant = await ctx.wait_for_participant()
    logger.info(f"🎙️ Starting voice assistant for participant {participant.identity}")

    # Fetch participant metadata (bot name)
    bot_name = await wait_for_metadata(participant)
    logger.info(f"🆔 Bot is now identified as: {bot_name}")

    # Use the bot name dynamically in the system message
    bot_template = templates.get(bot_name)
    if not bot_template:
        logger.warning(f"❌ No template found for bot name: {bot_name}")

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
                    f"You are an AI assistant designed for interactive, conversational feedback. "
                    f"You'll embody one of three expert personas, chosen by the user: {bot_name}.\n\n"
                    f"<prompt>\n{bot_name}\n"
                    f"Listen closely, as you'll be one of these experts:\n\n"
                    f"{bot_template}\n"
                    
                    f"Speak naturally, as if we're having a real conversation. "
                    f"Ask clarifying questions, offer specific suggestions, and truly understand the context.\n\n"
                    f"Let's make this feel like a genuine dialogue.\n\n"
                    f"When responding, remember:\n"
                    f"1. One point at a time – let's keep it focused.\n"
                    f"2. Brief and to the point – under 30 words.\n"
                    f"3. Simple language – easy to understand when spoken.\n"
                    f"4. Focus on conversational clarity.\n\n"
                    f"Your output should be the spoken response only, as if you are talking to the user.\n"
                    f"You will also receive images. Analyze these images and incorporate your observations into your responses.\n</prompt>"
                ),
            )

    # Initialize the voice assistant agent
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=azure.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=azure.TTS(voice="en-US-JennyNeural"), # Choose your preferred Azure voice
        turn_detector=turn_detector.EOUModel(),
        min_endpointing_delay=0.5,
        max_endpointing_delay=5.0,
        chat_ctx=initial_ctx,
        before_llm_cb=before_llm_cb,
    )

    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    # Start the assistant for the participant
    agent.start(ctx.room, participant)

    # Use the retrieved bot name in the greeting message
    greeting_message = f"Hey, I'm {bot_name}. How can I help you today?"
    await agent.say(greeting_message, allow_interruptions=True)

# Main execution
if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )