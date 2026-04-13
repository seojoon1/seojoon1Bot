import discord
from discord import app_commands
from discord.ext import commands
import requests

from config import gemini_api_key, GEMINI_API_URL


class FoodSelect(discord.ui.Select):
    def __init__(self, key: str, placeholder: str, options: list[str]):
        self.key = key
        super().__init__(
            placeholder=placeholder,
            options=[discord.SelectOption(label=o, value=o) for o in options],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selections[self.key] = self.values[0]
        await interaction.response.defer()


class FoodRecommendView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.selections: dict[str, str] = {}
        self.add_item(FoodSelect("상황", "상황을 선택하세요", ["아침", "점심", "저녁", "야식", "간식", "회식"]))
        self.add_item(FoodSelect("온도", "온도를 선택하세요", ["뜨거운거", "차가운거", "미지근한거", "상관없음"]))
        self.add_item(FoodSelect("나라", "어느 나라 요리?", ["한식", "중식", "일식", "양식", "아시안", "상관없음"]))
        self.add_item(FoodSelect("종류", "종류를 선택하세요", ["밥", "빵", "면", "스프", "고기", "해산물", "샐러드", "상관없음"]))

    @discord.ui.button(label="추천받기", style=discord.ButtonStyle.primary, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        required = ["상황", "온도", "나라", "종류"]
        missing = [k for k in required if k not in self.selections]
        if missing:
            await interaction.response.send_message(
                f"❌ 아직 선택 안 한 항목: {', '.join(missing)}", ephemeral=True
            )
            return

        if not gemini_api_key:
            await interaction.response.send_message(
                "❌ Gemini API 키가 설정되지 않았습니다. (.env의 GEMINI_API_KEY)", ephemeral=True
            )
            return

        await interaction.response.defer()

        s = self.selections
        prompt = (
            f"당신은 음식 추천 전문가입니다. 아래 조건에 맞는 구체적인 메뉴 하나를 추천해주세요.\n"
            f"- 상황: {s['상황']}\n"
            f"- 온도: {s['온도']}\n"
            f"- 요리 국가: {s['나라']}\n"
            f"- 종류: {s['종류']}\n\n"
            f"형식: **메뉴이름**\n- 만 주세요. 설명이나 부가 정보는 필요 없어요. 메뉴 이름만 정확히 답해주세요. 예시) **김치찌개**"
        )

        try:
            res = requests.post(
                f"{GEMINI_API_URL}?key={gemini_api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15,
            )
            if res.status_code != 200:
                body = res.text[:1500]
                await interaction.followup.send(f"❌ Gemini API 오류: {res.status_code}\n```{body}```")
                return
            data = res.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"][:4000]
        except requests.exceptions.Timeout:
            await interaction.followup.send("❌ Gemini API 응답 시간 초과")
            return
        except Exception as e:
            await interaction.followup.send(f"❌ 오류 발생: {str(e)}")
            return

        embed = discord.Embed(title="🍽️ 오늘의 추천 메뉴", description=text, color=discord.Color.orange())
        embed.add_field(
            name="선택한 조건",
            value=f"{s['상황']} · {s['온도']} · {s['나라']} · {s['종류']}",
            inline=False,
        )
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(embed=embed)


def register_food_command(bot: commands.Bot):
    @bot.tree.command(name="뭐먹지", description="상황/온도/나라/종류를 골라서 Gemini가 메뉴를 추천해줘요")
    async def what_to_eat(interaction: discord.Interaction):
        await interaction.response.send_message(
            "먹고 싶은 조건을 골라주세요 (4개 모두 선택 후 '추천받기' 클릭):",
            view=FoodRecommendView(),
            ephemeral=True,
        )
