import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("API_KEY")
api_url = os.environ.get("API_URL")
er_api_key = os.environ.get("ER_API_KEY")
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# Gemini API 설정
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
# GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# 이터널리턴 API 설정
ER_API_BASE = "https://open-api.bser.io"
SEASON_ID = 37
MATCHING_TEAM_MODE = 3