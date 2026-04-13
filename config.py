import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.environ.get("API_KEY")
api_url = os.environ.get("API_URL")
er_api_key = os.environ.get("ER_API_KEY")

# 이터널리턴 API 설정
ER_API_BASE = "https://open-api.bser.io"
SEASON_ID = 37
MATCHING_TEAM_MODE = 3