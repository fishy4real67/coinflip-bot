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
balances = {}
active_games = set()

def get_bal(user_id):
    return balances.get(user_id, 0)

# -------------------------
# UI COMPONENTS
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
# COMMANDS
# -------------------------

@bot.tree.command(name="balance", description="Check balance")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = discord.Embed(title="💳 Balance", color=discord.Color.blue())
    embed.add_field(name=target.display_name, value=f"`{get_bal(target.id)}` tokens")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="add_balance", description="Admin: Add tokens")
@app_commands.checks.has_permissions(administrator=True)
async def add_balance(interaction: discord.Interaction, member: discord.Member, amount: int):
    balances[member.id] = get_bal(member.id) + amount
    await interaction.response.send_message(f"✅ Added {amount} to {member.mention}. New balance: `{get_bal(member.id)}`")

@bot.tree.command(name="coinflip", description="Start a coinflip match")
async def coinflip(interaction: discord.Interaction, opponent: discord.Member, wager: int, rounds: int):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(f"❌ Use <#{ALLOWED_CHANNEL_ID}>", ephemeral=True)

    if opponent == interaction.user or opponent.bot:
        return await interaction.response.send_message("Invalid opponent.", ephemeral=True)

    if interaction.user.id in active_games or opponent.id in active_games:
        return await interaction.response.send_message("❌ Someone is already in a game.", ephemeral=True)

    if get_bal(interaction.user.id) < wager or get_bal(opponent.id) < wager:
        return await interaction.response.send_message("Insufficient funds.", ephemeral=True)

    active_games.add(interaction.user.id)
    active_games.add(opponent.id)

    view = AcceptView(opponent)
    embed = discord.Embed(title="🪙 Challenge Issued", description=f"{interaction.user.mention} vs {opponent.mention}\n**Wager:** {wager}\n**First to:** {rounds}", color=discord.Color.gold())
    
    await interaction.response.send_message(content=f"{opponent.mention}, you've been challenged!", embed=embed, view=view)
    msg = await interaction.original_response()

    await view.wait()

    if view.accepted is not True:
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        return await msg.edit(content="❌ Challenge cancelled or expired.", view=None)

    # --- ESCROW: Take money immediately ---
    balances[interaction.user.id] -= wager
    balances[opponent.id] -= wager
    total_prize = wager * 2

    scores = {interaction.user: 0, opponent: 0}
    turn, other = interaction.user, opponent
    round_num = 1
    
    game_embed = discord.Embed(title="🪙 Match in Progress", color=discord.Color.purple())
    game_msg = await interaction.followup.send(content=f"Game Started! Prize Pool: `{total_prize}`")

    while max(scores.values()) < rounds:
        game_embed.description = f"**Round {round_num}**\nWaiting for {turn.mention}..."
        game_embed.clear_fields()
        game_embed.add_field(name="Score", value=f"{interaction.user.name}: {scores[interaction.user]}\n{opponent.name}: {scores[opponent]}")
        
        turn_view = CoinflipTurnView(turn)
        await game_msg.edit(content=f"{turn.mention}, pick your side!", embed=game_embed, view=turn_view)
        
        await turn_view.wait()

        # --- REFUND LOGIC: If they don't pick a side ---
        if turn_view.choice is None:
            balances[interaction.user.id] += wager
            balances[opponent.id] += wager
            active_games.remove(interaction.user.id)
            active_games.remove(opponent.id)
            return await game_msg.edit(content=f"⏰ {turn.mention} went AFK. Wagers have been refunded.", embed=None, view=None)

        result = random.choice(["heads", "tails"])
        if turn_view.choice == result:
            scores[turn] += 1
            res_msg = f"✅ {turn.name} guessed right!"
        else:
            scores[other] += 1
            res_msg = f"❌ {turn.name} guessed wrong!"

        game_embed.add_field(name="Result", value=f"It was **{result}**. {res_msg}", inline=False)
        await game_msg.edit(content=None, embed=game_embed, view=None)
        
        turn, other = other, turn
        round_num += 1
        await asyncio.sleep(2)

    # --- FINAL WINNER ---
    winner = max(scores, key=scores.get)
    loser = opponent if winner == interaction.user else interaction.user
    
    # Give the prize pool to the winner
    balances[winner.id] += total_prize

    end_embed = discord.Embed(title="🏆 Match Over", color=discord.Color.green())
    end_embed.description = f"{winner.mention} defeated {loser.mention} and won `{total_prize}` tokens!"
    end_embed.add_field(name="Final Score", value=f"{winner.name}: {scores[winner]}\n{loser.name}: {scores[loser]}")
    
    await game_msg.edit(content=f"Winner: {winner.mention}!", embed=end_embed, view=None)
    
    active_games.remove(interaction.user.id)
    active_games.remove(opponent.id)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    bot.run(TOKEN)