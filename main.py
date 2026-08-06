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
        # タイムアウトをなしにする
        super().__init__(timeout=None)
        self.bot_instance = bot_instance
        self.timer_key = timer_key
        
        # 【重要】再起動後もボタンを識別できるよう、custom_id に timer_key を埋め込む
        self.stop_button.custom_id = f"stop_{timer_key}"

    @discord.ui.button(label="タイマーを終了", style=discord.ButtonStyle.danger)
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
        super().__init__(command_prefix="!_", intents=intents)
        self.active_timers = {}
        
        self.conn = sqlite3.connect("timers.db")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_timers (
                timer_key TEXT PRIMARY KEY,
                user_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                end_timestamp REAL
            )
        """)
        self.conn.commit()

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")
        
        # ボット再起動時に、DBにあるタイマーのボタン（View）をすべて再登録する
        self.cursor.execute("SELECT timer_key FROM active_timers")
        rows = self.cursor.fetchall()
        for row in rows:
            timer_key = row[0]
            self.add_view(TimerView(self, timer_key))
            
        self.loop.create_task(self.resume_timers())

    async def resume_timers(self):
        await self.wait_until_ready()
        
        self.cursor.execute("SELECT timer_key, user_id, channel_id, message_id, end_timestamp FROM active_timers")
        rows = self.cursor.fetchall()
        
        for row in rows:
            timer_key, user_id, channel_id, message_id, end_timestamp = row
            current_time = time.time()
            remaining_seconds = int(end_timestamp - current_time)
            
            # 再起動した時点で既に終了時間を過ぎていた場合
            if remaining_seconds <= 0:
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                if channel:
                    try:
                        # 過去のメッセージを未処理のまま残さないよう、Viewを消去して終了表示にする
                        message = await channel.fetch_message(message_id)
                        await message.edit(content=f"**[Bot]**　このタイマーは終了しました。", view=None)
                        await channel.send(f"**[Bot]** <@{user_id}> さん、ボット再起動中にタイマーが終了していました。")
                    except Exception:
                        pass
                self.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
                self.conn.commit()
                continue
            
            self.active_timers[timer_key] = True
            asyncio.create_task(resume_countdown(self, timer_key, remaining_seconds, channel_id, message_id, user_id))

bot = MyBot()

@bot.event
async def on_ready():
    print(f'ログインに成功しました　BOT名: {bot.user}')

def format_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

async def run_countdown(interaction: discord.Interaction, message: discord.Message, timer_key: str, total_seconds: int):
    channel_id = interaction.channel.id
    message_id = message.id
    user_id = interaction.user.id

    while total_seconds > 0:
        sleep_time = min(5, total_seconds)
        await asyncio.sleep(sleep_time)
        
        if not bot.active_timers.get(timer_key, True):
            break

        total_seconds -= sleep_time
        time_str = format_time(total_seconds)
        
        try:
            await message.edit(content=f"**[Bot]**　**{time_str}**のタイマーを実行中。終了すると、メンションします。")
        except discord.NotFound:
            break
        except discord.HTTPException:
            pass

    # 終了・キャンセル時のメッセージ更新処理を確実に実行する
    try:
        if bot.active_timers.get(timer_key, True) and total_seconds <= 0:
            await message.edit(content=f"**[Bot]**　タイマーが終了しました。", view=None)
            await interaction.channel.send(f"**[Bot]**　{interaction.user.mention} さん、タイマーが終了しました。")
        elif not bot.active_timers.get(timer_key, True):
            await message.edit(content=f"**[Bot]**　{interaction.user.mention} さんのタイマーは**キャンセル**されました。", view=None)
    except discord.HTTPException:
        pass

    if timer_key in bot.active_timers:
        del bot.active_timers[timer_key]
        
    bot.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
    bot.conn.commit()

async def resume_countdown(bot_instance, timer_key: str, total_seconds: int, channel_id: int, message_id: int, user_id: int):
    channel = bot_instance.get_channel(channel_id) or await bot_instance.fetch_channel(channel_id)
    message = None
    if channel:
        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            pass

    while total_seconds > 0:
        sleep_time = min(5, total_seconds)
        await asyncio.sleep(sleep_time)
        
        if not bot_instance.active_timers.get(timer_key, True):
            break

        total_seconds -= sleep_time
        time_str = format_time(total_seconds)
        
        if message:
            try:
                await message.edit(content=f"**[Bot]**　**{time_str}**のタイマーを実行中（復元）。終了すると、メンションします。")
            except discord.NotFound:
                break
            except discord.HTTPException:
                pass

    try:
        if bot_instance.active_timers.get(timer_key, True) and total_seconds <= 0:
            if message:
                await message.edit(content=f"**[Bot]**　タイマーが終了しました。", view=None)
            if channel:
                await channel.send(f"**[Bot]**　<@{user_id}> さん、タイマーが終了しました。")
        elif not bot_instance.active_timers.get(timer_key, True):
            if message:
                await message.edit(content=f"**[Bot]**　<@{user_id}> さんのタイマーは**キャンセル**されました。", view=None)
    except discord.HTTPException:
        pass

    if timer_key in bot_instance.active_timers:
        del bot_instance.active_timers[timer_key]
        
    bot_instance.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
    bot_instance.conn.commit()

@bot.tree.command(name="ping", description="Pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('**[Bot]**　Pong!')

@bot.tree.command(name="timer", description="タイマーをセットし、終了したらメンションします")
@app_commands.describe(hours="時間", minutes="分", seconds="秒")
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
        "INSERT OR REPLACE INTO active_timers VALUES (?, ?, ?, ?, ?)",
        (timer_key, interaction.user.id, interaction.channel.id, message.id, end_timestamp)
    )
    bot.conn.commit()

    view = TimerView(bot, timer_key)
    await message.edit(view=view)

    asyncio.create_task(run_countdown(interaction, message, timer_key, total_seconds))

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)