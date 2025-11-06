from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import importlib.util
from pathlib import Path
import re
import sys
import types
import contextlib

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
create_idea = _database_module.create_idea
store_idea_message = _database_module.store_idea_message
update_idea_status = _database_module.update_idea_status
delete_idea = _database_module.delete_idea
get_idea = _database_module.get_idea
list_user_ideas = _database_module.list_user_ideas
list_server_ideas = _database_module.list_server_ideas
count_user_ideas = _database_module.count_user_ideas
count_server_ideas = _database_module.count_server_ideas
get_user_idea_stats = _database_module.get_user_idea_stats
get_server_idea_stats = _database_module.get_server_idea_stats
get_idea_rating_summary = _database_module.get_idea_rating_summary
set_idea_rating = _database_module.set_idea_rating
remove_idea_rating = _database_module.remove_idea_rating
get_user_rating_for_idea = _database_module.get_user_rating_for_idea
get_idea_channel = _database_module.get_idea_channel
get_idea_admin_roles = _database_module.get_idea_admin_roles
get_system_embed_colour = _database_module.get_system_embed_colour
list_pending_idea_messages = _database_module.list_pending_idea_messages


class IdeaStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    @property
    def label(self) -> str:
        if self is IdeaStatus.APPROVED:
            return "Одобрено"
        if self is IdeaStatus.REJECTED:
            return "Отклонено"
        return "На рассмотрении"


@dataclass
class IdeaRecord:
    id: int
    guild_id: int
    author_id: int
    content: str
    status: IdeaStatus
    created_at: datetime
    updated_at: datetime
    channel_id: Optional[int]
    message_id: Optional[int]
    thread_id: Optional[int]
    admin_id: Optional[int]
    rejection_reason: Optional[str]
    average_rating: Optional[float] = None
    ratings_count: int = 0

    @classmethod
    def from_row(cls, row: Dict[str, object]) -> "IdeaRecord":
        def parse_datetime(value: object) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    pass
            return datetime.utcnow()

        status_value = row.get("status", IdeaStatus.PENDING.value)
        try:
            status = IdeaStatus(str(status_value)) if status_value else IdeaStatus.PENDING
        except ValueError:
            status = IdeaStatus.PENDING
        created = parse_datetime(row.get("created_at"))
        updated = parse_datetime(row.get("updated_at"))

        return cls(
            id=int(row.get("id", 0)),
            guild_id=int(row.get("guild_id", 0)),
            author_id=int(row.get("author_id", 0)),
            content=str(row.get("content", "")),
            status=status,
            created_at=created,
            updated_at=updated,
            channel_id=(int(row["channel_id"]) if row.get("channel_id") is not None else None),
            message_id=(int(row["message_id"]) if row.get("message_id") is not None else None),
            thread_id=(int(row["thread_id"]) if row.get("thread_id") is not None else None),
            admin_id=(int(row["admin_id"]) if row.get("admin_id") is not None else None),
            rejection_reason=(
                str(row.get("rejection_reason")) if row.get("rejection_reason") is not None else None
            ),
        )


class Idea(commands.Cog):
    """Управление пользовательскими предложениями."""

    ideas_per_page = 15

    BUTTON_APPEARANCE: Dict[
        str,
        Dict[str, Optional[str | disnake.PartialEmoji]]
        | str
        | disnake.PartialEmoji
        | None,
    ] = {
        "back": {"label": "Назад", "emoji": None},
        "previous": {"label": None, "emoji": "<:pred:1434251697022173284>"},
        "next": {"label": None, "emoji": "<:next:1434250501863772170>"},
        "edit": {"label": None, "emoji": "<:created:1434448038587273217>"},
        "create": {"label": None, "emoji": "<:odobreno:1434909104794501243>"},
    }

    _CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:[A-Za-z0-9_~]+:[0-9]{15,22}>$")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.loop.create_task(self._restore_persistent_views())

    async def _restore_persistent_views(self) -> None:
        await self.bot.wait_until_ready()
        pending_rows = list_pending_idea_messages()
        for row in pending_rows:
            idea = IdeaRecord.from_row(row)
            if idea.message_id is None or idea.channel_id is None:
                continue

            guild = self.bot.get_guild(idea.guild_id)
            if guild is None:
                continue

            with contextlib.suppress(Exception):
                await self.update_idea_message(idea.id, guild)

    def get_button_appearance(
        self,
        button_key: str,
        *,
        default_label: Optional[str] = None,
        default_emoji: Optional[disnake.PartialEmoji | str] = None,
    ) -> Tuple[Optional[str], Optional[disnake.PartialEmoji | str]]:
        config = self.BUTTON_APPEARANCE.get(button_key)

        label: Optional[str] = default_label
        emoji: Optional[disnake.PartialEmoji | str] = default_emoji
        emoji_value: Optional[disnake.PartialEmoji | str] = None

        if isinstance(config, dict):
            if "label" in config:
                label = config.get("label")
            if "emoji" in config:
                emoji_value = config.get("emoji")
        elif isinstance(config, (str, disnake.PartialEmoji)):
            label = str(config)
        elif config is None:
            pass
        else:
            label = str(config)

        if emoji_value is not None:
            try:
                emoji = disnake.PartialEmoji.from_str(str(emoji_value))
            except Exception:
                emoji = emoji_value

        if isinstance(label, str):
            stripped_label = label.strip()
            if not stripped_label:
                label = None
            elif emoji is None and self._CUSTOM_EMOJI_PATTERN.fullmatch(stripped_label):
                try:
                    emoji = disnake.PartialEmoji.from_str(stripped_label)
                    label = None
                except Exception:
                    label = stripped_label
            else:
                label = stripped_label

        if label is None and emoji is None:
            label = default_label
            emoji = default_emoji

        return label, emoji

    @commands.command(name="idea")
    async def idea_command(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            embed = self.build_system_message_embed(
                "Эту команду можно использовать только на сервере.",
                title="Ошибка",
            )
            await ctx.send(embed=embed)
            return

        embed = self.build_summary_embed(guild, ctx.author)
        view = IdeaMenuView(self, ctx.author, guild)
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    # ------------------------------------------------------------------
    # Embed builders

    def _resolve_colour(self, guild: Optional[disnake.Guild]) -> disnake.Colour:
        if guild is None:
            return disnake.Colour.blurple()
        stored = get_system_embed_colour(guild.id)
        if stored is None:
            return disnake.Colour.blurple()
        try:
            return disnake.Colour(value=int(stored))
        except (TypeError, ValueError):
            return disnake.Colour.blurple()

    def build_system_message_embed(
        self,
        message: str,
        *,
        guild: Optional[disnake.Guild] = None,
        title: str = "Системное сообщение",
        emoji: Optional[str] = None,
    ) -> disnake.Embed:
        description = message.strip()
        if not description:
            description = "\u200b"
        if emoji:
            description = f"{emoji} {description}"
        embed = disnake.Embed(description=description, colour=self._resolve_colour(guild))
        if title:
            embed.title = title
        return embed

    def build_summary_embed(self, guild: disnake.Guild, user: disnake.abc.User) -> disnake.Embed:
        stats = get_user_idea_stats(guild.id, user.id)
        total = int(stats.get("total", 0) or 0)
        approved = int(stats.get("approved", 0) or 0)
        rejected = int(stats.get("rejected", 0) or 0)
        average_rating = stats.get("average_rating")
        if average_rating is not None:
            average_display = f"{average_rating:.2f}"
        else:
            average_display = "Нет оценок"

        description_lines = [
            "> **<:ideas:1434916461951975526> Ваши идеи:**",
            f"<:alls:1434448070950785066> ➜ Всего: `{total}`",
            f"<:odobreno:1434909104794501243> ➜ Одобрено: `{approved}`",
            f"<:otkaz:1434909101242060902> ➜ Отклонено: `{rejected}`",
            f"⭐ ➜ Средняя оценка: `{average_display}`",
            "",
            "*Воспользуйтесь выпадающим меню выбора ниже для создания новой идеи или просмотра своих уже существующих идей.*",
        ]

        embed = disnake.Embed(
            title="<:created:1434448038587273217> Предложения по серверу",
            description="\n".join(description_lines),
            colour=self._resolve_colour(guild),
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        return embed

    def build_view_placeholder_embed(
        self, guild: disnake.Guild, user: disnake.abc.User, *, page: int
    ) -> disnake.Embed:
        description = [
            "*Выберите предложение из выпадающего меню выбора для просмотра подробностей.*",
        ]
        embed = disnake.Embed(
            title="<:created:1434448038587273217> Предложения по серверу",
            description="\n".join(description),
            colour=self._resolve_colour(guild),
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        return embed

    def build_propose_embed(
        self, guild: disnake.Guild, user: disnake.abc.User, *, content: str | None
    ) -> disnake.Embed:
        proposal_text = (content or "").strip()
        description_lines: List[str] = []
        if proposal_text:
            description_lines.append(proposal_text)
        else:
            description_lines.append("\u200b")
        description_lines.extend(["", "*Для взаимодействия воспользуйтесь кнопками ниже.*"])
        embed = disnake.Embed(
            title="<:created:1434448038587273217> Ваше предложение:",
            description="\n".join(description_lines),
            colour=self._resolve_colour(guild),
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        return embed

    def build_server_summary_embed(
        self, guild: disnake.Guild, *, page: int
    ) -> disnake.Embed:
        stats = self.get_server_summary_stats(guild.id)
        total = stats.get("total", 0)
        approved = stats.get("approved", 0)
        rejected = stats.get("rejected", 0)
        pending = stats.get("pending", 0)

        description_lines = [
            "> Предложено:",
            f"<:alls:1434448070950785066> ➜ Всего: `{total}`",
            f"<:odobreno:1434909104794501243> ➜ Одобрено: `{approved}`",
            f"<:otkaz:1434909101242060902> ➜ Отклонено: `{rejected}`",
            f"<:timers:1434911932397129828> ➜ На рассмотрении: `{pending}`",
            "",
            "*Воспользуйтесь выпадающим меню выбора ниже для просмотра предложений сервера.*",
        ]

        embed = disnake.Embed(
            title="<:created:1434448038587273217> Предложения сервера",
            description="\n".join(description_lines),
            colour=self._resolve_colour(guild),
        )

        icon_url: Optional[str] = None
        if guild.icon:
            icon_url = guild.icon.url
        else:
            bot_member = guild.me
            if bot_member is not None:
                icon_url = bot_member.display_avatar.url

        if icon_url:
            embed.set_author(name=guild.name, icon_url=icon_url)
        else:
            embed.set_author(name=guild.name)

        return embed

    def build_idea_detail_embed(
        self,
        guild: disnake.Guild,
        viewer: disnake.abc.User,
        idea: IdeaRecord,
        *,
        include_author: bool = False,
    ) -> disnake.Embed:
        embed = disnake.Embed(
            title=f"<:ideas:1434916461951975526> Предложение №{idea.id}",
            colour=self._resolve_colour(guild),
        )
        author = guild.get_member(idea.author_id)
        author_name = author.display_name if author else f"ID {idea.author_id}"
        author_icon = author.display_avatar.url if author else viewer.display_avatar.url
        embed.set_author(name=author_name, icon_url=author_icon)

        average = idea.average_rating
        if average is not None:
            average_display = f"{average:.2f}"
        else:
            average_display = "Нет оценок"

        description_lines: List[str] = [idea.content or ""]
        info_lines = ["", "> **<:inform:1434448079834320926> Информация:**"]
        if include_author:
            info_lines.append(f"<:autoridea:1434913638329749595> ➜ Автор идеи: <@{idea.author_id}>")
        info_lines.extend(
            [
                f"⭐ ➜ Оценка: `{average_display}`",
                f"⭐ ➜ Количество оценок: `{idea.ratings_count}`",
                f"<:statusk:1434448033772343479> ➜ Статус: `{idea.status.label}`",
            ]
        )

        if idea.status is IdeaStatus.APPROVED or idea.status is IdeaStatus.REJECTED:
            if idea.admin_id:
                info_lines.append(f"<:administrator:1434913080344707122> ➜ Администратор: <@{idea.admin_id}>")
            if idea.status is IdeaStatus.REJECTED and idea.rejection_reason:
                info_lines.append(f"<:oprosik:1434913975228956762> ➜ Причина: `{idea.rejection_reason}`")

        embed.description = "\n".join(description_lines + info_lines).strip()
        return embed

    def build_idea_message_embed(self, guild: disnake.Guild, idea: IdeaRecord) -> disnake.Embed:
        average = idea.average_rating
        average_display = f"{average:.2f}" if average is not None else "Нет оценок"
        embed = disnake.Embed(
            title=f"<:ideas:1434916461951975526> Предложение №{idea.id}",
            colour=self._resolve_colour(guild),
        )
        author = guild.get_member(idea.author_id)
        if author:
            embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        else:
            embed.set_author(name=f"<:autoridea:1434913638329749595> ➜ Пользователь {idea.author_id}")

        lines = [idea.content or "", "", f"⭐ ➜ Средняя оценка: `{average_display}`"]
        lines.append(f"⭐ ➜ Количество оценок: `{idea.ratings_count}`")
        lines.append(f"<:statusk:1434448033772343479> ➜ Статус: `{idea.status.label}`")
        if idea.status is IdeaStatus.APPROVED or idea.status is IdeaStatus.REJECTED:
            if idea.admin_id:
                lines.append(f"<:administrator:1434913080344707122> ➜ Администратор: <@{idea.admin_id}>")
        if idea.status is IdeaStatus.REJECTED and idea.rejection_reason:
            lines.append(f"<:oprosik:1434913975228956762> ➜ Причина: `{idea.rejection_reason}`")
        embed.description = "\n".join(lines).strip()

        created_display = idea.created_at.strftime("%d.%m.%Y %H:%M")
        embed.set_footer(text=f"{created_display}")
        return embed

    # ------------------------------------------------------------------
    # Data helpers

    def fetch_user_ideas(self, guild_id: int, user_id: int, *, page: int) -> List[IdeaRecord]:
        offset = page * self.ideas_per_page
        rows = list_user_ideas(guild_id, user_id, limit=self.ideas_per_page, offset=offset)
        ideas: List[IdeaRecord] = []
        for row in rows:
            record = IdeaRecord.from_row(row)
            average, count = get_idea_rating_summary(record.id)
            record.average_rating = average
            record.ratings_count = count
            ideas.append(record)
        return ideas

    def get_user_idea_count(self, guild_id: int, user_id: int) -> int:
        return count_user_ideas(guild_id, user_id)

    def fetch_server_ideas(self, guild_id: int, *, page: int) -> List[IdeaRecord]:
        offset = page * self.ideas_per_page
        rows = list_server_ideas(guild_id, limit=self.ideas_per_page, offset=offset)
        ideas: List[IdeaRecord] = []
        for row in rows:
            record = IdeaRecord.from_row(row)
            average, count = get_idea_rating_summary(record.id)
            record.average_rating = average
            record.ratings_count = count
            ideas.append(record)
        return ideas

    def get_server_idea_count(self, guild_id: int) -> int:
        return count_server_ideas(guild_id)

    def get_server_summary_stats(self, guild_id: int) -> Dict[str, int]:
        return get_server_idea_stats(guild_id)

    def fetch_idea(self, idea_id: int) -> Optional[IdeaRecord]:
        row = get_idea(idea_id)
        if not row:
            return None
        record = IdeaRecord.from_row(row)
        average, count = get_idea_rating_summary(record.id)
        record.average_rating = average
        record.ratings_count = count
        return record

    def format_rating_label(self, rating: int) -> str:
        mapping = {
            1: "1 ⭐",
            2: "2 ⭐",
            3: "3 ⭐",
            4: "4 ⭐",
            5: "5 ⭐",
        }
        return mapping.get(rating, f"{rating} ⭐")

    def is_idea_admin(self, member: disnake.Member) -> bool:
        if member.guild_permissions.administrator:
            return True

        configured_roles = get_idea_admin_roles(member.guild.id)
        if not configured_roles:
            return member.guild_permissions.manage_guild

        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids.intersection(configured_roles))

    async def ensure_idea_channel(self, guild: disnake.Guild) -> Optional[disnake.TextChannel]:
        channel_id = get_idea_channel(guild.id)
        if channel_id is None:
            return None
        channel = guild.get_channel(channel_id)
        if isinstance(channel, disnake.TextChannel):
            return channel
        return None

    async def post_idea_message(self, idea: IdeaRecord, guild: disnake.Guild) -> Optional[disnake.Message]:
        channel = await self.ensure_idea_channel(guild)
        if channel is None:
            return None

        embed = self.build_idea_message_embed(guild, idea)
        view = IdeaMessageView(self, idea)
        message = await channel.send(embed=embed, view=view)
        with contextlib.suppress(Exception):
            self.bot.add_view(view, message_id=message.id)

        thread = None
        try:
            thread = await message.create_thread(
                name=f"Обсуждение предложения №{idea.id}",
                auto_archive_duration=10080,
            )
        except disnake.HTTPException:
            thread = None

        store_idea_message(
            idea.id,
            channel_id=channel.id,
            message_id=message.id,
            thread_id=thread.id if thread else None,
        )
        return message

    async def update_idea_message(self, idea_id: int, guild: disnake.Guild) -> None:
        idea = self.fetch_idea(idea_id)
        if idea is None:
            return

        channel_id = idea.channel_id
        message_id = idea.message_id
        if channel_id is None or message_id is None:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, disnake.TextChannel):
            return

        try:
            message = await channel.fetch_message(message_id)
        except disnake.DiscordException:
            return

        embed = self.build_idea_message_embed(guild, idea)
        view = IdeaMessageView(self, idea)
        try:
            await message.edit(embed=embed, view=view)
            with contextlib.suppress(Exception):
                self.bot.add_view(view, message_id=message.id)
        except disnake.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Idea mutations

    async def create_user_idea(
        self,
        guild: disnake.Guild,
        user: disnake.Member,
        content: str,
    ) -> Optional[IdeaRecord]:
        idea_id = create_idea(guild.id, user.id, content, created_at=utcnow().replace(tzinfo=None))
        record = self.fetch_idea(idea_id)
        if record is None:
            return None

        await self.post_idea_message(record, guild)
        return record

    async def approve_idea(
        self,
        idea: IdeaRecord,
        guild: disnake.Guild,
        admin: disnake.Member,
    ) -> None:
        update_idea_status(
            idea.id,
            status=IdeaStatus.APPROVED.value,
            admin_id=admin.id,
            rejection_reason=None,
            updated_at=utcnow().replace(tzinfo=None),
        )
        await self.update_idea_message(idea.id, guild)

    async def reject_idea(
        self,
        idea: IdeaRecord,
        guild: disnake.Guild,
        admin: disnake.Member,
        reason: str,
    ) -> None:
        update_idea_status(
            idea.id,
            status=IdeaStatus.REJECTED.value,
            admin_id=admin.id,
            rejection_reason=reason,
            updated_at=utcnow().replace(tzinfo=None),
        )
        await self.update_idea_message(idea.id, guild)

    async def delete_idea_entry(self, idea: IdeaRecord, guild: disnake.Guild) -> None:
        channel_id = idea.channel_id
        message_id = idea.message_id
        thread_id = idea.thread_id

        delete_idea(idea.id)

        if channel_id and message_id:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, disnake.TextChannel):
                try:
                    message = await channel.fetch_message(message_id)
                except disnake.DiscordException:
                    message = None
                if message is not None:
                    with contextlib.suppress(disnake.HTTPException):
                        await message.delete()

        if thread_id:
            thread = guild.get_thread(thread_id)
            if thread:
                with contextlib.suppress(disnake.HTTPException):
                    await thread.delete()


class IdeaViewMode(Enum):
    SUMMARY = "summary"
    VIEW = "view"
    PROPOSE = "propose"
    ALL = "all"


class IdeaMenuView(disnake.ui.View):
    def __init__(self, cog: Idea, author: disnake.Member, guild: disnake.Guild) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.mode = IdeaViewMode.SUMMARY
        self.page = 0
        self.idea_text: str = ""
        self.selected_idea_id: Optional[int] = None
        self.message: Optional[disnake.Message] = None
        self._current_ideas: List[IdeaRecord] = []
        self.refresh_components()

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "Только автор команды может взаимодействовать с этим меню.",
                    title="Доступ запрещен",
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, (disnake.ui.Button, disnake.ui.Select)):
                child.disabled = True
        if self.message is not None:
            with contextlib.suppress(disnake.HTTPException):
                await self.message.edit(view=self)

    # ------------------------------------------------------------------
    # State helpers

    def _system_embed(self, message: str, *, title: str = "Системное сообщение") -> disnake.Embed:
        return self.cog.build_system_message_embed(
            message,
            guild=self.guild,
            title=title,
        )

    def _button_custom_id(self, key: str) -> str:
        return f"idea_menu:{self.author.id}:{key}"

    def total_items(self) -> int:
        if self.mode is IdeaViewMode.VIEW:
            return self.cog.get_user_idea_count(self.guild.id, self.author.id)
        if self.mode is IdeaViewMode.ALL:
            return self.cog.get_server_idea_count(self.guild.id)
        return 0

    def total_pages(self) -> int:
        total = self.total_items()
        if total <= 0:
            return 1
        return (total - 1) // self.cog.ideas_per_page + 1

    def ensure_valid_page(self) -> None:
        total_pages = self.total_pages()
        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)
        if self.page < 0:
            self.page = 0

    def refresh_components(self) -> None:
        self.ensure_valid_page()
        if self.mode is IdeaViewMode.VIEW:
            self._current_ideas = self.cog.fetch_user_ideas(
                self.guild.id, self.author.id, page=self.page
            )
        elif self.mode is IdeaViewMode.ALL:
            self._current_ideas = self.cog.fetch_server_ideas(
                self.guild.id, page=self.page
            )
        else:
            self._current_ideas = []
        self.clear_items()

        self.primary_select = IdeaPrimarySelect(self)
        self.add_item(self.primary_select)

        self.secondary_select = IdeaListSelect(self)
        self.add_item(self.secondary_select)

        for button in self._build_navigation_buttons():
            self.add_item(button)

        for button in self._build_proposal_buttons():
            self.add_item(button)

    def _build_navigation_buttons(self) -> List[disnake.ui.Button]:
        buttons: List[disnake.ui.Button] = []

        back_label, back_emoji = self.cog.get_button_appearance(
            "back", default_label="Назад"
        )
        back_button = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            row=2,
            custom_id=self._button_custom_id("back"),
        )
        if back_label is not None:
            back_button.label = back_label
        if back_emoji is not None:
            back_button.emoji = back_emoji
        back_button.callback = self.on_back
        buttons.append(back_button)

        allow_navigation = self.mode in (IdeaViewMode.VIEW, IdeaViewMode.ALL)

        prev_label, prev_emoji = self.cog.get_button_appearance(
            "previous", default_label="Предыдущая"
        )
        previous_button = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            row=2,
            custom_id=self._button_custom_id("previous"),
            disabled=not allow_navigation or self.page <= 0,
        )
        if prev_label is not None:
            previous_button.label = prev_label
        if prev_emoji is not None:
            previous_button.emoji = prev_emoji
        previous_button.callback = self.on_previous
        buttons.append(previous_button)

        has_next = (
            allow_navigation
            and self.page < self.total_pages() - 1
            and bool(self._current_ideas)
        )
        next_label, next_emoji = self.cog.get_button_appearance(
            "next", default_label="Следующая"
        )
        next_button = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            row=2,
            custom_id=self._button_custom_id("next"),
            disabled=not has_next,
        )
        if next_label is not None:
            next_button.label = next_label
        if next_emoji is not None:
            next_button.emoji = next_emoji
        next_button.callback = self.on_next
        buttons.append(next_button)

        return buttons

    def _build_proposal_buttons(self) -> List[disnake.ui.Button]:
        buttons: List[disnake.ui.Button] = []

        edit_label, edit_emoji = self.cog.get_button_appearance(
            "edit", default_label="Редактировать"
        )
        edit_button = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            row=3,
            custom_id=self._button_custom_id("edit"),
            disabled=self.mode is not IdeaViewMode.PROPOSE,
        )
        if edit_label is not None:
            edit_button.label = edit_label
        if edit_emoji is not None:
            edit_button.emoji = edit_emoji
        edit_button.callback = self.on_edit
        buttons.append(edit_button)

        create_label, create_emoji = self.cog.get_button_appearance(
            "create", default_label="Создать"
        )
        create_button = disnake.ui.Button(
            style=disnake.ButtonStyle.secondary,
            row=3,
            custom_id=self._button_custom_id("create"),
            disabled=(
                self.mode is not IdeaViewMode.PROPOSE
                or not self.idea_text.strip()
            ),
        )
        if create_label is not None:
            create_button.label = create_label
        if create_emoji is not None:
            create_button.emoji = create_emoji
        create_button.callback = self.on_create
        buttons.append(create_button)

        return buttons

    # ------------------------------------------------------------------
    # Embed helpers

    def current_embed(self) -> disnake.Embed:
        if self.mode is IdeaViewMode.SUMMARY:
            return self.cog.build_summary_embed(self.guild, self.author)
        if self.mode is IdeaViewMode.PROPOSE:
            return self.cog.build_propose_embed(
                self.guild, self.author, content=self.idea_text or None
            )
        if self.mode is IdeaViewMode.ALL:
            if self.selected_idea_id is not None:
                idea = self.cog.fetch_idea(self.selected_idea_id)
                if idea and idea.guild_id == self.guild.id:
                    return self.cog.build_idea_detail_embed(
                        self.guild,
                        self.author,
                        idea,
                        include_author=True,
                    )
            return self.cog.build_server_summary_embed(self.guild, page=self.page)
        if self.selected_idea_id is not None:
            idea = self.cog.fetch_idea(self.selected_idea_id)
            if idea and idea.author_id == self.author.id:
                return self.cog.build_idea_detail_embed(self.guild, self.author, idea)
        return self.cog.build_view_placeholder_embed(self.guild, self.author, page=self.page)

    async def _edit_message(
        self,
        interaction: disnake.MessageInteraction,
        *,
        embed: Optional[disnake.Embed] = None,
        view: Optional[disnake.ui.View] = None,
    ) -> None:
        if embed is None:
            embed = self.current_embed()
        if view is None:
            view = self
        self.message = interaction.message
        if interaction.response.is_done():
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    # Callbacks

    async def on_back(self, interaction: disnake.MessageInteraction) -> None:
        self.mode = IdeaViewMode.SUMMARY
        self.selected_idea_id = None
        self.page = 0
        self.refresh_components()
        await self._edit_message(interaction, embed=self.current_embed())

    async def on_previous(self, interaction: disnake.MessageInteraction) -> None:
        if self.mode not in (IdeaViewMode.VIEW, IdeaViewMode.ALL):
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Навигация доступна только при просмотре идей.*",
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return
        if self.page > 0:
            self.page -= 1
        self.selected_idea_id = None
        self.refresh_components()
        if self.mode is IdeaViewMode.ALL:
            placeholder_embed = self.cog.build_server_summary_embed(
                self.guild, page=self.page
            )
        else:
            placeholder_embed = self.cog.build_view_placeholder_embed(
                self.guild, self.author, page=self.page
            )
        await self._edit_message(interaction, embed=placeholder_embed)

    async def on_next(self, interaction: disnake.MessageInteraction) -> None:
        if self.mode not in (IdeaViewMode.VIEW, IdeaViewMode.ALL):
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Навигация доступна только при просмотре идей.*",
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return
        if self.page < self.total_pages() - 1:
            self.page += 1
        self.selected_idea_id = None
        self.refresh_components()
        if self.mode is IdeaViewMode.ALL:
            placeholder_embed = self.cog.build_server_summary_embed(
                self.guild, page=self.page
            )
        else:
            placeholder_embed = self.cog.build_view_placeholder_embed(
                self.guild, self.author, page=self.page
            )
        await self._edit_message(interaction, embed=placeholder_embed)

    async def on_edit(self, interaction: disnake.MessageInteraction) -> None:
        if self.mode is not IdeaViewMode.PROPOSE:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Редактирование доступно только при создании идеи.*",
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=self._system_embed(
                "*Отправьте текст вашей идеи в чат.*",
                title="<:created:1434448038587273217> Редактирование идеи",
            ),
            ephemeral=True,
        )

        def check(message: disnake.Message) -> bool:
            return (
                message.author.id == self.author.id
                and message.guild == self.guild
                and message.channel == interaction.channel
            )

        try:
            user_message = await self.cog.bot.wait_for("message", check=check, timeout=180)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=self._system_embed(
                    "*Время ожидания истекло. Повторите попытку.*",
                    title="<:timers:1434911932397129828> Время ожидания истекло",
                ),
                ephemeral=True,
            )
            return

        content = user_message.content.strip()
        truncated = False
        if len(content) > 4000:
            content = content[:4000]
            truncated = True

        self.idea_text = content
        self.refresh_components()
        embed = self.cog.build_propose_embed(self.guild, self.author, content=self.idea_text)
        self.message = interaction.message
        await interaction.message.edit(embed=embed, view=self)

        with contextlib.suppress(disnake.HTTPException):
            await user_message.delete()

        if truncated:
            await interaction.followup.send(
                embed=self._system_embed(
                    "*Текст был сокращен до 4000 символов из-за ограничений Discord.*",
                    title="<:messages:1434448053057749014> Текст сокращен",
                ),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                embed=self._system_embed(
                    "*Текст идеи обновлен.*",
                    title="<:odobreno:1434909104794501243> Успешно",
                ),
                ephemeral=True,
            )

    async def on_create(self, interaction: disnake.MessageInteraction) -> None:
        if self.mode is not IdeaViewMode.PROPOSE:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Создание доступно только в режиме создания идеи.*",
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return
        guild = self.guild
        member = guild.get_member(self.author.id)
        if member is None:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Не удалось определить участника сервера.*",
                    title="<:otkaz:1434909101242060902> Ошибка",
                ),
                ephemeral=True,
            )
            return

        content = self.idea_text.strip()
        if not content:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Пожалуйста введите текст вашей идеи.*",
                    title="<:oprosik:1434913975228956762> Текст не указан",
                ),
                ephemeral=True,
            )
            return

        channel = await self.cog.ensure_idea_channel(guild)
        if channel is None:
            await interaction.response.send_message(
                embed=self._system_embed(
                    "*Канал для идей не настроен. Обратитесь к администрации сервера.*",
                    title="<:channels:1434448044576870470> Канал не найден",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        self.message = interaction.message

        record = await self.cog.create_user_idea(guild, member, content)
        if record is None:
            await interaction.followup.send(
                embed=self._system_embed(
                    "*Не удалось создать идею. Попробуйте позже.*",
                    title="<:otkaz:1434909101242060902> Ошибка",
                ),
                ephemeral=True,
            )
            return

        self.idea_text = ""
        self.mode = IdeaViewMode.SUMMARY
        self.page = 0
        self.selected_idea_id = None
        self.refresh_components()
        embed = self.cog.build_summary_embed(guild, self.author)
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.message.edit(embed=embed, view=self)

        await interaction.followup.send(
            embed=self._system_embed(
                f"*Предложение №{record.id} успешно создано.*",
                title="<:odobreno:1434909104794501243> Успешно",
            ),
            ephemeral=True,
        )


class IdeaPrimarySelect(disnake.ui.Select):
    def __init__(self, view: IdeaMenuView) -> None:
        options = [
            disnake.SelectOption(
                label="Просмотреть свои идеи",
                value="view",
                emoji="<:ideas:1434916461951975526>",
            ),
            disnake.SelectOption(
                label="Все идеи сервера",
                value="all",
                emoji="<:ideas:1434916461951975526>",
            ),
            disnake.SelectOption(
                label="Предложить идею",
                value="propose",
                emoji="<:ideas:1434916461951975526>",
            ),
        ]
        super().__init__(
            placeholder="Нажмите для взаимодействия",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self._idea_view = view

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        value = self.values[0]
        idea_view = self._idea_view

        if value == "view":
            idea_view.mode = IdeaViewMode.VIEW
            idea_view.selected_idea_id = None
            idea_view.page = 0
            idea_view.refresh_components()
            embed = idea_view.cog.build_view_placeholder_embed(
                idea_view.guild, idea_view.author, page=idea_view.page
            )
            await idea_view._edit_message(interaction, embed=embed)
        elif value == "all":
            idea_view.mode = IdeaViewMode.ALL
            idea_view.selected_idea_id = None
            idea_view.page = 0
            idea_view.refresh_components()
            embed = idea_view.cog.build_server_summary_embed(
                idea_view.guild, page=idea_view.page
            )
            await idea_view._edit_message(interaction, embed=embed)
        elif value == "propose":
            idea_view.mode = IdeaViewMode.PROPOSE
            idea_view.refresh_components()
            embed = idea_view.cog.build_propose_embed(
                idea_view.guild, idea_view.author, content=idea_view.idea_text
            )
            await idea_view._edit_message(interaction, embed=embed)


class IdeaListSelect(disnake.ui.Select):
    def __init__(self, view: IdeaMenuView) -> None:
        self._idea_view = view
        placeholder = f"Выберите идею ( Страница {view.page + 1} )"

        options: List[disnake.SelectOption] = []

        if view.mode in (IdeaViewMode.VIEW, IdeaViewMode.ALL) and view._current_ideas:
            for idea in view._current_ideas:
                options.append(
                    disnake.SelectOption(
                        label=f"Предложение №{idea.id}",
                        value=str(idea.id),
                        emoji="<:ideas:1434916461951975526>",
                    )
                )
            disabled = False
        else:
            options.append(
                disnake.SelectOption(
                    label="Предложения недоступны", value="no_ideas", emoji="🚫"
                )
            )
            disabled = True

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )
        self.disabled = disabled

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        value = self.values[0]
        try:
            idea_id = int(value)
        except ValueError:
            await interaction.response.defer()
            return
        idea_view = self._idea_view

        idea = idea_view.cog.fetch_idea(idea_id)
        if idea is None or idea.guild_id != idea_view.guild.id:
            await interaction.response.send_message(
                embed=idea_view._system_embed(
                    "Не удалось найти выбранное предложение.",
                    title="Предложение не найдено",
                ),
                ephemeral=True,
            )
            return

        if idea_view.mode is IdeaViewMode.VIEW and idea.author_id != idea_view.author.id:
            await interaction.response.send_message(
                embed=idea_view._system_embed(
                    "Вы можете просматривать только свои предложения в этом разделе.",
                    title="Доступ ограничен",
                ),
                ephemeral=True,
            )
            return

        idea_view.selected_idea_id = idea.id
        idea_view.refresh_components()
        embed = idea_view.cog.build_idea_detail_embed(
            idea_view.guild,
            idea_view.author,
            idea,
            include_author=idea_view.mode is IdeaViewMode.ALL,
        )
        await idea_view._edit_message(interaction, embed=embed)


class IdeaMessageView(disnake.ui.View):
    def __init__(self, cog: Idea, idea: IdeaRecord) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.idea_id = idea.id
        self.rating_select = IdeaRatingSelect(self, idea.status)
        self.add_item(self.rating_select)
        self.admin_select = IdeaAdminSelect(self, idea.status)
        self.add_item(self.admin_select)

    def get_idea(self) -> Optional[IdeaRecord]:
        idea = self.cog.fetch_idea(self.idea_id)
        if idea is not None:
            self.refresh_component_states(idea.status)
        return idea

    def build_system_embed(
        self,
        message: str,
        *,
        guild: Optional[disnake.Guild] = None,
        title: str = "Системное сообщение",
    ) -> disnake.Embed:
        return self.cog.build_system_message_embed(
            message,
            guild=guild,
            title=title,
        )

    def refresh_component_states(self, status: IdeaStatus) -> None:
        is_pending = status is IdeaStatus.PENDING
        self.rating_select.disabled = not is_pending
        self.rating_select.placeholder = (
            "Нажмите для оценки" if is_pending else "Оценивание недоступно"
        )
        self.admin_select.disabled = not is_pending
        self.admin_select.placeholder = (
            "Для администрации" if is_pending else "Рассмотрено"
        )


class IdeaRatingSelect(disnake.ui.Select):
    def __init__(self, view: IdeaMessageView, status: IdeaStatus) -> None:
        self._idea_view = view
        placeholder = "Нажмите для оценки"
        options = [
            disnake.SelectOption(label="Установить 1 звезду", value="set_1", emoji="⭐"),
            disnake.SelectOption(label="Установить 2 звезды", value="set_2", emoji="⭐"),
            disnake.SelectOption(label="Установить 3 звезды", value="set_3", emoji="⭐"),
            disnake.SelectOption(label="Установить 4 звезды", value="set_4", emoji="⭐"),
            disnake.SelectOption(label="Установить 5 звезд", value="set_5", emoji="⭐"),
            disnake.SelectOption(label="Узнать свою оценку", value="get", emoji="ℹ️"),
            disnake.SelectOption(label="Удалить свою оценку", value="clear", emoji="<:deletes:1434915856814571560>"),
        ]
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            custom_id=f"idea_rating:{view.idea_id}",
        )
        if status is not IdeaStatus.PENDING:
            self.disabled = True
            self.placeholder = "Оценивание недоступно"

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._idea_view.build_system_embed(
                    "*Эта функция доступна только на сервере.*",
                    guild=guild,
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return

        value = self.values[0]
        idea_view = self._idea_view
        idea = idea_view.get_idea()

        if idea is None:
            await interaction.response.send_message(
                embed=self._idea_view.build_system_embed(
                    "*Предложение не найдено.*",
                    guild=guild,
                    title="<:otkaz:1434909101242060902> Ошибка",
                ),
                ephemeral=True,
            )
            return

        if value.startswith("set_"):
            if idea.status is not IdeaStatus.PENDING:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        "*Оценивание для этой идеи недоступно.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Недоступно",
                    ),
                    ephemeral=True,
                )
                return

            try:
                rating = int(value.split("_", 1)[1])
            except ValueError:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        "*Некорректное значение оценки.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Ошибка",
                    ),
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)
            set_idea_rating(idea.id, interaction.user.id, rating)
            if guild:
                await idea_view.cog.update_idea_message(idea.id, guild)
            rating_label = idea_view.cog.format_rating_label(rating)
            await interaction.followup.send(
                embed=self._idea_view.build_system_embed(
                    f"*Вы оставили оценку: {rating_label} для предложения №{idea.id}.*",
                    guild=guild,
                    title="<:odobreno:1434909104794501243> Оценка сохранена",
                ),
                ephemeral=True,
            )
        elif value == "get":
            rating = get_user_rating_for_idea(idea.id, interaction.user.id)
            if rating is None:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        f"*Вы еще не оценивали предложение №{idea.id}.*",
                        guild=guild,
                        title="<:inform:1434448079834320926> Информация",
                    ),
                    ephemeral=True,
                )
            else:
                rating_label = idea_view.cog.format_rating_label(rating)
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        f"*Ваша оценка предложения №{idea.id} составляет {rating_label}.*",
                        guild=guild,
                        title="<:inform:1434448079834320926> Информация",
                    ),
                    ephemeral=True,
                )
        elif value == "clear":
            current_rating = get_user_rating_for_idea(idea.id, interaction.user.id)
            if current_rating is None:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        f"*У вас нет оценки для предложения №{idea.id}.*",
                        guild=guild,
                        title="<:inform:1434448079834320926> Информация",
                    ),
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)
            remove_idea_rating(idea.id, interaction.user.id)
            if guild:
                await idea_view.cog.update_idea_message(idea.id, guild)
            rating_label = idea_view.cog.format_rating_label(current_rating)
            await interaction.followup.send(
                embed=self._idea_view.build_system_embed(
                    f"*Вы удалили свою оценку {rating_label} для предложения №{idea.id}.*",
                    guild=guild,
                    title="<:deletes:1434915856814571560> Оценка удалена",
                ),
                ephemeral=True,
            )


class IdeaAdminSelect(disnake.ui.Select):
    def __init__(self, view: IdeaMessageView, status: IdeaStatus) -> None:
        self._idea_view = view
        options = [
            disnake.SelectOption(label="Одобрить идею", value="approve", emoji="<:odobreno:1434909104794501243>"),
            disnake.SelectOption(label="Отклонить идею", value="reject", emoji="<:otkaz:1434909101242060902>"),
            disnake.SelectOption(label="Удалить идею", value="delete", emoji="<:deletes:1434915856814571560>"),
        ]
        super().__init__(
            placeholder="Для администрации",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
            custom_id=f"idea_admin:{view.idea_id}",
        )
        if status is not IdeaStatus.PENDING:
            self.disabled = True
            self.placeholder = "Рассмотрено"

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, disnake.Member):
            await interaction.response.send_message(
                embed=self._idea_view.build_system_embed(
                    "*Действие доступно только на сервере.*",
                    guild=guild,
                    title="<:otkaz:1434909101242060902> Недоступно",
                ),
                ephemeral=True,
            )
            return

        idea_view = self._idea_view
        idea = idea_view.get_idea()
        if idea is None:
            await interaction.response.send_message(
                embed=self._idea_view.build_system_embed(
                    "*Предложение не найдено.*",
                    guild=guild,
                    title="<:otkaz:1434909101242060902> Ошибка",
                ),
                ephemeral=True,
            )
            return
        if not idea_view.cog.is_idea_admin(interaction.user):
            await interaction.response.send_message(
                embed=self._idea_view.build_system_embed(
                    "*У вас нет прав для управления предложениями.*",
                    guild=guild,
                    title="<:otkaz:1434909101242060902> Доступ запрещен",
                ),
                ephemeral=True,
            )
            return

        value = self.values[0]

        if value == "approve":
            if idea.status is not IdeaStatus.PENDING:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        "*Это предложение уже рассмотрено.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Недоступно",
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True)
            refreshed = idea_view.cog.fetch_idea(idea.id)
            if refreshed is None:
                await interaction.followup.send(
                    embed=self._idea_view.build_system_embed(
                        "*Не удалось найти предложение.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Ошибка",
                    ),
                    ephemeral=True,
                )
                return
            await idea_view.cog.approve_idea(refreshed, guild, interaction.user)
            await interaction.followup.send(
                embed=self._idea_view.build_system_embed(
                    f"*Вы одобрили предложение №{idea.id}.*",
                    guild=guild,
                    title="<:odobreno:1434909104794501243> Успешно",
                ),
                ephemeral=True,
            )
        elif value == "reject":
            if idea.status is not IdeaStatus.PENDING:
                await interaction.response.send_message(
                    embed=self._idea_view.build_system_embed(
                        "*Это предложение уже рассмотрено.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Недоступно",
                    ),
                    ephemeral=True,
                )
                return
            modal = IdeaRejectModal(idea_view.cog, idea_view.idea_id)
            await interaction.response.send_modal(modal)
        elif value == "delete":
            await interaction.response.defer(ephemeral=True)
            refreshed = idea_view.cog.fetch_idea(idea.id)
            if refreshed is None:
                await interaction.followup.send(
                    embed=self._idea_view.build_system_embed(
                        "*Не удалось найти предложение.*",
                        guild=guild,
                        title="<:otkaz:1434909101242060902> Ошибка",
                    ),
                    ephemeral=True,
                )
                return
            await idea_view.cog.delete_idea_entry(refreshed, guild)
            await interaction.followup.send(
                embed=self._idea_view.build_system_embed(
                    f"*Предложение №{idea.id} удалено.*",
                    guild=guild,
                    title="<:deletes:1434915856814571560> Удалено",
                ),
                ephemeral=True,
            )


class IdeaRejectModal(disnake.ui.Modal):
    def __init__(self, cog: Idea, idea_id: int) -> None:
        self.cog = cog
        self.idea_id = idea_id
        self.reason_input = disnake.ui.TextInput(
            label="Причина отклонения",
            placeholder="Опишите причину отклонения",
            custom_id="reject_reason",
            style=disnake.TextInputStyle.paragraph,
            max_length=500,
            required=True,
        )
        super().__init__(
            title="Отклонить идею",
            components=[self.reason_input],
        )

    async def callback(self, interaction: disnake.ModalInteraction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, disnake.Member):
            await interaction.response.send_message(
                embed=self.cog.build_system_message_embed(
                    "Действие доступно только на сервере.",
                    guild=guild,
                    title="Недоступно",
                ),
                ephemeral=True,
            )
            return

        if not self.cog.is_idea_admin(interaction.user):
            await interaction.response.send_message(
                embed=self.cog.build_system_message_embed(
                    "У вас нет прав для управления предложениями.",
                    guild=guild,
                    title="Доступ запрещен",
                ),
                ephemeral=True,
            )
            return

        reason = (interaction.text_values.get(self.reason_input.custom_id, "") or "").strip()
        if not reason:
            await interaction.response.send_message(
                embed=self.cog.build_system_message_embed(
                    "Укажите причину отклонения.",
                    guild=guild,
                    title="Требуется причина",
                ),
                ephemeral=True,
            )
            return

        idea = self.cog.fetch_idea(self.idea_id)
        if idea is None:
            await interaction.response.send_message(
                embed=self.cog.build_system_message_embed(
                    "Предложение не найдено.",
                    guild=guild,
                    title="Ошибка",
                ),
                ephemeral=True,
            )
            return

        if idea.status is not IdeaStatus.PENDING:
            await interaction.response.send_message(
                embed=self.cog.build_system_message_embed(
                    "Это предложение уже рассмотрено.",
                    guild=guild,
                    title="Недоступно",
                ),
                ephemeral=True,
            )
            return

        await self.cog.reject_idea(idea, guild, interaction.user, reason)
        await interaction.response.send_message(
            embed=self.cog.build_system_message_embed(
                f"Вы отклонили предложение №{idea.id}.",
                guild=guild,
                title="Отклонено",
            ),
            ephemeral=True,
        )

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Idea(bot))