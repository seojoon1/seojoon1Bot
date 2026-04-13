import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from dotenv import load_dotenv
import requests
from db import init_db, DB_PATH
from config import BOT_TOKEN, er_api_key, ER_API_BASE, SEASON_ID, MATCHING_TEAM_MODE
from food import register_food_command
from bid import register_bid_commands
from constants import EVENT_MESSAGES


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- DB 초기화 --------------------
init_db()



init_db()

# -------------------- 알림 태스크 --------------------

@tasks.loop(minutes=1)
async def event_notification_loop():
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    current_hour = now.hour
    current_minute = now.minute
    weekday = now.weekday()  # 월=0 ~ 일=6

    # 다음 정시까지 5분 남았는지 확인 (XX:55분일 때 발송)
    if current_minute != 55:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    next_hour = (current_hour + 1) % 24
    event_type = "짝수" if next_hour % 2 == 0 else "홀수"
    message = EVENT_MESSAGES.get(event_type)
    if message:
        c.execute(
            "SELECT user_id FROM subscriptions WHERE event_type = ? AND start_hour <= ? AND end_hour >= ?",
            (event_type, next_hour, next_hour)
        )
        for (user_id,) in c.fetchall():
            try:
                user = await bot.fetch_user(user_id)
                await user.send(f"🔔 [{event_type}시간 이벤트] {message}")
            except Exception as e:
                print(f"알림 발송 실패 (유저: {user_id}): {e}")

    # 나흐마: 토(5)/일(6) 21:55 KST
    if weekday in (5, 6) and current_hour == 21:
        nahma_msg = EVENT_MESSAGES.get("나흐마")
        if nahma_msg:
            c.execute("SELECT user_id FROM subscriptions WHERE event_type = ?", ("나흐마",))
            for (user_id,) in c.fetchall():
                try:
                    user = await bot.fetch_user(user_id)
                    await user.send(f"🔔 [나흐마] {nahma_msg}")
                except Exception as e:
                    print(f"나흐마 알림 발송 실패 (유저: {user_id}): {e}")

    conn.close()

# -------------------- 봇 이벤트 핸들러 --------------------

@bot.event
async def on_ready():
    print(f'{bot.user} (으)로 로그인 성공!')

    # 알림 루프 시작
    if not event_notification_loop.is_running():
        event_notification_loop.start()

    # 슬래시 명령어 동기화 - 글로벌 (모든 서버, 반영까지 최대 1시간)
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

# -------------------- /알림설정 명령어 --------------------

class EventTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="슈고만", value="슈고만", description="매 정시 5분 전 (짝수/홀수 이벤트)"),
            discord.SelectOption(label="all", value="all", description="슈고 + 나흐마(토/일 21:55)"),
        ]
        super().__init__(placeholder="알림 받을 이벤트를 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_type = self.values[0]
        self.view.stop()
        await interaction.response.defer()

class EventTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
        self.selected_type = None
        self.add_item(EventTypeSelect())

register_food_command(bot)

@bot.tree.command(name="알림설정", description="이벤트 정시 알림을 구독합니다 (5분 전 DM)")
@app_commands.describe(
    시작시간="알림 받을 시작 시각 (0~23, 예: 9)",
    종료시간="알림 받을 종료 시각 (0~23, 예: 23)"
)
async def set_notification(interaction: discord.Interaction, 시작시간: int, 종료시간: int):
    if not (0 <= 시작시간 <= 23) or not (0 <= 종료시간 <= 23):
        await interaction.response.send_message("❌ 시간은 0~23 사이여야 합니다.", ephemeral=True)
        return

    if 시작시간 >= 종료시간:
        await interaction.response.send_message("❌ 시작시간은 종료시간보다 작아야 합니다.", ephemeral=True)
        return

    view = EventTypeView()
    await interaction.response.send_message("알림 받을 이벤트 타입을 선택하세요:", view=view, ephemeral=True)
    await view.wait()

    if view.selected_type is None:
        await interaction.followup.send("❌ 시간 초과로 취소되었습니다.", ephemeral=True)
        return

    if view.selected_type == "슈고만":
        event_types = ["짝수", "홀수"]
    elif view.selected_type == "all":
        event_types = ["짝수", "홀수", "나흐마"]
    else:
        event_types = [view.selected_type]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for et in event_types:
        c.execute(
            "INSERT OR REPLACE INTO subscriptions (user_id, event_type, start_hour, end_hour) VALUES (?, ?, ?, ?)",
            (interaction.user.id, et, 시작시간, 종료시간)
        )
    conn.commit()
    conn.close()

    if view.selected_type == "슈고만":
        type_label = "슈고 (짝수+홀수)"
    elif view.selected_type == "all":
        type_label = "슈고 + 나흐마"
    else:
        type_label = view.selected_type
    print(f"[알림 구독] {interaction.user.name}({interaction.user.id}) | 이벤트: {type_label} | 시간: {시작시간}시~{종료시간}시")
    embed = discord.Embed(title="✅ 알림 구독 완료", color=discord.Color.green())
    embed.add_field(name="이벤트", value=type_label, inline=True)
    embed.add_field(name="활동 시간", value=f"{시작시간}시 ~ {종료시간}시", inline=True)
    embed.add_field(name="알림 타이밍", value="매 정시 5분 전 DM", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

# -------------------- /알림해제 명령어 --------------------

@bot.tree.command(name="알림해제", description="이벤트 알림 구독을 해제합니다")
async def unsubscribe_notification(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT event_type FROM subscriptions WHERE user_id = ?", (interaction.user.id,))
    rows = c.fetchall()

    if not rows:
        conn.close()
        await interaction.response.send_message("구독 중인 알림이 없습니다.", ephemeral=True)
        return

    c.execute("DELETE FROM subscriptions WHERE user_id = ?", (interaction.user.id,))
    conn.commit()
    conn.close()

    types = ", ".join(r[0] for r in rows)
    await interaction.response.send_message(f"✅ [{types}] 이벤트 알림이 해제되었습니다.", ephemeral=True)

# -------------------- /알림목록 명령어 --------------------

@bot.tree.command(name="알림목록", description="내 알림 구독 상태를 확인합니다")
async def list_notifications(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT event_type, start_hour, end_hour FROM subscriptions WHERE user_id = ?", (interaction.user.id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await interaction.response.send_message("구독 중인 알림이 없습니다.", ephemeral=True)
        return

    embed = discord.Embed(title="🔔 내 알림 구독 목록", color=discord.Color.blue())
    for event_type, start_hour, end_hour in rows:
        embed.add_field(
            name=f"{event_type}시간 이벤트",
            value=f"활동 시간: {start_hour}시 ~ {end_hour}시\n알림: 정시 5분 전 DM",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

register_bid_commands(bot)

# -------------------- /정보 명령어 --------------------

# 캐릭터 코드 → 이름 매핑
CHARACTER_NAMES = {
    1: "재키", 2: "아야", 3: "피오라", 4: "매그너스", 5: "자히르",
    6: "나딘", 7: "현우", 8: "하트", 9: "아이솔", 10: "리 다이린",
    11: "유키", 12: "혜진", 13: "쇼우", 14: "키아라", 15: "시셀라",
    16: "실비아", 17: "아드리아나", 18: "쇼이치", 19: "엠마", 20: "레녹스",
    21: "로지", 22: "루크", 23: "캐시", 24: "아델라", 25: "버니스",
    26: "바바라", 27: "알렉스", 28: "수아", 29: "레온", 30: "일레븐",
    31: "리오", 32: "윌리엄", 33: "니키", 34: "나타폰", 35: "얀",
    36: "이바", 37: "다니엘", 38: "제니", 39: "카밀로", 40: "클로에",
    41: "요한", 42: "비앙카", 43: "셀린", 44: "에키온", 45: "마이",
    46: "에이든", 47: "라우라", 48: "띠아", 49: "펠릭스", 50: "엘레나",
    51: "프리야", 52: "아디나", 53: "마커스", 54: "칼라", 55: "에스텔",
    56: "피올로", 57: "마르티나", 58: "헤이즈", 59: "아이작", 60: "타지아",
    61: "이렘", 62: "테오도르", 63: "이안", 64: "바냐", 65: "데비&마를렌",
    66: "아르다", 67: "아비게일", 68: "알론소", 69: "레니", 70: "츠바메",
    71: "케네스", 72: "카티야", 73: "샬럿", 74: "다르코", 75: "르노어",
    76: "가넷", 77: "유민", 78: "히스이", 79: "유스티나", 80: "이슈트반",
    81: "니아", 82: "슈린", 83: "헨리", 84: "블레어", 85: "미르카",
    86: "펜리르", 87: "코렐라인"
}

@bot.tree.command(name="정보", description="플레이어의 상세 정보를 조회합니다")
@app_commands.describe(
    nickname="조회할 닉네임"
)
async def player_info(interaction: discord.Interaction, nickname: str):
    """이터널리턴 API를 직접 호출해 플레이어 정보를 조회합니다"""
    await interaction.response.defer()

    if not er_api_key:
        await interaction.followup.send("❌ 이터널리턴 API 키가 설정되지 않았습니다. (.env의 ER_API_KEY)")
        return

    headers = {"x-api-key": er_api_key}

    try:
        # 1) 닉네임으로 userId 조회
        user_res = requests.get(
            f"{ER_API_BASE}/v1/user/nickname",
            params={"query": nickname},
            headers=headers,
            timeout=10
        )
        user_data = user_res.json()

        if user_data.get("code") != 200 or not user_data.get("user"):
            await interaction.followup.send(f"❌ '{nickname}' 유저를 찾을 수 없습니다.")
            return

        user_id = user_data["user"]["userId"]

        # 2) userId로 시즌 랭크 스쿼드 통계 조회
        stats_res = requests.get(
            f"{ER_API_BASE}/v2/user/stats/uid/{user_id}/{SEASON_ID}/{MATCHING_TEAM_MODE}",
            headers=headers,
            timeout=10
        )
        stats_data = stats_res.json()

        if stats_data.get("code") != 200 or not stats_data.get("userStats"):
            await interaction.followup.send(f"❌ '{nickname}'의 랭크 정보가 없습니다.")
            return

        stats = stats_data["userStats"][0]

        # 기본 정보
        mmr = stats["mmr"]
        rank = stats["rank"]
        total_games = stats["totalGames"]
        total_wins = stats["totalWins"]
        win_rate = round(total_wins / total_games * 100, 1) if total_games > 0 else 0
        avg_rank = stats["averageRank"]

        # 티어 계산
        if rank <= 300:
            tier = "이터니티"
        elif rank <= 1000:
            tier = "데미갓"
        elif mmr >= 7400:
            tier = "미스릴"
        elif mmr >= 6400:
            tier = "메테오라이트"
        elif mmr >= 5000:
            tier = "다이아몬드"
        elif mmr >= 3600:
            tier = "플래티넘"
        elif mmr >= 2400:
            tier = "골드"
        elif mmr >= 1400:
            tier = "실버"
        elif mmr >= 400:
            tier = "브론즈"
        else:
            tier = "아이언"

        tireColor = {
            "이터니티": discord.Color.from_rgb(255, 239, 179),   # 환한 골드/화이트
            "데미갓": discord.Color.from_rgb(220, 20, 60),       # 크림슨 레드
            "미스릴": discord.Color.from_rgb(64, 224, 208),      # 터쿼이즈
            "메테오라이트": discord.Color.from_rgb(138, 43, 226), # 바이올렛
            "다이아몬드": discord.Color.from_rgb(91, 192, 235),  # 라이트 블루
            "플래티넘": discord.Color.from_rgb(63, 183, 174),    # 틸
            "골드": discord.Color.from_rgb(255, 215, 0),         # 골드
            "실버": discord.Color.from_rgb(192, 192, 192),       # 실버
            "브론즈": discord.Color.from_rgb(169, 113, 66),      # 브론즈 브라운
            "아이언": discord.Color.from_rgb(107, 107, 107)      # 아이언 그레이
        }

        # 임베드 생성
        embed = discord.Embed(
            title=f"🎮 {nickname}",
            url=f"https://dak.gg/er/players/{quote(nickname)}",
            color=tireColor.get(tier, discord.Color.gold())
        )

        embed.add_field(
            name="기본 정보",
            value=(
                f"**티어:** {tier}\n"
                f"**MMR:** {mmr:,}\n"
                f"**랭킹:** {rank:,}위"
            ),
            inline=True
        )

        embed.add_field(
            name="전적",
            value=(
                f"**총 게임:** {total_games}판\n"
                f"**총 승수:** {total_wins}승\n"
                f"**승률:** {win_rate}%\n"
                f"**평균 순위:** {avg_rank}위"
            ),
            inline=True
        )


        # 모스트 캐릭터 (상위 3개)
        char_stats = stats.get("characterStats", [])[:3]
        if char_stats:
            most_lines = []
            for i, c in enumerate(char_stats, 1):
                char_name = CHARACTER_NAMES.get(c["characterCode"], f"#{c['characterCode']}")
                char_wins = c["wins"]
                char_games = c["totalGames"]
                char_wr = round(char_wins / char_games * 100, 1) if char_games > 0 else 0
                most_lines.append(f"{i}. {char_name} — {char_games}판 (승률{char_wr}%)")

            embed.add_field(
                name="most3",
                value="\n".join(most_lines),
                inline=False
            )

        await interaction.followup.send(embed=embed)

    except requests.exceptions.ConnectionError:
        await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
    except requests.exceptions.Timeout:
        await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {str(e)}")

# -------------------- 봇 실행 --------------------

if BOT_TOKEN:
    bot.run(BOT_TOKEN)
else:
    print("오류: .env 파일에서 BOT_TOKEN을 찾을 수 없습니다.")
