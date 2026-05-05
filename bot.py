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
# ADMIN COMMANDS
# -------------------------

@bot.tree.command(name="add_balance", description="Admin: Add tokens to a user")
@app_commands.checks.has_permissions(administrator=True)
async def add_balance(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be positive.", ephemeral=True)
    
    balances[member.id] = get_bal(member.id) + amount
    await interaction.response.send_message(f"✅ Added `{amount}` tokens to {member.mention}. New balance: `{get_bal(member.id)}`")

@bot.tree.command(name="remove_balance", description="Admin: Remove tokens from a user")
@app_commands.checks.has_permissions(administrator=True)
async def remove_balance(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be positive.", ephemeral=True)
    
    current_bal = get_bal(member.id)
    # Ensure they don't go below 0
    new_bal = max(0, current_bal - amount)
    removed_actual = current_bal - new_bal
    
    balances[member.id] = new_bal
    await interaction.response.send_message(f"✅ Removed `{removed_actual}` tokens from {member.mention}. New balance: `{new_bal}`")

@bot.tree.command(name="resetbalance", description="Admin: Reset a user's balance to 0")
@app_commands.checks.has_permissions(administrator=True)
async def resetbalance(interaction: discord.Interaction, member: discord.Member):
    balances[member.id] = 0
    await interaction.response.send_message(f"🔄 Balance reset for {member.mention}. New balance: `0`")

# -------------------------
# USER COMMANDS
# -------------------------

@bot.tree.command(name="balance", description="Check balance")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    embed = discord.Embed(title="💳 Balance", color=discord.Color.blue())
    embed.add_field(name=target.display_name, value=f"`{get_bal(target.id)}` tokens")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Start a coinflip match")
async def coinflip(interaction: discord.Interaction, opponent: discord.Member, wager: int, rounds: int):
    if interaction.channel_id != ALLOWED_CHANNEL_ID:
        return await interaction.response.send_message(f"❌ Commands only allowed in <#{ALLOWED_CHANNEL_ID}>", ephemeral=True)

    if opponent == interaction.user or opponent.bot:
        return await interaction.response.send_message("You cannot challenge yourself or a bot.", ephemeral=True)

    if interaction.user.id in active_games or opponent.id in active_games:
        return await interaction.response.send_message("❌ One of you is already in a game.", ephemeral=True)

    if get_bal(interaction.user.id) < wager or get_bal(opponent.id) < wager:
        return await interaction.response.send_message("One of you does not have enough tokens.", ephemeral=True)

    active_games.add(interaction.user.id)
    active_games.add(opponent.id)

    view = AcceptView(opponent)
    embed = discord.Embed(title="🪙 Coinflip Challenge", color=discord.Color.gold())
    embed.description = f"{interaction.user.mention} challenged {opponent.mention}!\n💰 **Wager:** `{wager}`\n🏁 **First to:** `{rounds}`"
    
    await interaction.response.send_message(content=f"{opponent.mention}, you've been challenged!", embed=embed, view=view)
    msg = await interaction.original_response()

    await view.wait()

    if view.accepted is not True:
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        status = "declined" if view.accepted is False else "expired"
        return await msg.edit(content=f"❌ Challenge {status}.", embed=None, view=None)

    # --- ESCROW: Subtract wager immediately ---
    balances[interaction.user.id] -= wager
    balances[opponent.id] -= wager
    total_prize = wager * 2

    scores = {interaction.user: 0, opponent: 0}
    turn, other = interaction.user, opponent
    round_num = 1
    
    game_msg = await interaction.followup.send(content="Game starting...")

    while max(scores.values()) < rounds:
        game_embed = discord.Embed(title=f"Round {round_num}", color=discord.Color.purple())
        game_embed.add_field(name="Score", value=f"{interaction.user.name}: {scores[interaction.user]}\n{opponent.name}: {scores[opponent]}")
        
        turn_view = CoinflipTurnView(turn)
        await game_msg.edit(content=f"{turn.mention}, pick your side! (Prize: `{total_prize}`)", embed=game_embed, view=turn_view)
        
        await turn_view.wait()

        # --- REFUND: In case of AFK ---
        if turn_view.choice is None:
            balances[interaction.user.id] += wager
            balances[opponent.id] += wager
            active_games.remove(interaction.user.id)
            active_games.remove(opponent.id)
            return await game_msg.edit(content=f"⏰ {turn.mention} failed to respond. Wagers refunded.", embed=None, view=None)

        result = random.choice(["heads", "tails"])
        if turn_view.choice == result:
            scores[turn] += 1
            res_txt = f"✅ {turn.name} guessed right!"
        else:
            scores[other] += 1
            res_txt = f"❌ {turn.name} guessed wrong!"

        game_embed.add_field(name="Result", value=f"It was **{result}**\n{res_txt}", inline=False)
        await game_msg.edit(content=None, embed=game_embed, view=None)
        
        turn, other = other, turn
        round_num += 1
        await asyncio.sleep(2)

    # --- WINNER ---
    winner = max(scores, key=scores.get)
    loser = opponent if winner == interaction.user else interaction.user
    balances[winner.id] += total_prize

    final_embed = discord.Embed(title="🏆 Match Over", color=discord.Color.green())
    final_embed.description = f"🎉 {winner.mention} defeated {loser.mention} and won `{total_prize}` tokens!"
    final_embed.add_field(name="Final Score", value=f"{winner.name}: {scores[winner]}\n{loser.name}: {scores[loser]}")
    
    await game_msg.edit(content=f"Congratulations {winner.mention}!", embed=final_embed, view=None)
    
    active_games.remove(interaction.user.id)
    active_games.remove(opponent.id)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("TOKEN variable not found in Railway.")