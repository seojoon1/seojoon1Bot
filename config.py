import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("API_KEY")
api_url = os.environ.get("API_URL")
er_api_key = os.environ.get("ER_API_KEY")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# 망호컵 백엔드 공통 베이스 URL (/api/bid, /api/join, /api/chat 등에서 재사용)
BACKEND_URL = api_url if api_url else "http://localhost:8000"

# 실시간 채팅 중계 대상 채널 ID (미설정 시 중계 비활성화)
_chat_relay_channel = os.environ.get("CHAT_RELAY_CHANNEL_ID")
CHAT_RELAY_CHANNEL_ID = (
    int(_chat_relay_channel) if _chat_relay_channel and _chat_relay_channel.strip().isdigit() else None
)

# Gemini API 설정
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
# GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# 이터널리턴 API 설정
ER_API_BASE = "https://open-api.bser.io"
SEASON_ID = 37
MATCHING_TEAM_MODE = 3