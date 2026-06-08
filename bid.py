import discord
from discord import app_commands
from discord.ext import commands
import requests

from config import BACKEND_URL


def _base_url() -> str:
    return BACKEND_URL


def _join_error_message(response) -> str:
    """/api/join 의 에러 응답을 사용자 친화적 메시지로 변환한다."""
    # 백엔드는 평문 또는 {"detail": "..."} 형태로 메시지를 줄 수 있음
    detail = ""
    try:
        body = response.json()
        detail = body.get("detail", "") if isinstance(body, dict) else str(body)
    except ValueError:
        detail = (response.text or "").strip()

    if response.status_code == 400:
        return "❌ 자기어필을 입력해주세요. (빈 값/공백은 등록할 수 없습니다)"
    if response.status_code == 404:
        if "랭크" in detail:
            return "❌ 해당 시즌의 랭크 기록을 찾을 수 없습니다. 랭크 게임을 플레이한 뒤 다시 시도해주세요."
        return "❌ 유저를 찾을 수 없습니다. 이터널리턴 닉네임을 정확히 입력했는지 확인해주세요."
    if response.status_code == 422:
        return "❌ 요청 형식 오류입니다. 봇 관리자에게 문의해주세요. (필드 누락)"
    return f"❌ 참여 등록 실패: {detail or response.text}"


APPEAL_MAX_LEN = 100


class JoinModal(discord.ui.Modal, title="망호컵 참여 등록"):
    username = discord.ui.TextInput(
        label="이터널리턴 닉네임",
        placeholder="디스코드 이름이 아닌 게임 내 실제 닉네임",
        required=True,
        max_length=50,
    )
    appeal = discord.ui.TextInput(
        label="자기어필",
        placeholder="자신을 어필해주세요 (줄바꿈 가능)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=APPEAL_MAX_LEN,
    )

    async def on_submit(self, interaction: discord.Interaction):
        username = str(self.username).strip()
        appeal = str(self.appeal).strip()

        # 빈/공백 검증 (모달 required는 공백만 입력하면 통과될 수 있음)
        if not appeal:
            await interaction.response.send_message(
                "❌ 자기어필을 입력해주세요. (빈 값/공백은 등록할 수 없습니다)",
                ephemeral=True,
            )
            return
        if not username:
            await interaction.response.send_message(
                "❌ 이터널리턴 닉네임을 입력해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            payload = {
                "discord_username": interaction.user.name,
                "username": username,  # 이터널리턴 닉네임
                "appeal": appeal,
            }
            response = requests.post(f"{_base_url()}/api/join", json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                embed = discord.Embed(
                    title="✅ 참여 등록 완료",
                    description="※ 같은 디스코드 계정으로 재등록하면 정보가 갱신됩니다.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="닉네임", value=data["username"], inline=True)
                embed.add_field(name="MMR", value=f"{data['mmr']:,}", inline=True)
                embed.add_field(name="티어", value=data["tier"], inline=True)
                embed.add_field(name="자기어필", value=data.get("appeal", appeal), inline=False)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(_join_error_message(response))
        except requests.exceptions.ConnectionError:
            await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
        except requests.exceptions.Timeout:
            await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류 발생: {str(e)}")


def register_bid_commands(bot: commands.Bot):
    @bot.tree.command(name="bid", description="팀에 돈을 베팅합니다")
    @app_commands.describe(team="팀명", amount="베팅 금액")
    async def bid(interaction: discord.Interaction, team: str, amount: int):
        if not any(role.name == "팀장" for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ 이 명령어는 '팀장' 역할을 가진 사람만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        try:
            payload = {
                "team": team,
                "amount": amount,
                "user_id": str(interaction.user.id),
                "user_name": interaction.user.name,
            }
            response = requests.post(f"{_base_url()}/api/bid", json=payload, timeout=5)

            if response.status_code == 200:
                await interaction.response.send_message(
                    f"✅ **{interaction.user.name}** 님이 **{team}** 팀에 **{amount}**만큼 베팅했습니다!",
                    ephemeral=False,
                )
            else:
                await interaction.response.send_message(
                    f"❌ 베팅 실패: {response.text}", ephemeral=True
                )
        except requests.exceptions.ConnectionError:
            await interaction.response.send_message(
                "❌ 백엔드 서버에 연결할 수 없습니다. (localhost:8000)", ephemeral=True
            )
        except requests.exceptions.Timeout:
            await interaction.response.send_message("❌ 백엔드 서버 응답 시간 초과", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {str(e)}", ephemeral=True)

    @bot.tree.command(
        name="참여",
        description="이터널리턴 닉네임과 자기어필을 등록합니다 (재등록 시 정보가 갱신됩니다)",
    )
    async def participate(interaction: discord.Interaction):
        await interaction.response.send_modal(JoinModal())

    @bot.tree.command(name="참여자목록", description="참여 등록된 플레이어 목록을 확인합니다")
    async def player_list(interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            response = requests.get(f"{_base_url()}/api/players", timeout=10)

            if response.status_code == 200:
                data = response.json()
                players = data["players"]

                if not players:
                    await interaction.followup.send("참여자가 없습니다.")
                    return

                embed = discord.Embed(
                    title="📋 참여자 목록",
                    description=f"총 {len(players)}명",
                    color=discord.Color.blue(),
                )
                for p in players:
                    embed.add_field(
                        name=p["username"],
                        value=f"디스코드: {p['discord_username']}\nMMR: {p['mmr']:,} | 티어: {p['tier']}",
                        inline=False,
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

    @bot.tree.command(name="초기화", description="참여자 정보를 모두 초기화합니다 (관리자 전용)")
    async def reset(interaction: discord.Interaction):
        # 관리자(서버 관리 권한) 전용
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            response = requests.post(f"{_base_url()}/api/reset", timeout=10)

            if response.status_code == 200:
                await interaction.followup.send("✅ 참여자 정보가 모두 초기화되었습니다.")
            else:
                await interaction.followup.send(f"❌ 초기화 실패: {response.text}")
        except requests.exceptions.ConnectionError:
            await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
        except requests.exceptions.Timeout:
            await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류 발생: {str(e)}")

    @bot.tree.command(name="목데이터", description="테스트용 목 데이터를 생성합니다 (관리자 전용)")
    async def mock(interaction: discord.Interaction):
        # 관리자(서버 관리 권한) 전용
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            response = requests.post(f"{_base_url()}/api/mock", timeout=10)

            if response.status_code == 200:
                await interaction.followup.send("✅ 목 데이터가 생성되었습니다.")
            else:
                await interaction.followup.send(f"❌ 목 데이터 생성 실패: {response.text}")
        except requests.exceptions.ConnectionError:
            await interaction.followup.send("❌ 백엔드 서버에 연결할 수 없습니다.")
        except requests.exceptions.Timeout:
            await interaction.followup.send("❌ 백엔드 서버 응답 시간 초과")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류 발생: {str(e)}")
