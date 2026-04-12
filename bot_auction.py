import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from dotenv import load_dotenv
import requests

# -------------------- 초기 설정 --------------------

load_dotenv()
BOT_TOKEN = os.environ.get("API_KEY")
api_url = os.environ.get("API_URL")
er_api_key = os.environ.get("ER_API_KEY")

# 이터널리턴 API 설정
ER_API_BASE = "https://open-api.bser.io"
SEASON_ID = 37
MATCHING_TEAM_MODE = 3

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- DB 초기화 --------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notifications.db")

# 이벤트 메시지 (고정)
EVENT_MESSAGES = {
    "짝수": "점프점프 / 슈고 상인 보호 / 오드 방울 수집 / 망령 회피 / 이 타일 아닌가요?",
    "홀수": "골드린의 보물 / 히든 루기 / 높이높이 / 신비로운 트랙 / 팡팡팡",
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL,
            UNIQUE(user_id, event_type)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -------------------- 알림 태스크 --------------------

@tasks.loop(minutes=1)
async def event_notification_loop():
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    current_hour = now.hour
    current_minute = now.minute
    print(f"[알림 루프] 현재 KST 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 다음 정시까지 5분 남았는지 확인 (XX:55분일 때 발송)
    if current_minute != 55:
        return

    next_hour = (current_hour + 1) % 24

    # 다음 정시가 짝수인지 홀수인지
    if next_hour % 2 == 0:
        event_type = "짝수"
    else:
        event_type = "홀수"

    message = EVENT_MESSAGES.get(event_type)
    if not message:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 해당 이벤트를 구독 중이고, 현재 시각이 활동 시간대인 구독자 조회
    c.execute(
        "SELECT user_id FROM subscriptions WHERE event_type = ? AND start_hour <= ? AND end_hour >= ?",
        (event_type, next_hour, next_hour)
    )
    subscribers = c.fetchall()
    conn.close()

    print(f"[알림 루프] {event_type}시간 이벤트 | 구독자 수: {len(subscribers)}")

    for (user_id,) in subscribers:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(f"🔔 [{event_type}시간 이벤트] {message}")
            print(f"[알림 발송 성공] 유저: {user_id}")
        except Exception as e:
            print(f"[알림 발송 실패] 유저: {user_id} | 에러: {e}")

# -------------------- 봇 이벤트 핸들러 --------------------

@bot.event
async def on_ready():
    print(f'{bot.user} (으)로 로그인 성공!')

    # 알림 루프 시작
    if not event_notification_loop.is_running():
        event_notification_loop.start()

    # 슬래시 명령어 동기화 (특정 길드 즉시 반영)
    guild_ids = [1322870067163299861, 1006188392276561930]
    for gid in guild_ids:
        try:
            guild = discord.Object(id=gid)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"길드 {gid}: {len(synced)}개의 슬래시 명령어를 동기화했습니다.")
        except Exception as e:
            print(f"길드 {gid} 명령어 동기화 실패: {e}")

# -------------------- /알림설정 명령어 --------------------

class EventTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="짝수시간 이벤트", value="짝수", description="0, 2, 4, 6 ... 22시 이벤트"),
            discord.SelectOption(label="홀수시간 이벤트", value="홀수", description="1, 3, 5, 7 ... 23시 이벤트"),
            discord.SelectOption(label="둘 다", value="둘다", description="모든 정시 이벤트"),
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

    event_types = ["짝수", "홀수"] if view.selected_type == "둘다" else [view.selected_type]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for et in event_types:
        c.execute(
            "INSERT OR REPLACE INTO subscriptions (user_id, event_type, start_hour, end_hour) VALUES (?, ?, ?, ?)",
            (interaction.user.id, et, 시작시간, 종료시간)
        )
    conn.commit()
    conn.close()

    type_label = "짝수 + 홀수" if view.selected_type == "둘다" else f"{view.selected_type}시간"
    print(f"[알림 구독] {interaction.user.name}({interaction.user.id}) | 이벤트: {type_label} | 시간: {시작시간}시~{종료시간}시")
    embed = discord.Embed(title="✅ 알림 구독 완료", color=discord.Color.green())
    embed.add_field(name="이벤트", value=f"{type_label} 이벤트", inline=True)
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

# -------------------- /bid 명령어 --------------------

@bot.tree.command(name="bid", description="팀에 돈을 베팅합니다")
@app_commands.describe(
    team="팀명",
    amount="베팅 금액"
)
async def bid(interaction: discord.Interaction, team: str, amount: int):
    """로컬 백엔드 8000포트에 베팅 정보를 POST합니다"""
    # 팀장 역할 확인
    if not any(role.name == "팀장" for role in interaction.user.roles):
        await interaction.response.send_message(
            "❌ 이 명령어는 '팀장' 역할을 가진 사람만 사용할 수 있습니다.",
            ephemeral=True
        )
        return

    try:
        # 데이터 준비
        payload = {
            "team": team,
            "amount": amount,
            "user_id": str(interaction.user.id),
            "user_name": interaction.user.name
        }

        # 로컬 백엔드에 POST 요청
        response = requests.post(f"{api_url if api_url else 'http://localhost:8000'}/api/bid", json=payload, timeout=5)

        if response.status_code == 200:
            await interaction.response.send_message(
                f"✅ **{interaction.user.name}** 님이 **{team}** 팀에 **{amount}**만큼 베팅했습니다!",
                ephemeral=False
            )
        else:
            await interaction.response.send_message(
                f"❌ 베팅 실패: {response.text}",
                ephemeral=True
            )
    except requests.exceptions.ConnectionError:
        await interaction.response.send_message(
            "❌ 백엔드 서버에 연결할 수 없습니다. (localhost:8000)",
            ephemeral=True
        )
    except requests.exceptions.Timeout:
        await interaction.response.send_message(
            "❌ 백엔드 서버 응답 시간 초과",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ 오류 발생: {str(e)}",
            ephemeral=True
        )

# -------------------- /참여 명령어 --------------------

@bot.tree.command(name="참여", description="유저 이름을 등록합니다")
@app_commands.describe(
    username="등록할 유저 이름"
)
async def participate(interaction: discord.Interaction, username: str):
    """로컬 백엔드에 참여 정보를 POST합니다"""
    await interaction.response.defer()

    try:
        payload = {
            "discord_username": interaction.user.name,
            "username": username
        }

        base_url = api_url if api_url else "http://localhost:8000"
        response = requests.post(f"{base_url}/api/join", json=payload, timeout=10)

        if response.status_code == 200:
            data = response.json()
            embed = discord.Embed(
                title="✅ 참여 등록 완료",
                color=discord.Color.green()
            )
            embed.add_field(name="닉네임", value=data["username"], inline=True)
            embed.add_field(name="MMR", value=f"{data['mmr']:,}", inline=True)
            embed.add_field(name="티어", value=data["tier"], inline=True)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ 참여 등록 실패: {response.text}")
    except requests.exceptions.ConnectionError:
        await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
    except requests.exceptions.Timeout:
        await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {str(e)}")

# -------------------- /참여자목록 명령어 --------------------

@bot.tree.command(name="참여자목록", description="참여 등록된 플레이어 목록을 확인합니다")
async def player_list(interaction: discord.Interaction):
    """백엔드에서 참여자 목록을 조회합니다"""
    await interaction.response.defer()

    try:
        base_url = api_url if api_url else "http://localhost:8000"
        response = requests.get(f"{base_url}/api/players", timeout=10)

        if response.status_code == 200:
            data = response.json()
            players = data["players"]

            if not players:
                await interaction.followup.send("참여자가 없습니다.")
                return

            embed = discord.Embed(
                title="📋 참여자 목록",
                description=f"총 {len(players)}명",
                color=discord.Color.blue()
            )
            for p in players:
                embed.add_field(
                    name=p["username"],
                    value=f"디스코드: {p['discord_username']}\nMMR: {p['mmr']:,} | 티어: {p['tier']}",
                    inline=False
                )
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ 조회 실패: {response.text}")
    except requests.exceptions.ConnectionError:
        await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
    except requests.exceptions.Timeout:
        await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {str(e)}")

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
