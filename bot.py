import discord
from discord import app_commands
import random
import asyncio

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# -------------------------
# DATA
# -------------------------
balances = {}
active_games = set()

def get_bal(user_id):
    return balances.get(user_id, 1000)

# -------------------------
# UI: ACCEPT / DECLINE
# -------------------------
class AcceptView(discord.ui.View):
    def __init__(self, opponent):
        super().__init__(timeout=60)
        self.opponent = opponent
        self.accepted = None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("Not your challenge!", ephemeral=True)
        self.accepted = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("Not your challenge!", ephemeral=True)
        self.accepted = False
        self.stop()
        await interaction.response.send_message("❌ Challenge declined.")

# -------------------------
# UI: HEADS / TAILS
# -------------------------
class CoinflipTurnView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=60)
        self.player = player
        self.choice = None

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)
        self.choice = "heads"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.secondary)
    async def tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.player:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)
        self.choice = "tails"
        self.stop()
        await interaction.response.defer()

# -------------------------
# /balance
# -------------------------
@bot.tree.command(name="balance", description="Check balance")
@app_commands.describe(member="User (optional)")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = discord.Embed(title="💳 Balance", color=discord.Color.blue())
    embed.add_field(name=target.display_name, value=f"`{get_bal(target.id)}` tokens")
    await interaction.response.send_message(embed=embed)

# -------------------------
# /add_balance (ADMIN)
# -------------------------
@bot.tree.command(name="add_balance", description="Admin: Add tokens")
@app_commands.checks.has_permissions(administrator=True)
async def add_balance(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be positive.", ephemeral=True)

    balances[member.id] = get_bal(member.id) + amount

    embed = discord.Embed(title="✅ Balance Updated", color=discord.Color.green())
    embed.add_field(name="User", value=member.mention)
    embed.add_field(name="Added", value=f"`{amount}`")
    embed.add_field(name="New Balance", value=f"`{get_bal(member.id)}`")

    await interaction.response.send_message(embed=embed)

# -------------------------
# /resetbalance (ADMIN)
# -------------------------
@bot.tree.command(name="resetbalance", description="Admin: Reset balance")
@app_commands.checks.has_permissions(administrator=True)
async def resetbalance(interaction: discord.Interaction, member: discord.Member):
    balances[member.id] = 1000

    embed = discord.Embed(title="🔄 Balance Reset", color=discord.Color.orange())
    embed.add_field(name="User", value=member.mention)
    embed.add_field(name="New Balance", value="`1000`")

    await interaction.response.send_message(embed=embed)

# -------------------------
# /coinflip
# -------------------------
@bot.tree.command(name="coinflip", description="Start a coinflip match")
async def coinflip(interaction: discord.Interaction, opponent: discord.Member, wager: int, rounds: int):

    if opponent == interaction.user:
        return await interaction.response.send_message("You can't challenge yourself!", ephemeral=True)

    if interaction.user.id in active_games or opponent.id in active_games:
        return await interaction.response.send_message("❌ One of you is already in a game.", ephemeral=True)

    if get_bal(interaction.user.id) < wager or get_bal(opponent.id) < wager:
        return await interaction.response.send_message("Not enough balance.", ephemeral=True)

    active_games.add(interaction.user.id)
    active_games.add(opponent.id)

    embed = discord.Embed(title="🪙 Coinflip Challenge", color=discord.Color.blue())
    embed.description = f"{interaction.user.mention} vs {opponent.mention}"
    embed.add_field(name="💰 Wager", value=f"`{wager}` each")
    embed.add_field(name="🏁 First to", value=f"`{rounds}` wins")

    view = AcceptView(opponent)
    await interaction.response.send_message(
    content="something",
    embed=embed,
    view=view
)
    msg = await interaction.original_response()

    await view.wait()

    if view.accepted is None:
        embed.color = discord.Color.red()
        embed.description = "⏰ This request expired."
        await msg.edit(embed=embed, view=None)
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        return

    if view.accepted is False:
        embed.color = discord.Color.red()
        embed.description = "❌ Challenge declined."
        await msg.edit(embed=embed, view=None)
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        return

    scores = {interaction.user: 0, opponent: 0}
    turn = interaction.user
    other = opponent
    round_num = 1

    game_embed = discord.Embed(title="🪙 Coinflip Match", color=discord.Color.purple())
    game_msg = await interaction.followup.send(embed=game_embed)

    while scores[interaction.user] < rounds and scores[opponent] < rounds:

        game_embed.clear_fields()
        game_embed.description = f"**Round {round_num}**\n👉 {turn.mention}'s turn"

        game_embed.add_field(
            name="📊 Score",
            value=f"{interaction.user.display_name}: **{scores[interaction.user]}**\n"
                  f"{opponent.display_name}: **{scores[opponent]}**",
            inline=False
        )

        view = CoinflipTurnView(turn)
        await game_msg.edit(embed=game_embed, view=view)

        await view.wait()

        if view.choice is None:
            await game_msg.edit(content="⏰ Match cancelled.", embed=None, view=None)
            active_games.remove(interaction.user.id)
            active_games.remove(opponent.id)
            return

        result = random.choice(["heads", "tails"])

        if view.choice == result:
            scores[turn] += 1
            text = f"✅ {turn.display_name} guessed correctly ({result})"
        else:
            scores[other] += 1
            text = f"❌ {turn.display_name} guessed wrong ({result})"

        game_embed.add_field(name="🪙 Result", value=text, inline=False)
        await game_msg.edit(embed=game_embed, view=None)

        turn, other = other, turn
        round_num += 1
        await asyncio.sleep(1.5)

    winner = interaction.user if scores[interaction.user] >= rounds else opponent
    loser = opponent if winner == interaction.user else interaction.user

    balances[winner.id] += wager
    balances[loser.id] -= wager

    game_embed.clear_fields()
    game_embed.title = "🏆 Match Over"
    game_embed.color = discord.Color.green()
    game_embed.description = f"Winner: {winner.mention}"

    game_embed.add_field(
        name="📊 Final Score",
        value=f"{interaction.user.display_name}: {scores[interaction.user]}\n"
              f"{opponent.display_name}: {scores[opponent]}",
        inline=False
    )

    game_embed.add_field(name="💰 Winnings", value=f"`{wager}` tokens", inline=False)

    await game_msg.edit(embed=game_embed, view=None)

    active_games.remove(interaction.user.id)
    active_games.remove(opponent.id)

# -------------------------
# ERROR HANDLER
# -------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ You must be an administrator to use this command.",
            ephemeral=True
        )

# -------------------------
# RUN BOT (TOKEN AT END)
# -------------------------
if __name__ == "__main__":
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    bot.run('TOKEN')