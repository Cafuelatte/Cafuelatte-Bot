import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'ログインに成功しました　BOT名: {bot.user}')

@bot.tree.command(name="ping", description="Pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!')

@bot.tree.command(name="timer", description="タイマーをセットし、終了したらメンションします")
@app_commands.describe(seconds="タイマーを測る秒数を入力してください")
async def timer(interaction: discord.Interaction, seconds: int):
    if seconds <= 0:
        await interaction.response.send_message("**[Bot]**　タイマーは1秒からセットしてください。", ephemeral=True)
        return
    await interaction.response.send_message(f"**[Bot]**　**{seconds}秒間**のタイマーをスタートしました。終了すると、メンションします。")
    await asyncio.sleep(seconds)
    await interaction.followup.send(f"**[Bot]**　{interaction.user.mention} さん、**{seconds}秒間**のタイマーが終了しました。")

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)