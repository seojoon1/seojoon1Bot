import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import BACKEND_URL, CHAT_RELAY_CHANNEL_ID
from db import get_setting, set_setting, delete_setting

logger = logging.getLogger(__name__)

# 웹 패널 표시 깨짐 방지를 위한 메시지 최대 길이
MAX_MESSAGE_LEN = 200
# 명령어(prefix)로 시작하는 메시지는 중계하지 않음
COMMAND_PREFIX = "!"
# 백엔드 요청 타임아웃(초)
REQUEST_TIMEOUT = 5
# 중계 채널 ID 를 저장하는 설정 키
SETTING_KEY = "chat_relay_channel_id"


def get_relay_channel_id():
    """현재 중계 채널 ID 를 반환한다. DB 설정 우선, 없으면 환경변수 fallback."""
    value = get_setting(SETTING_KEY)
    if value and value.isdigit():
        return int(value)
    return CHAT_RELAY_CHANNEL_ID


def register_chat_relay(bot: commands.Bot):
    """중계 채널의 일반 메시지를 백엔드 /api/chat 으로 비동기 전송한다."""

    @bot.listen("on_message")
    async def relay_chat(message: discord.Message):
        # 1) 봇/다른 봇 메시지 무시 (무한루프 방지)
        if message.author.bot:
            return

        # 2) 중계 채널 미설정이면 비활성화
        relay_channel_id = get_relay_channel_id()
        if relay_channel_id is None:
            return

        # 3) 지정한 중계 채널이 아니면 무시
        if message.channel.id != relay_channel_id:
            return

        content = message.content or ""

        # 4) 명령어(prefix로 시작)는 중계하지 않음
        if content.startswith(COMMAND_PREFIX):
            return

        # 5) 빈 메시지/첨부파일만 있는 메시지는 보내지 않음
        content = content.strip()
        if not content:
            return

        # 6) 너무 긴 메시지는 잘라서 전송
        if len(content) > MAX_MESSAGE_LEN:
            content = content[:MAX_MESSAGE_LEN]

        payload = {
            "username": message.author.display_name,  # 서버 별명
            "message": content,
        }

        # 7) 전송 실패/타임아웃에도 봇이 죽지 않도록 방어 (채팅 흐름은 막지 않음)
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{BACKEND_URL}/api/chat", json=payload) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning("채팅 중계 실패 (status=%s): %s", resp.status, body)
        except aiohttp.ClientError as e:
            logger.warning("채팅 중계 연결 오류: %s", e)
        except Exception as e:
            logger.warning("채팅 중계 중 예외 발생: %s", e)

    @bot.tree.command(
        name="중계채널설정",
        description="이 채널(또는 지정 채널)을 실시간 채팅 중계 채널로 설정합니다 (관리자 전용)",
    )
    @app_commands.describe(채널="중계할 채널 (생략 시 명령어를 입력한 채널)")
    async def set_relay_channel(
        interaction: discord.Interaction,
        채널: discord.TextChannel = None,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        target = 채널 or interaction.channel
        set_setting(SETTING_KEY, str(target.id))
        await interaction.response.send_message(
            f"✅ 실시간 채팅 중계 채널이 {target.mention} (으)로 설정되었습니다.",
            ephemeral=True,
        )

    @bot.tree.command(
        name="중계채널해제",
        description="실시간 채팅 중계를 비활성화합니다 (관리자 전용)",
    )
    async def unset_relay_channel(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        delete_setting(SETTING_KEY)
        await interaction.response.send_message(
            "✅ 실시간 채팅 중계가 비활성화되었습니다.", ephemeral=True
        )

    @bot.tree.command(
        name="중계채널확인",
        description="현재 설정된 실시간 채팅 중계 채널을 확인합니다 (관리자 전용)",
    )
    async def show_relay_channel(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 이 명령어는 관리자만 사용할 수 있습니다.", ephemeral=True
            )
            return

        relay_channel_id = get_relay_channel_id()
        if relay_channel_id is None:
            await interaction.response.send_message(
                "ℹ️ 현재 중계 채널이 설정되어 있지 않습니다.", ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(relay_channel_id) if interaction.guild else None
        if channel:
            await interaction.response.send_message(
                f"ℹ️ 현재 중계 채널: {channel.mention}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ 현재 중계 채널 ID: `{relay_channel_id}` (이 서버에서 찾을 수 없음)",
                ephemeral=True,
            )
