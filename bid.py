import discord
from discord import app_commands
from discord.ext import commands
import requests

from config import api_url


def _base_url() -> str:
    return api_url if api_url else "http://localhost:8000"


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

    @bot.tree.command(name="참여", description="유저 이름을 등록합니다")
    @app_commands.describe(username="등록할 유저 이름")
    async def participate(interaction: discord.Interaction, username: str):
        await interaction.response.defer()

        try:
            payload = {
                "discord_username": interaction.user.name,
                "username": username,
            }
            response = requests.post(f"{_base_url()}/api/join", json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()
                embed = discord.Embed(title="✅ 참여 등록 완료", color=discord.Color.green())
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
