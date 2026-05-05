import discord
from discord import app_commands
import random
import asyncio
import os

# Configuration
ALLOWED_CHANNEL_ID = 1451222531271950447

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
# Fixed: Default balance is now 0 as requested
balances = {}
active_games = set()

def get_bal(user_id):
    return balances.get(user_id, 0)

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
    # This will now correctly show 0 if they have no tokens
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
# /coinflip
# -------------------------
@bot.tree.command(name="coinflip", description="Start a coinflip match")
async def coinflip(interaction: discord.Interaction, opponent: discord.Member, wager: int, rounds: int):
    # Check for correct channel
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>.", ephemeral=True)

    if opponent == interaction.user:
        return await interaction.response.send_message("You can't challenge yourself!", ephemeral=True)

    if interaction.user.id in active_games or opponent.id in active_games:
        return await interaction.response.send_message("❌ One of you is already in a game.", ephemeral=True)

    if get_bal(interaction.user.id) < wager or get_bal(opponent.id) < wager:
        return await interaction.response.send_message("One of you doesn't have enough tokens for this wager.", ephemeral=True)

    active_games.add(interaction.user.id)
    active_games.add(opponent.id)

    embed = discord.Embed(title="🪙 Coinflip Challenge", color=discord.Color.blue())
    embed.description = f"{interaction.user.mention} has challenged {opponent.mention}!"
    embed.add_field(name="💰 Wager", value=f"`{wager}` tokens")
    embed.add_field(name="🏁 First to", value=f"`{rounds}` wins")

    view = AcceptView(opponent)
    # Mention opponent here so they get a notification
    await interaction.response.send_message(content=f"Hey {opponent.mention}, you've been challenged!", embed=embed, view=view)
    msg = await interaction.original_response()

    await view.wait()

    if view.accepted is not True:
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        status_text = "❌ Challenge declined." if view.accepted is False else "⏰ This request expired."
        embed.color = discord.Color.red()
        embed.description = status_text
        return await msg.edit(content=None, embed=embed, view=None)

    # Game Loop Logic
    scores = {interaction.user: 0, opponent: 0}
    turn = interaction.user
    other = opponent
    round_num = 1

    game_embed = discord.Embed(title="🪙 Coinflip Match", color=discord.Color.purple())
    game_msg = await interaction.followup.send(content=f"The match begins! {turn.mention}, you're up first!")

    while scores[interaction.user] < rounds and scores[opponent] < rounds:
        game_embed.clear_fields()
        game_embed.description = f"**Round {round_num}**\n👉 Waiting for {turn.mention}..."
        game_embed.add_field(
            name="📊 Score",
            value=f"{interaction.user.display_name}: **{scores[interaction.user]}**\n"
                  f"{opponent.display_name}: **{scores[opponent]}**",
            inline=False
        )

        view = CoinflipTurnView(turn)
        await game_msg.edit(content=f"{turn.mention}, pick your side!", embed=game_embed, view=view)

        await view.wait()

        if view.choice is None:
            await game_msg.edit(content="⏰ Match cancelled due to inactivity.", embed=None, view=None)
            active_games.remove(interaction.user.id)
            active_games.remove(opponent.id)
            return

        result = random.choice(["heads", "tails"])

        if view.choice == result:
            scores[turn] += 1
            res_text = f"✅ {turn.display_name} guessed correctly! It was **{result}**."
        else:
            scores[other] += 1
            res_text = f"❌ {turn.display_name} guessed wrong! It was **{result}**."

        game_embed.add_field(name="🪙 Result", value=res_text, inline=False)
        await game_msg.edit(content=None, embed=game_embed, view=None)

        turn, other = other, turn
        round_num += 1
        await asyncio.sleep(2)

    # Final Results
    winner = interaction.user if scores[interaction.user] >= rounds else opponent
    loser = opponent if winner == interaction.user else interaction.user

    balances[winner.id] = get_bal(winner.id) + wager
    balances[loser.id] = get_bal(loser.id) - wager

    game_embed.clear_fields()
    game_embed.title = "🏆 Match Results"
    game_embed.color = discord.Color.gold()
    # Mention who won against whom
    game_embed.description = f"🎉 {winner.mention} has defeated {loser.mention}!"

    game_embed.add_field(
        name="📊 Final Score",
        value=f"{interaction.user.display_name}: {scores[interaction.user]}\n"
              f"{opponent.display_name}: {scores[opponent]}",
        inline=True
    )
    game_embed.add_field(name="💰 Prize Pool", value=f"`{wager}` tokens won!", inline=True)

    await game_msg.edit(content=f"Congratulations {winner.mention}!", embed=game_embed, view=None)

    active_games.remove(interaction.user.id)
    active_games.remove(opponent.id)

# -------------------------
# ERROR HANDLER
# -------------------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Admin permissions required.", ephemeral=True)
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    bot.run(TOKEN)