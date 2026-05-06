import discord
from discord import app_commands
import random
import asyncio
import os

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
active_games = set()

# -------------------------
# UI COMPONENTS
# -------------------------
class AcceptView(discord.ui.View):
    def __init__(self, opponent):
        super().__init__(timeout=60)
        self.opponent = opponent
        self.accepted = None

    @discord.ui.button(label="Accept Challenge", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("This isn't your challenge!", ephemeral=True)
        self.accepted = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.opponent:
            return await interaction.response.send_message("This isn't your challenge!", ephemeral=True)
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
# COMMAND
# -------------------------
@bot.tree.command(name="coinflip", description="Start an item-based coinflip match")
@app_commands.describe(
    opponent="The user you want to challenge",
    your_items="The items you are wagering",
    opponent_items="The items you want the opponent to wager",
    rounds="Number of wins needed to end the match"
)
async def coinflip(
    interaction: discord.Interaction,
    opponent: discord.Member,
    your_items: str,
    opponent_items: str,
    rounds: int
):
    if opponent == interaction.user or opponent.bot:
        return await interaction.response.send_message("You cannot challenge yourself or a bot.", ephemeral=True)

    if interaction.user.id in active_games or opponent.id in active_games:
        return await interaction.response.send_message("❌ One of you is already in an active game.", ephemeral=True)

    if rounds < 1 or rounds > 10:
        return await interaction.response.send_message("Rounds must be between 1 and 10.", ephemeral=True)

    active_games.add(interaction.user.id)
    active_games.add(opponent.id)

    # Challenge
    view = AcceptView(opponent)
    embed = discord.Embed(title="🪙 Item Coinflip Challenge", color=discord.Color.gold())
    embed.add_field(name="Challenger", value=f"{interaction.user.mention}\n**Betting:** {your_items}", inline=False)
    embed.add_field(name="Opponent", value=f"{opponent.mention}\n**Betting:** {opponent_items}", inline=False)
    embed.add_field(name="Rules", value=f"First to `{rounds}` wins.", inline=False)

    await interaction.response.send_message(
        content=f"{opponent.mention}, you've been challenged by {interaction.user.mention}!",
        embed=embed,
        view=view
    )

    msg = await interaction.original_response()
    await view.wait()

    if view.accepted is not True:
        active_games.remove(interaction.user.id)
        active_games.remove(opponent.id)
        status = "declined" if view.accepted is False else "expired"
        return await msg.edit(content=f"❌ Challenge {status}.", embed=None, view=None)

    # Game Start
    scores = {interaction.user: 0, opponent: 0}
    turn, other = interaction.user, opponent
    round_num = 1

    await interaction.followup.send("🎮 Match starting! Items are locked in.")

    while max(scores.values()) < rounds:

        round_embed = discord.Embed(title=f"🪙 Round {round_num}", color=discord.Color.purple())
        round_embed.add_field(
            name="📊 Score",
            value=f"{interaction.user.name}: **{scores[interaction.user]}**\n{opponent.name}: **{scores[opponent]}**",
            inline=False
        )
        round_embed.add_field(
            name="🎁 Stakes",
            value=f"{your_items} **AND** {opponent_items}",
            inline=False
        )
        round_embed.set_footer(text=f"{turn.name}'s turn")

        turn_view = CoinflipTurnView(turn)

        round_msg = await interaction.followup.send(
            content=f"{turn.mention}, choose heads or tails!",
            embed=round_embed,
            view=turn_view
        )

        await turn_view.wait()

        if turn_view.choice is None:
            active_games.remove(interaction.user.id)
            active_games.remove(opponent.id)
            return await round_msg.edit(
                content=f"⏰ {turn.mention} didn't respond. Match cancelled.",
                embed=None,
                view=None
            )

        result = random.choice(["heads", "tails"])

        if turn_view.choice == result:
            scores[turn] += 1
            result_text = f"✅ {turn.name} guessed correctly!"
        else:
            scores[other] += 1
            result_text = f"❌ {turn.name} guessed wrong!"

        result_embed = discord.Embed(title=f"🎲 Result - Round {round_num}", color=discord.Color.blue())
        result_embed.add_field(name="Coin Result", value=f"🪙 Landed on **{result}**", inline=False)
        result_embed.add_field(name="Outcome", value=result_text, inline=False)

        await interaction.followup.send(embed=result_embed)

        turn, other = other, turn
        round_num += 1
        await asyncio.sleep(2)

    # Final Result
    winner = max(scores, key=scores.get)
    loser = opponent if winner == interaction.user else interaction.user

    final_embed = discord.Embed(title="🏆 Match Completed", color=discord.Color.green())
    final_embed.description = f"{winner.mention} wins against {loser.mention}!"
    final_embed.add_field(name="🎁 Items Won", value=f"{your_items}, {opponent_items}", inline=False)
    final_embed.add_field(
        name="📊 Final Score",
        value=f"{interaction.user.name}: {scores[interaction.user]}\n{opponent.name}: {scores[opponent]}",
        inline=False
    )

    await interaction.followup.send(embed=final_embed)

    active_games.remove(interaction.user.id)
    active_games.remove(opponent.id)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    bot.run(TOKEN)