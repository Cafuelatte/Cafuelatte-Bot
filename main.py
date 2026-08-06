import os, asyncio, sqlite3, time, re, aiohttp, discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True

class TimerView(discord.ui.View):
    def __init__(self, bot, key):
        super().__init__(timeout=None)
        self.bot, self.key = bot, key
        self.stop_btn.custom_id = f"stop_{key}"
    @discord.ui.button(label="タイマーを終了", style=discord.ButtonStyle.danger)
    async def stop_btn(self, i, btn):
        if i.user.id != int(self.key.split("_")):
            return await i.response.send_message("このタイマーはあなたの所有物ではありません。", ephemeral=True)
        await i.response.defer()
        if self.key in self.bot.timers: self.bot.timers[self.key] = False

async def download_hamo(bot_instance):
    # 確実に「raw.」が入った正しい公式JSONファイルのURLに一本化しました
    endpoint = "https://githubusercontent.com"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(endpoint) as res:
                if res.status != 200: return
                data = await res.json()
                count = 0
                for k, v in data.items():
                    if k.startswith("Role.") and k.endswith(".Desc"):
                        parts = k.split(".")
                        if len(parts) < 2: continue
                        # リスト型エラーが起きないようインデックス[1]で文字列を確実に抽出
                        iname = parts[1]
                        
                        raw = data.get(f"Role.{iname}", iname)
                        name = re.sub(r'<[^>]+>', '', str(raw)).strip()
                        desc = re.sub(r'<[^>]+>', '', str(v)).strip()
                        sname = conv(name) + iname.lower()
                        bot_instance.cur.execute("INSERT OR REPLACE INTO hamo_roles VALUES (?, ?, ?)", (name, sname, desc))
                        count += 1
                bot_instance.conn.commit()
                print(f"TOH-hamoの役職データを同期しました。 (計 {count} 件)")
    except Exception as e:
        print(f"同期システム内部でエラーが発生しました: {e}")

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!_", intents=intents)
        self.timers = {}
        self.conn = sqlite3.connect("timers.db")
        self.cur = self.conn.cursor()
        self.cur.execute("CREATE TABLE IF NOT EXISTS active_timers (key TEXT PRIMARY KEY, uid INTEGER, cid INTEGER, mid INTEGER, et REAL)")
        
        # 起動時に古い不完全なデータをクリアします
        self.cur.execute("DROP TABLE IF EXISTS hamo_roles")
        self.cur.execute("CREATE TABLE IF NOT EXISTS hamo_roles (name TEXT PRIMARY KEY, sname TEXT, desc TEXT)")
        self.conn.commit()
    async def setup_hook(self):
        self.cur.execute("SELECT key FROM active_timers")
        for r in self.cur.fetchall(): self.add_view(TimerView(self, r))
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")
        self.loop.create_task(self.resume_timers())
        self.loop.create_task(download_hamo(self))
    async def resume_timers(self):
        await self.wait_until_ready()
        self.cur.execute("SELECT key, uid, cid, mid, et FROM active_timers")
        for r in self.cur.fetchall():
            key, uid, cid, mid, et = r
            rem = int(et - time.time())
            if rem <= 0:
                ch = self.get_channel(cid) or await self.fetch_channel(cid)
                if ch:
                    try:
                        msg = await ch.fetch_message(mid)
                        await msg.edit(content="**[Bot]**　このタイマーは終了しました。", view=None)
                        await ch.send(f"**[Bot]** <@{uid}> さん、ボット再起動中にタイマーが終了していました。")
                    except: pass
                self.cur.execute("DELETE FROM active_timers WHERE key = ?", (key,))
                self.conn.commit()
                continue
            self.timers[key] = True
            asyncio.create_task(countdown(self, key, rem, cid, mid, uid, True))

bot = MyBot()

@bot.event
async def on_ready():
    print(f'ログインに成功しました　BOT名: {bot.user}')

def format_t(s):
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"

def conv(t):
    return "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in t).lower() if t else ""

async def countdown(bot, key, rem, cid, mid, uid, is_res=False):
    ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
    msg = None
    if ch:
        try: msg = await ch.fetch_message(mid)
        except: pass
    while rem > 0:
        st = min(5, rem)
        await asyncio.sleep(st)
        if not bot.timers.get(key, True): break
        rem -= st
        if msg:
            try: await msg.edit(content=f"**[Bot]**　**{format_t(rem)}**のタイマーを実行中{ '（復元）' if is_res else '' }。終了すると、メンションします。")
            except discord.NotFound: break
            except: pass
    try:
        if bot.timers.get(key, True) and rem <= 0:
            if msg: await msg.edit(content="**[Bot]**　タイマーが終了しました。", view=None)
            if ch: await ch.send(f"**[Bot]**　<@{uid}> さん、タイマーが終了しました。")
        elif not bot.timers.get(key, True):
            if msg: await msg.edit(content="**[Bot]**　<@{uid}> さんのタイマーは**キャンセル**されました。", view=None)
    except: pass
    if key in bot.timers: del bot.timers[key]
    bot.cur.execute("DELETE FROM active_timers WHERE key = ?", (key,))
    bot.conn.commit()

@bot.tree.command(name="ping", description="Pong")
async def ping(i): await i.response.send_message('**[Bot]**　Pong!')

@bot.tree.command(name="timer", description="タイマーをセットし、終了したらメンションします")
@app_commands.describe(hours="時間", minutes="分", seconds="秒")
async def timer(i, hours: int = 0, minutes: int = 0, seconds: int = 0):
    tot = (hours * 3600) + (minutes * 60) + seconds
    if tot <= 0: return await i.response.send_message("**[Bot]**　タイマーは1秒からセットしてください。", ephemeral=True)
    
    # 応答切れバグを防ぐため、保留（defer）を入れます
    await i.response.defer()
    
    # 応答保留時は followup を使ってタイマーをスタートさせます
    msg = await i.followup.send(f"**[Bot]**　**{format_t(tot)}**のタイマーをスタートしました。終了すると、メンションします。")
    key = f"{i.user.id}_{msg.id}"
    bot.timers[key] = True
    bot.cur.execute("INSERT OR REPLACE INTO active_timers VALUES (?, ?, ?, ?, ?)", (key, i.user.id, i.channel.id, msg.id, time.time() + tot))
    bot.conn.commit()
    await msg.edit(view=TimerView(bot, key))
    asyncio.create_task(countdown(bot, key, tot, i.channel.id, msg.id, i.user.id))

@bot.tree.command(name="howrole", description="TOH-hamoの役職を調べます")
@app_commands.describe(role="役職名")
async def howrole(i, role: str):
    bot.cur.execute("SELECT desc FROM hamo_roles WHERE name = ?", (role,))
    row = bot.cur.fetchone()
    if not row: return await i.response.send_message(f"**[Bot]**　**「{role}」**　という役職はデータベースに見つかりませんでした。", ephemeral=True)
    embed = discord.Embed(title=f"役職を調べる: {role}", description=row[0], color=discord.Color.teal())
    embed.set_footer(text=f"Requested by {i.user.display_name}")
    await i.response.send_message(embed=embed, ephemeral=True)

@howrole.autocomplete("role")
async def role_auto(i, current: str):
    bot.cur.execute("SELECT name FROM hamo_roles WHERE sname LIKE ? LIMIT 25", (f"%{conv(current)}%",))
    return [app_commands.Choice(name=r[0], value=r[0]) for r in bot.cur.fetchall()]

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)