import discord
from discord.ext import commands
from discord import app_commands
import os
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

# -------------------- 봇 이벤트 핸들러 --------------------

@bot.event
async def on_ready():
    print(f'{bot.user} (으)로 로그인 성공!')

    # 슬래시 명령어 동기화 (특정 길드 즉시 반영)
    try:
        guild = discord.Object(id=1322870067163299861)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"{len(synced)}개의 슬래시 명령어를 동기화했습니다.")
    except Exception as e:
        print(f"명령어 동기화 실패: {e}")

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
            "이터니티": discord.Color.dark_red(),
            "데미갓": discord.Color.red(),
            "미스릴": discord.Color.dark_orange(),
            "메테오라이트": discord.Color.orange(),
            "다이아몬드": discord.Color.blue(),
            "플래티넘": discord.Color.light_grey(),
            "골드": discord.Color.gold(),
            "실버": discord.Color.greyple(),
            "브론즈": discord.Color.dark_gold(),
            "아이언": discord.Color.dark_grey()
        }

        # 임베드 생성
        embed = discord.Embed(
            title=f"🎮 {nickname}",
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
