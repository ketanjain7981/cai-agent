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

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

def prewarm(proc: JobProcess):
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
                selected_person = metadata.get("selectedPerson", "Unknown")
                bot_name = metadata.get("botName", "VoiceBot")
                logger.info(f"✅ Metadata found for {participant.identity}: {selected_person}, Bot Name: {bot_name}")
                return selected_person, bot_name
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse metadata for {participant.identity}: {e}")
        
        logger.info(f"⏳ Waiting for metadata... Attempt {attempt + 1}/{max_retries}")
        await asyncio.sleep(delay)

    logger.warning(f"⚠️ Metadata not found after {max_retries} retries. Using defaults.")
    return "Unknown", "VoiceBot"

async def fetch_metadata_again(ctx, participant, retry_after=5):
    """Fetch metadata again after waiting for some time."""
    await asyncio.sleep(retry_after)
    logger.info("🔄 Fetching participant metadata again after initial failure...")
    return await wait_for_metadata(participant, max_retries=5, delay=2.0)

async def entrypoint(ctx: JobContext):
    async def before_llm_cb(assistant: VoicePipelineAgent, chat_ctx: llm.ChatContext):
        """Callback that runs before LLM generates a response, capturing video frames."""
        latest_image = await get_latest_image(ctx.room)
        if latest_image:
            image_content = [ChatImage(image=latest_image)]
            chat_ctx.messages.append(ChatMessage(role="user", content=image_content))
            logger.debug("Added latest frame to conversation context")

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a voice assistant created by LiveKit that can both see and hear. "
            "You should use short and concise responses, avoiding unpronounceable punctuation. "
            "When you see an image in our conversation, naturally incorporate what you see "
            "into your response. Keep visual descriptions brief but informative."
        ),
    )

    logger.info(f"🔗 Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
    
    if ctx.room.metadata:
        logger.info(f"Room metadata found: {ctx.room.metadata}")
        print(f"Room metadata: {ctx.room.metadata}")
    else:
        logger.info("Room metadata is empty.")
        print("Room metadata is empty.")

    participant = await ctx.wait_for_participant()
    logger.info(f"🎙️ Starting voice assistant for participant {participant.identity}")

    selected_person, bot_name = await wait_for_metadata(participant)
    
    if selected_person == "Unknown":
        selected_person, bot_name = await fetch_metadata_again(ctx, participant)

    logger.info(f"🔹 Final participant metadata: {participant.metadata}")
    logger.info(f"🆔 Bot is now identified as: {bot_name}")

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

    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    agent.start(ctx.room, participant)
    
    greeting_message = f"Hey {selected_person}, how can I help you today?" if selected_person != "Unknown" else "Hey there, how can I help you today?"
    await agent.say(greeting_message, allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )