from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, cast

import importlib.util
import sys
import types

import disnake
from disnake.ext import commands

from disnake.utils import utcnow

def _load_database_module() -> types.ModuleType:
    module_name = "database"
    existing = sys.modules.get(module_name)
    if isinstance(existing, types.ModuleType):
        return existing

    project_root = Path(__file__).resolve().parent.parent
    module_path = project_root / "database.py"

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(
            "Не удалось загрузить модуль базы данных по пути " f"{module_path}"
        )

    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    loader.exec_module(module)  # type: ignore[attr-defined]

    sys.modules[module_name] = module
    return module


_database_module = _load_database_module()
_get_system_embed_colour = _database_module.get_system_embed_colour

GetColourFn = Callable[[int], Optional[int]]

get_system_embed_colour: GetColourFn = cast(GetColourFn, _get_system_embed_colour)

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

        stored_colour_value = get_system_embed_colour(guild.id)

        embed_colour = disnake.Colour.blurple()
        if stored_colour_value is not None:
            try:
                embed_colour = disnake.Colour(value=stored_colour_value)
            except (TypeError, ValueError):
                embed_colour = disnake.Colour.blurple()

        embed = disnake.Embed(
            title="<:inform:1434448079834320926> Информация о сервере:",
            colour=embed_colour,
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