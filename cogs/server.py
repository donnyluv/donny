from __future__ import annotations

import disnake
from disnake.ext import commands

from disnake.utils import utcnow


class Server(commands.Cog):
    """Предоставляет информацию о текущем Discord-сервере."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="server")
    async def server_info(self, ctx: commands.Context) -> None:
        """Отправляет эмбед с подробной информацией о сервере."""
        guild = ctx.guild

        if guild is None:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        total_members = guild.member_count or 0
        bot_members = sum(1 for member in guild.members if member.bot)
        human_members = total_members - bot_members

        voice_channels = len(guild.voice_channels)
        text_channels = len(guild.text_channels)
        total_channels = voice_channels + text_channels

        status_order = [
            (disnake.Status.online, "🟢", "➜ В сети"),
            (disnake.Status.idle, "🌙", "➜ Неактивны"),
            (disnake.Status.dnd, "⛔", "➜ Не беспокоить"),
            (disnake.Status.offline, "⚫", "➜ Не в сети"),
        ]

        status_counts = {
            label: sum(
                1
                for member in guild.members
                if not member.bot and member.status == status
            )
            for status, _, label in status_order
        }

        created_at = guild.created_at
        created_display = (
            created_at.strftime("%d.%m.%Y %H:%M") if created_at else "Неизвестно"
        )

        boost_count = guild.premium_subscription_count or 0
        emoji_count = len(guild.emojis)
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_owner()
            except disnake.DiscordException:
                owner = None
        owner_display = owner.mention if owner else "Неизвестно"

        embed = disnake.Embed(
            title="<:inform:1434448079834320926> Информация о сервере:",
            colour=disnake.Colour.blurple(),
        )

        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
        else:
            embed.set_author(name=guild.name)

        lines = [
            "> **<:everyone:1434448056035573760> Участники:**",
            f"<:alls:1434448070950785066> ➜ Всего: `{total_members}`",
            f"<:bots:1434448076487000196> ➜ Ботов: `{bot_members}`",
            f"<:peoples:1434448047039058072> ➜ Людей: `{human_members}`",
            "",
            "> **<:channels:1434448044576870470> Каналы:**",
            f"<:voices:1434448049773609034> ➜ Голосовые: `{voice_channels}`",
            f"<:messages:1434448053057749014> ➜ Текстовые: `{text_channels}`",
            f"<:alls:1434448070950785066> ➜ Всего: `{total_channels}`",
            "",
            "> **<:statusk:1434448033772343479> Статусы пользователей:**",
            *(
                f"{emoji} {label}: `{status_counts.get(label, 0)}`"
                for _, emoji, label in status_order
            ),
            "",
            "> **<:settings:1434448066274000917> Сервер:**",
            f"<:boosts:1434448041661694024> ➜ Бустов: `{boost_count}`",
            f"<:created:1434448038587273217> ➜ Сервер создан: {created_display}",
            f"<:emojiks:1434448036389589112> ➜ Всего эмодзи: `{emoji_count}`",
            f"<:ownerks:1434448068824268820> ➜ Владелец сервера: {owner_display}",
        ]

        embed.description = "\n".join(lines)

        requester = ctx.author
        request_moment = ctx.message.created_at or utcnow()
        now = utcnow()
        request_date = request_moment.date()
        now_date = now.date()

        if request_date == now_date:
            date_label = "Сегодня"
        elif (now_date - request_date).days == 1:
            date_label = "Вчера"
        else:
            date_label = request_moment.strftime("%d.%m.%Y")

        time_label = request_moment.strftime("%H:%M")
        footer_timestamp = f"{date_label} {time_label}"

        embed.set_footer(
            text=f"Запрос от {requester.name} • {footer_timestamp}",
            icon_url=requester.display_avatar.url,
        )

        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    """Регистрирует ког в экземпляре бота."""
    bot.add_cog(Server(bot))