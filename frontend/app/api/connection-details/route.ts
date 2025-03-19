import { NextRequest, NextResponse } from "next/server";
import { randomString } from "@/lib/client-utils";
import { ConnectionDetails } from "@/lib/types";
import { AccessToken, AccessTokenOptions, VideoGrant } from "livekit-server-sdk";

const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const COOKIE_KEY = "random-participant-postfix";

export async function GET(request: NextRequest) {
  try {
    // Extract query parameters
    const roomName = request.nextUrl.searchParams.get("roomName");
    const participantName = request.nextUrl.searchParams.get("participantName");
    let metadata = request.nextUrl.searchParams.get("metadata") ?? ""; // ✅ Extract metadata

    if (!roomName || !participantName) {
      return new NextResponse("Missing required parameters", { status: 400 });
    }

    // ✅ Debugging: Log metadata before assigning
    if (!metadata) {
      console.warn(`⚠️ Warning: No metadata received for participant ${participantName}`);
    } else {
      console.log(`✅ Received metadata for ${participantName}: ${metadata}`);
    }

    // ✅ Ensure metadata is valid JSON
    try {
      JSON.parse(metadata);
    } catch {
      console.error(`❌ Invalid JSON metadata: ${metadata}`);
      metadata = JSON.stringify({ selectedPerson: participantName }); // ✅ Default to participantName
    }

    console.log(`🚀 Assigning metadata to participant ${participantName}:`, metadata);

    // Generate a unique participant identity
    const participantIdentity = `${participantName}__${randomString(4)}`;

    // Generate a participant token
    const participantToken = await createParticipantToken(
      {
        identity: participantIdentity,
        name: participantName,
        metadata, // ✅ Ensure metadata is assigned
      },
      roomName,
    );

    return NextResponse.json({
      serverUrl: LIVEKIT_URL,
      roomName,
      participantToken,
      participantName,
    });
  } catch (error) {
    console.error("❌ Error generating participant token:", error);
    return new NextResponse("Internal Server Error", { status: 500 });
  }
}

function createParticipantToken(userInfo: AccessTokenOptions, roomName: string) {
  const at = new AccessToken(API_KEY, API_SECRET, userInfo);
  at.ttl = "5m"; // Token expires in 5 minutes
  at.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  });
  return at.toJwt();
}

function getLiveKitURL(region: string | null): string {
  let targetKey = "LIVEKIT_URL";
  if (region) {
    targetKey = `LIVEKIT_URL_${region}`.toUpperCase();
  }
  const url = process.env[targetKey];
  if (!url) {
    throw new Error(`${targetKey} is not defined`);
  }
  return url;
}
