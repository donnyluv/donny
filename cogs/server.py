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
            title="<:emoji_info:1434168193835995236> Информация о сервере:",
            colour=disnake.Colour.blurple(),
        )

        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
        else:
            embed.set_author(name=guild.name)

        lines = [
            "> **<:emoji_polz:1434144440510976110> Участники:**",
            f"<:emoji_doc:1434148705409437787> ➜ Всего: `{total_members}`",
            f"<:emoji_bot:1434148707586015304> ➜ Ботов: `{bot_members}`",
            f"<:emoji_people:1434144432881405995> ➜ Людей: `{human_members}`",
            "",
            "> **<:emoji_channel:1434144430188658844> Каналы:**",
            f"<:emoji_voice:1434144435075158057> ➜ Голосовые: `{voice_channels}`",
            f"<:emoji_message:1434144437772226692> ➜ Текстовые: `{text_channels}`",
            f"<:emoji_doc:1434148705409437787> ➜ Всего: `{total_channels}`",
            "",
            "> **<:emoji_status:1434144413369630890> Статусы пользователей:**",
            *(
                f"{emoji} {label}: `{status_counts.get(label, 0)}`"
                for _, emoji, label in status_order
            ),
            "",
            "> **<:emoji_settings:1434148710748655706> Сервер:**",
            f"<:emoji_boost:1434144427433005076> ➜ Бустов: `{boost_count}`",
            f"<:emoji_create:1434144424866091068> ➜ Сервер создан: {created_display}",
            f"<:emoji_emoji:1434144416431345705> ➜ Всего эмодзи: `{emoji_count}`",
            f"<:emoji_owner:1434148702758633563> ➜ Владелец сервера: {owner_display}",
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