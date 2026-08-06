import os
import asyncio
import sqlite3
import time
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

class TimerView(discord.ui.View):
    def __init__(self, bot_instance, timer_key: str):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance
        self.timer_key = timer_key

    @discord.ui.button(label="タイマーを終了", style=discord.ButtonStyle.danger, custom_id="stop_timer_btn")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = int(self.timer_key.split("_")[0])
        if interaction.user.id != user_id:
            await interaction.response.send_message("このタイマーはあなたの所有物ではありません。", ephemeral=True)
            return

        await interaction.response.defer()
        if self.timer_key in self.bot_instance.active_timers:
            self.bot_instance.active_timers[self.timer_key] = False

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.active_timers = {}
        
        self.conn = sqlite3.connect("timers.db")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_timers (
                timer_key TEXT PRIMARY KEY,
                user_id INTEGER,
                channel_id INTEGER,
                end_timestamp REAL
            )
        """)
        self.conn.commit()

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")

bot = MyBot()

@bot.event
async def on_ready():
    print(f'ログインに成功しました　BOT名: {bot.user}')

def format_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

async def run_countdown(interaction: discord.Interaction, message: discord.Message, timer_key: str, total_seconds: int, hours: int, minutes: int, seconds: int):
    while total_seconds > 0:
        await asyncio.sleep(1)
        
        if not bot.active_timers.get(timer_key, True):
            break

        total_seconds -= 1
        time_str = format_time(total_seconds)
        
        try:
            await message.edit(content=f"**[Bot]**　**{time_str}**のタイマーをスタートしました。終了すると、メンションします。")
        except discord.NotFound:
            break

    if bot.active_timers.get(timer_key, True) and total_seconds <= 0:
        try:
            original_time_str = format_time((hours * 3600) + (minutes * 60) + seconds)
            await message.edit(view=None)
            await interaction.channel.send(f"**[Bot]**　{interaction.user.mention} さん、**{original_time_str}**のタイマーが終了しました。")
        except discord.NotFound:
            pass
    elif not bot.active_timers.get(timer_key, True):
        try:
            await message.edit(content=f"**[Bot]**　{interaction.user.mention} さんのタイマーは**キャンセル**されました。", view=None)
        except discord.NotFound:
            pass

    if timer_key in bot.active_timers:
        del bot.active_timers[timer_key]
        
    bot.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
    bot.conn.commit()

@bot.tree.command(name="ping", description="Pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('**[Bot]**　Pong!')

@bot.tree.command(name="timer", description="タイマーをセットし、終了したらメンションします")
@app_commands.describe(
    hours="時間",
    minutes="分",
    seconds="秒"
)
async def timer(interaction: discord.Interaction, hours: int = 0, minutes: int = 0, seconds: int = 0):
    total_seconds = (hours * 3600) + (minutes * 60) + seconds

    if total_seconds <= 0:
        await interaction.response.send_message("**[Bot]**　タイマーは1秒からセットしてください。", ephemeral=True)
        return

    time_str = format_time(total_seconds)
    await interaction.response.send_message(f"**[Bot]**　**{time_str}**のタイマーをスタートしました。終了すると、メンションします。")
    
    message = await interaction.original_response()
    timer_key = f"{interaction.user.id}_{message.id}"
    
    bot.active_timers[timer_key] = True
    end_timestamp = time.time() + total_seconds
    
    bot.cursor.execute(
        "INSERT OR REPLACE INTO active_timers VALUES (?, ?, ?, ?)",
        (timer_key, interaction.user.id, interaction.channel.id, end_timestamp)
    )
    bot.conn.commit()

    view = TimerView(bot, timer_key)
    await message.edit(view=view)

    asyncio.create_task(run_countdown(interaction, message, timer_key, total_seconds, hours, minutes, seconds))

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)