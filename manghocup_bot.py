"""망호컵 백엔드 연동 전용 봇 (배팅 / 참여 / 채팅 중계).

main.py 의 알림·음식·정보 기능과 분리해, 경매(배팅)·참여·실시간 채팅 중계
기능만 담당하는 별도 진입점.
"""

import discord
from discord.ext import commands

from config import BOT_TOKEN
from db import init_db
from bid import register_bid_commands
from chat_relay import register_chat_relay


intents = discord.Intents.default()
intents.message_content = True  # 채팅 중계에 필요

bot = commands.Bot(command_prefix="!", intents=intents)

# DB 초기화 (채팅 중계 채널 설정 저장용 settings 테이블 포함)
init_db()

# 기능 등록
register_bid_commands(bot)   # /bid, /참여, /참여자목록, /초기화
register_chat_relay(bot)     # 채팅 중계 + /중계채널설정·해제·확인


@bot.event
async def on_ready():
    print(f"{bot.user} (으)로 로그인 성공! (망호컵 봇)")

    # 슬래시 명령어 동기화 - 글로벌 (반영까지 최대 1시간)
    try:
        synced = await bot.tree.sync()
        print(f"글로벌: {len(synced)}개의 슬래시 명령어를 동기화했습니다.")
    except Exception as e:
        print(f"글로벌 명령어 동기화 실패: {e}")

    # 특정 길드 즉시 반영
    guild_ids = [1322870067163299861, 1006188392276561930]
    for gid in guild_ids:
        try:
            guild = discord.Object(id=gid)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"길드 {gid}: {len(synced)}개의 슬래시 명령어를 즉시 동기화했습니다.")
        except Exception as e:
            print(f"길드 {gid} 명령어 동기화 실패: {e}")


if __name__ == "__main__":
    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        print("오류: .env 파일에서 BOT_TOKEN(API_KEY)을 찾을 수 없습니다.")
