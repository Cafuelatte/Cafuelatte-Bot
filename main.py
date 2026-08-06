import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'ログイン成功！BOT名: {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
bot.run(TOKEN)
