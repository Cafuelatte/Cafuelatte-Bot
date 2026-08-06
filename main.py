import os, asyncio, sqlite3, time, re, aiohttp, discord
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
        self.cursor.execute("CREATE TABLE IF NOT EXISTS active_timers (timer_key TEXT PRIMARY KEY, user_id INTEGER, channel_id INTEGER, message_id INTEGER, end_timestamp REAL)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS hamo_roles (role_name TEXT PRIMARY KEY, role_search_name TEXT, description TEXT)")
        self.conn.commit()

    async def setup_hook(self):
        self.cursor.execute("SELECT timer_key FROM active_timers")
        for row in self.cursor.fetchall():
            self.add_view(TimerView(self, row[0])) # [0] をつけてバグを修正
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")
        self.loop.create_task(self.resume_timers())
        self.loop.create_task(download_hamo_roles(self))

    async def resume_timers(self):
        await self.wait_until_ready()
        self.cursor.execute("SELECT timer_key, user_id, channel_id, message_id, end_timestamp FROM active_timers")
        for row in self.cursor.fetchall():
            timer_key, user_id, channel_id, message_id, end_timestamp = row
            remaining = int(end_timestamp - time.time())
            if remaining <= 0:
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        await msg.edit(content="**[Bot]** このタイマーは終了しました。", view=None)
                        await channel.send(f"**[Bot]** <@{user_id}> さん、再起動中にタイマーが終了していました。")
                    except: pass
                self.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
                self.conn.commit()
                continue
            self.active_timers[timer_key] = True
            asyncio.create_task(resume_countdown(self, timer_key, remaining, channel_id, message_id, user_id))

bot = MyBot()
@bot.event
async def on_ready():
    print(f'ログインに成功しました BOT名: {bot.user}')

def format_time(s: int) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"

def clean_text(t: str) -> str:
    return re.sub(r'<[^>]+>', '', t).strip() if t else ""

def katakana_to_hiragana(t: str) -> str:
    return "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in t).lower()

async def run_countdown(interaction: discord.Interaction, message: discord.Message, timer_key: str, total_seconds: int):
    while total_seconds > 0:
        sleep_time = min(5, total_seconds)
        await asyncio.sleep(sleep_time)
        if not bot.active_timers.get(timer_key, True): break
        total_seconds -= sleep_time
        try: await message.edit(content=f"**[Bot]** **{format_time(total_seconds)}**のタイマーを実行中。")
        except discord.NotFound: break
        except: pass
    try:
        if bot.active_timers.get(timer_key, True) and total_seconds <= 0:
            await message.edit(content="**[Bot]** タイマーが終了しました。", view=None)
            await interaction.channel.send(f"**[Bot]** {interaction.user.mention} さん、タイマーが終了しました。")
        elif not bot.active_timers.get(timer_key, True):
            await message.edit(content=f"**[Bot]** {interaction.user.mention} さんのタイマーはキャンセルされました。", view=None)
    except: pass
    if timer_key in bot.active_timers: del bot.active_timers[timer_key]
    bot.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
    bot.conn.commit()

async def resume_countdown(bot_instance, timer_key: str, total_seconds: int, channel_id: int, message_id: int, user_id: int):
    channel = bot_instance.get_channel(channel_id) or await bot_instance.fetch_channel(channel_id)
    message = None
    if channel:
        try: message = await channel.fetch_message(message_id)
        except: pass
    while total_seconds > 0:
        sleep_time = min(5, total_seconds)
        await asyncio.sleep(sleep_time)
        if not bot_instance.active_timers.get(timer_key, True): break
        total_seconds -= sleep_time
        if message:
            try: await message.edit(content=f"**[Bot]** **{format_time(total_seconds)}**のタイマーを実行中（復元）。")
            except discord.NotFound: break
            except: pass
    try:
        if bot_instance.active_timers.get(timer_key, True) and total_seconds <= 0:
            if message: await message.edit(content="**[Bot]** タイマーが終了しました。", view=None)
            if channel: await channel.send(f"**[Bot]** <@{user_id}> さん、タイマーが終了しました。")
        elif not bot_instance.active_timers.get(timer_key, True):
            if message: await message.edit(content="**[Bot]** <@{user_id}> さんのタイマーはキャンセルされました。", view=None)
    except: pass
    if timer_key in bot_instance.active_timers: del bot_instance.active_timers[timer_key]
    bot_instance.cursor.execute("DELETE FROM active_timers WHERE timer_key = ?", (timer_key,))
    bot_instance.conn.commit()

async def download_hamo_roles(bot_instance):
    url = "https://githubusercontent.com"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200: return
                data = await response.json()
                count = 0
                for key, value in data.items():
                    if key.startswith("Role.") and key.endswith(".Desc"):
                        internal_name = key.split(".")[1]
                        raw_name = data.get(f"Role.{internal_name}", internal_name)
                        role_name_jp = clean_text(raw_name)
                        description_jp = clean_text(value)
                        search_name = katakana_to_hiragana(role_name_jp) + internal_name.lower()
                        bot_instance.cursor.execute("INSERT OR REPLACE INTO hamo_roles VALUES (?, ?, ?)", (role_name_jp, search_name, description_jp))
                        count += 1
                bot_instance.conn.commit()
                print(f"TOH-hamoの役職データを同期しました。 (計 {count} 件)")
    except Exception as e: print(f"TOH-hamo同期エラー: {e}")

@bot.tree.command(name="ping", description="Pong")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('**[Bot]** Pong!')

@bot.tree.command(name="timer", description="タイマーをセットし、終了したらメンションします")
@app_commands.describe(hours="時間", minutes="分", seconds="秒")
async def timer(interaction: discord.Interaction, hours: int = 0, minutes: int = 0, seconds: int = 0):
    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    if total_seconds <= 0:
        await interaction.response.send_message("**[Bot]** タイマーは1秒からセットしてください。", ephemeral=True)
        return
    await interaction.response.send_message(f"**[Bot]** **{format_time(total_seconds)}**のタイマーをスタートしました。")
    message = await interaction.original_response()
    timer_key = f"{interaction.user.id}_{message.id}"
    bot.active_timers[timer_key] = True
    bot.cursor.execute("INSERT OR REPLACE INTO active_timers VALUES (?, ?, ?, ?, ?)", (timer_key, interaction.user.id, interaction.channel.id, message.id, time.time() + total_seconds))
    bot.conn.commit()
    await message.edit(view=TimerView(bot, timer_key))
    asyncio.create_task(run_countdown(interaction, message, timer_key, total_seconds))

@bot.tree.command(name="howrole", description="TOH-hamoの役職を調べます")
@app_commands.describe(role="役職名")
async def howrole_command(interaction: discord.Interaction, role: str):
    bot.cursor.execute("SELECT description FROM hamo_roles WHERE role_name = ?", (role,))
    row = bot.cursor.fetchone()
    if not row:
        await interaction.response.send_message(f"**[Bot]** **「{role}」**という役職は見つかりませんでした。", ephemeral=True)
        return
    embed = discord.Embed(title=f"役職を調べる: {role}", description=row[0], color=discord.Color.teal()) # [0] をつけて修正
    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@howrole_command.autocomplete("role")
async def role_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current_search = katakana_to_hiragana(current)
    bot.cursor.execute("SELECT role_name FROM hamo_roles WHERE role_search_name LIKE ? LIMIT 25", (f"%{current_search}%",))
    return [app_commands.Choice(name=row[0], value=row[0]) for row in bot.cursor.fetchall()] # row[0] に修正

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)
