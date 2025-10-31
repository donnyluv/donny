from disnake.ext import commands


class Ping(commands.Cog):
    """Содержит команду для проверки задержки и доступности бота."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        """Отправляет сообщение с текущей задержкой бота."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(f"Понг! Текущая задержка: {latency_ms} мс")


def setup(bot: commands.Bot) -> None:
    """Регистрирует ког в экземпляре бота."""
    bot.add_cog(Ping(bot))