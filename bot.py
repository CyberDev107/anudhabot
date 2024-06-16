import os
import discord
from discord.ext import commands, tasks
import psycopg2
import pytz
import asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Connect to the PostgreSQL database
DATABASE_URL = os.getenv('DATABASE_URL')
connection = psycopg2.connect(DATABASE_URL)
cursor = connection.cursor()

# Create the leaderboard table if it doesn't exist
cursor.execute('''CREATE TABLE IF NOT EXISTS leaderboard
              (user_id BIGINT PRIMARY KEY, count INTEGER)''')
connection.commit()

# Dictionary to store the last time each user said "anudha"
last_anudha_time = {}
top_anudha_user = None
# Dictionary to store the full Names of the users
nicknames = {
    "641948208653795338": "Aslaan Waheed",
    "974243632888578048": "George Ou",
    "365733521102340096": "Roger Zhu",
    "727071988119765063": "An*dha Wjisehinge",
    # "411412560215146497": "test1 test2",
}
# Split the full names into first and last names
for user_id, nickname in nicknames.items():
    nicknames[user_id] = nickname.split()
# Custom help command
class CustomHelpCommand(commands.MinimalHelpCommand):
    def __init__(self):
        super().__init__()
        self.commands_heading = "Commands:"
        self.no_category = "General Commands"
        self.command_attrs["help"] = "Shows this message"

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Help", color=discord.Color.blue())
        embed.description = "Use `!help <command>` for more information on a command."

        for cog, commands in mapping.items():
            name = cog.qualified_name if cog else self.no_category
            filtered = await self.filter_commands(commands, sort=True)
            if filtered:
                value = "\n".join(f"`{self.context.clean_prefix}{c.name}`: {c.help or 'No description'}" for c in filtered)
                embed.add_field(name=name, value=value, inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command):
        embed = discord.Embed(title=f"Help with `{self.context.clean_prefix}{command.qualified_name}`", color=discord.Color.blue())
        embed.description = command.help or "No description"
        
        if command.aliases:
            embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
        
        if command.usage:
            embed.add_field(name="Usage", value=f"`{self.context.clean_prefix}{command.qualified_name} {command.usage}`", inline=False)

        channel = self.get_destination()
        await channel.send(embed=embed)

# Assign the custom help command to the bot
bot.help_command = CustomHelpCommand()


class LeaderboardView(discord.ui.View):
    def __init__(self, bot, rows, initial_time, user_per_page=4):
        super().__init__(timeout=None)
        self.bot = bot
        self.rows = rows
        self.initial_time = initial_time
        self.user_per_page = user_per_page
        self.current_page = 0
        self.max_pages = (len(self.rows) - 1) // self.user_per_page + 1

    async def format_leaderboard(self, page):
        start = page * self.user_per_page
        end = start + self.user_per_page
        leaderboard_str = ""
        for i, (user_id, count) in enumerate(self.rows[start:end], start=start + 1):
            user = await self.bot.fetch_user(user_id)
            leaderboard_str += f"{i}. **{user.name if user else 'Unknown User'}**: `{count} times`\n"
        return leaderboard_str

    async def update_leaderboard(self, interaction):
        await interaction.response.defer()  # Defer the response to allow more time
        embed = discord.Embed(
            title="Anudha Word Leaderboard!",
            description=await self.format_leaderboard(self.current_page),
            color=0x999999
        )
        # Use the initial time for the footer
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.max_pages} | Command sent at: {self.initial_time} ACST")
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_leaderboard(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            await self.update_leaderboard(interaction)

@bot.event
async def on_ready():
    # Set the bot's status to streaming
    streaming_activity = discord.Streaming(name="Alphapoint", url="https://www.twitch.tv/your_channel")
    await bot.change_presence(activity=streaming_activity)
    print(f'Logged in as {bot.user}')

    # Fetch the top anudha user
    fetch_top_anudha_user.start()

@tasks.loop(minutes=10)
async def fetch_top_anudha_user():
    global top_anudha_user
    cursor.execute('SELECT user_id FROM leaderboard ORDER BY count DESC LIMIT 1')
    result = cursor.fetchone()
    top_anudha_user = result[0] if result else None

@bot.event
async def on_message(message):
    if message.author == bot.user or isinstance(message.channel, discord.DMChannel):
        return

    current_time = datetime.utcnow()
    user_id = message.author.id

    # Check if the message contains the word "anudha" exactly once
    if message.content.lower().count('anudha') == 1:
        if user_id in last_anudha_time:
            last_time = last_anudha_time[user_id]
            if current_time - last_time < timedelta(seconds=10):
                await message.reply("You can only say 'anudha' once every 10 seconds.", delete_after=10)
                return

        last_anudha_time[user_id] = current_time

        cursor.execute('SELECT count FROM leaderboard WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()

        if result is None:
            cursor.execute('INSERT INTO leaderboard (user_id, count) VALUES (%s, 1)', (user_id,))
        else:
            count = result[0] + 1
            cursor.execute('UPDATE leaderboard SET count = %s WHERE user_id = %s', (count, user_id))
        
        connection.commit()
        await message.reply('🤨 📸 **You said Anudha, congrats!**', delete_after=10)
    # Nickname functionality, where the bot replies in the format "firstname '{message content}' lastname"
    if user_id in nicknames:
        first_name, last_name = nicknames[user_id]
        nickname_message = f'{first_name} "{message.content}" {last_name}'
        await message.reply(nickname_message, delete_after=10)
        
    # Process commands after handling the message
    await bot.process_commands(message)

@bot.command(help="Shows the Anudha Leaderboard.")
async def anudhaboard(ctx):
    cursor.execute('SELECT user_id, count FROM leaderboard ORDER BY count DESC')
    rows = cursor.fetchall()

    if not rows:
        await ctx.send('No one has said the word "anudha" yet!')
        return

    # Get the current time in ACST
    acst = pytz.timezone('Australia/Adelaide')
    current_time = datetime.now(acst).strftime('%Y-%m-%d %H:%M:%S')
    view = LeaderboardView(bot, rows, initial_time=current_time)
    embed = discord.Embed(
        title="Anudha Word Leaderboard!",
        description=await view.format_leaderboard(view.current_page),
        color=0x999999
    )
    embed.set_footer(text=f"Page {view.current_page + 1} of {view.max_pages} | Command sent at: {current_time} ACST")
    await ctx.send(embed=embed, view=view)

# Use the environment variable for the bot token
bot.run('DISCORD_KEY')
