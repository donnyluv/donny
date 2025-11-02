from __future__ import annotations

from typing import Iterable, List, Sequence, Set

import re

import importlib.util
import sys
import types

import disnake
from disnake.ext import commands
from disnake.abc import User

from pathlib import Path


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


database_module = _load_database_module()

get_connection = database_module.get_connection
load_system_embed_colours = database_module.load_system_embed_colours
set_system_embed_colour = database_module.set_system_embed_colour

SYSTEM_COLOUR_PRESETS: Sequence[dict[str, object]] = [
    {
        "label": "Зелёный",
        "value": 0x57F287,
        "description": "Яркий зеленый оттенок для уведомлений.",
        "emoji": "💚",
    },
    {
        "label": "Золотой",
        "value": 0xFEE75C,
        "description": "Теплый золотистый цвет с высоким контрастом.",
        "emoji": "💛",
    },
    {
        "label": "Красный",
        "value": 0xED4245,
        "description": "Выразительный красный оттенок для важных сообщений.",
        "emoji": "❤️",
    },
    {
        "label": "Синий",
        "value": 0x0400ff,
        "description": "Холодный синий цвет для свежего оформления.",
        "emoji": "💙",
    },
    {
        "label": "Фиолетовый",
        "value": 0x9B59B6,
        "description": "Глубокий фиолетовый оттенок для спокойных эмбедов.",
        "emoji": "💜",
    },
]


class Settings(commands.Cog):
    """Предоставляет интерфейс настройки сервера."""

    BUTTON_APPEARANCE: dict[
        str, dict[str, str | None] | str | disnake.PartialEmoji | None
    ] = {
        "back": {"label": "Назад", "emoji": None},
        "clear": {"label": "Очистить список ролей", "emoji": None},
        "previous": {"label": None, "emoji": "<:pred:1434251697022173284>"},
        "next": {"label": None, "emoji": "<:next:1434250501863772170>"},
    }

    DEFAULT_SYSTEM_COLOUR_VALUE = disnake.Colour.blurple().value

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._auto_roles: dict[int, Set[int]] = {}
        self._load_auto_roles()
        self._system_colours: dict[int, int] = load_system_embed_colours()

    @commands.command(name="settings")
    async def settings_command(self, ctx: commands.Context) -> None:
        """Отправляет сообщение с настройками сервера и интерактивными элементами."""
        guild = ctx.guild

        if guild is None:
            await ctx.send("Эту команду можно использовать только на сервере.")
            return

        embed = self.build_settings_embed(guild)
        view = SettingsView(self, ctx.author, guild)
        await ctx.send(embed=embed, view=view)

    def build_settings_embed(self, guild: disnake.Guild) -> disnake.Embed:
        embed = disnake.Embed(
            title="Настройки сервера:",
            description="Взаимодействуйте с выпадающим меню выбора для настройки сервера",
            colour=self.get_system_colour(guild.id),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        return embed

    def build_auto_roles_embed(self, guild: disnake.Guild) -> disnake.Embed:
        selected_roles = self.get_auto_roles(guild.id)
        description_lines: List[str] = []

        if selected_roles:
            resolved_roles = self._resolve_roles(guild, selected_roles)
            for index, role in enumerate(resolved_roles):
                description_lines.append(f"> ➜ {role.mention}")
                if index != len(resolved_roles) - 1:
                    description_lines.append("")
        else:
            description_lines.append("Список автоматических ролей пуст.")

        description_lines.extend(
            [
                "",
                "Воспользуйтесь выпадающим меню выбора для назначения автоматических ролей",
            ]
        )

        embed = disnake.Embed(
            title="Автоматические роли",
            description="\n".join(description_lines),
            colour=self.get_system_colour(guild.id),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        return embed

    def build_success_embed(self, guild: disnake.Guild) -> disnake.Embed:
        return disnake.Embed(
            title="Настройки успешно сохранены",
            colour=self.get_system_colour(guild.id),
        )

    def build_system_colour_embed(self, guild: disnake.Guild) -> disnake.Embed:
        current_raw = self.get_system_colour_raw(guild.id)

        description_lines = [
            "Выберите основной цвет, который будет использоваться во всех системных сообщениях бота.",
            "Ваш выбор немедленно применяется ко всем новым эмбедам.",
            "",
            f"Текущий цвет: `{self.format_system_colour_label(current_raw)}`",
        ]

        embed = disnake.Embed(
            title="Цвет системных сообщений",
            description="\n".join(description_lines),
            colour=self.get_system_colour(guild.id),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        return embed

    def get_system_colour_raw(self, guild_id: int) -> int | None:
        return self._system_colours.get(guild_id)

    def get_system_colour(self, guild_id: int) -> disnake.Colour:
        raw_value = self.get_system_colour_raw(guild_id)
        if raw_value is None:
            raw_value = self.DEFAULT_SYSTEM_COLOUR_VALUE
        return disnake.Colour(raw_value)

    def set_system_colour(self, guild_id: int, colour_value: int | None) -> None:
        if colour_value is None:
            self._system_colours.pop(guild_id, None)
        else:
            self._system_colours[guild_id] = colour_value
        set_system_embed_colour(guild_id, colour_value)

    def format_system_colour_label(self, colour_value: int | None) -> str:
        if colour_value is None:
            return "Стандартный (Blurple)"

        for preset in SYSTEM_COLOUR_PRESETS:
            preset_value = preset.get("value")
            if isinstance(preset_value, int) and preset_value == colour_value:
                label = preset.get("label")
                if isinstance(label, str) and label:
                    return f"{label} (#{colour_value:06X})"
                break

        return f"#{colour_value:06X}"

    _CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:[A-Za-z0-9_~]+:[0-9]{15,22}>$")

    def get_button_appearance(
        self, button_key: str
    ) -> tuple[str | None, disnake.PartialEmoji | str | None]:
        config = self.BUTTON_APPEARANCE.get(button_key)

        label: str | None = None
        emoji_value: str | disnake.PartialEmoji | None = None

        if isinstance(config, dict):
            label = config.get("label")
            emoji_value = config.get("emoji")
        elif isinstance(config, (str, disnake.PartialEmoji)):
            label = str(config)
        elif config is None:
            label = None
            emoji_value = None
        else:
            label = str(config)

        emoji: disnake.PartialEmoji | str | None = None

        if emoji_value:
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

        return label, emoji

    def get_auto_roles(self, guild_id: int) -> Set[int]:
        return self._auto_roles.setdefault(guild_id, set())

    def set_auto_roles(self, guild_id: int, role_ids: Iterable[int]) -> None:
        roles = set(role_ids)
        self._auto_roles[guild_id] = roles
        self._store_auto_roles(guild_id, roles)

    def _resolve_roles(self, guild: disnake.Guild, role_ids: Iterable[int]) -> List[disnake.Role]:
        role_map = {role.id: role for role in guild.roles}
        resolved = [role_map[role_id] for role_id in role_ids if role_id in role_map]
        resolved.sort(key=lambda role: role.position, reverse=True)
        return resolved

    def _ensure_auto_roles_table(self, cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_roles (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )

    def _load_auto_roles(self) -> None:
        with get_connection() as connection:
            cursor = connection.cursor()
            self._ensure_auto_roles_table(cursor)
            cursor.execute("SELECT guild_id, role_id FROM auto_roles")
            rows = cursor.fetchall()

        for guild_id, role_id in rows:
            self._auto_roles.setdefault(guild_id, set()).add(role_id)

    def _store_auto_roles(self, guild_id: int, role_ids: Set[int]) -> None:
        with get_connection() as connection:
            cursor = connection.cursor()
            self._ensure_auto_roles_table(cursor)
            cursor.execute("DELETE FROM auto_roles WHERE guild_id = ?", (guild_id,))
            if role_ids:
                cursor.executemany(
                    "INSERT OR REPLACE INTO auto_roles (guild_id, role_id) VALUES (?, ?)",
                    [(guild_id, role_id) for role_id in role_ids],
                )
            connection.commit()

    async def assign_auto_roles_to_member(self, member: disnake.Member) -> None:
        guild = member.guild
        role_ids = self.get_auto_roles(guild.id)
        if not role_ids:
            return

        me = guild.me
        if me is None:
            return

        roles_to_assign = [
            role
            for role in self._resolve_roles(guild, role_ids)
            if role < me.top_role and not role.managed and role != guild.default_role
        ]

        if not roles_to_assign:
            return

        missing_roles = [role for role in roles_to_assign if role not in member.roles]
        if not missing_roles:
            return

        try:
            await member.add_roles(*missing_roles, reason="Auto role assignment")
        except disnake.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: disnake.Member) -> None:
        await self.assign_auto_roles_to_member(member)


class BaseSettingsView(disnake.ui.View):
    def __init__(self, cog: Settings, author: User, guild: disnake.Guild) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.guild = guild

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Только автор команды может взаимодействовать с этими настройками.",
                ephemeral=True,
            )
            return False
        return True

    async def _ensure_deferred(self, interaction: disnake.MessageInteraction) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer()

    async def _edit_message(
        self,
        interaction: disnake.MessageInteraction,
        *,
        embed: disnake.Embed | None = None,
        view: disnake.ui.View | None = None,
    ) -> None:
        await self._ensure_deferred(interaction)
        await interaction.message.edit(embed=embed, view=view)

    async def _send_success(self, interaction: disnake.MessageInteraction) -> None:
        await interaction.followup.send(
            embed=self.cog.build_success_embed(self.guild), ephemeral=True
        )

    def _apply_button_appearance(
        self, button_map: dict[str, disnake.ui.Button]
    ) -> None:
        for key, button in button_map.items():
            label, emoji = self.cog.get_button_appearance(key)
            button.label = label if label is not None else None
            button.emoji = emoji


class SettingsView(BaseSettingsView):
    def __init__(self, cog: Settings, author: User, guild: disnake.Guild) -> None:
        super().__init__(cog, author, guild)
        self.select_menu = SettingsSelect(self)
        self.add_item(self.select_menu)


class SettingsSelect(disnake.ui.Select):
    def __init__(self, view: SettingsView) -> None:
        options = [
            disnake.SelectOption(
                label="Автоматические роли",
                value="auto_roles",
                emoji="⚙️",
                description="Настройка автоматической выдачи ролей",
            ),
            disnake.SelectOption(
                label="Цвет системных сообщений",
                value="system_colour",
                emoji="🎨",
                description="Выбор основного цвета эмбедов бота",
            ),
        ]
        super().__init__(
            placeholder="Выберите раздел настроек",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._settings_view = view

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        value = self.values[0]
        if value == "auto_roles":
            settings_view = self._settings_view
            auto_view = AutoRolesView(settings_view.cog, settings_view.author, settings_view.guild)
            embed = settings_view.cog.build_auto_roles_embed(settings_view.guild)
            await interaction.response.edit_message(embed=embed, view=auto_view)
        elif value == "system_colour":
            settings_view = self._settings_view
            colour_view = SystemColourView(
                settings_view.cog, settings_view.author, settings_view.guild
            )
            embed = settings_view.cog.build_system_colour_embed(settings_view.guild)
            await interaction.response.edit_message(embed=embed, view=colour_view)


class AutoRolesView(BaseSettingsView):
    roles_per_page = 15

    def __init__(
        self,
        cog: Settings,
        author: User,
        guild: disnake.Guild,
        page: int = 0,
    ) -> None:
        super().__init__(cog, author, guild)
        self.page = page
        self.select_menu = AutoRolesSelect(self)
        self.add_item(self.select_menu)
        self._apply_button_appearance(
            {
                "back": self.back_button,
                "clear": self.clear_button,
                "previous": self.previous_button,
                "next": self.next_button,
            }
        )
        self.update_components()

    def available_roles(self) -> List[disnake.Role]:
        return [role for role in reversed(self.guild.roles) if role != self.guild.default_role]

    def total_pages(self) -> int:
        roles = self.available_roles()
        if not roles:
            return 1
        return (len(roles) - 1) // self.roles_per_page + 1

    def get_page_roles(self) -> Sequence[disnake.Role]:
        roles = self.available_roles()
        start = self.page * self.roles_per_page
        end = start + self.roles_per_page
        return roles[start:end]

    def selected_role_ids(self) -> Set[int]:
        return set(self.cog.get_auto_roles(self.guild.id))

    def apply_page_selection(self, role_ids: Set[int]) -> None:
        stored = self.selected_role_ids()
        page_role_ids = {role.id for role in self.get_page_roles()}
        stored.difference_update(page_role_ids)
        stored.update(role_ids)
        self.cog.set_auto_roles(self.guild.id, stored)

    def update_components(self) -> None:
        page_roles = list(self.get_page_roles())
        selected_ids = self.selected_role_ids()

        options: List[disnake.SelectOption] = []
        for role in page_roles:
            options.append(
                disnake.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    emoji="<:boosts:1434448041661694024>",
                    default=role.id in selected_ids,
                )
            )

        if options:
            self.select_menu.disabled = False
            self.select_menu.options = options
            max_values = min(len(options), 25)
            self.select_menu.max_values = max(max_values, 1)
            self.select_menu.min_values = 0
        else:
            self.select_menu.disabled = True
            self.select_menu.options = [
                disnake.SelectOption(
                    label="Нет доступных ролей", value="noop", description="На этой странице нет ролей"
                )
            ]
            self.select_menu.max_values = 1
            self.select_menu.min_values = 0

        placeholder = self._build_placeholder(page_roles, selected_ids)
        self.select_menu.placeholder = placeholder

        has_prev = self.page > 0
        has_next = self.page < self.total_pages() - 1

        self.previous_button.disabled = not has_prev
        self.next_button.disabled = not has_next
        self.clear_button.disabled = not bool(selected_ids)

    def _build_placeholder(
        self, page_roles: Sequence[disnake.Role], selected_ids: Set[int]
    ) -> str:
        page_selected = [role.mention for role in page_roles if role.id in selected_ids]
        if not page_selected:
            return f"Роли не выбраны ( Страница {self.page + 1} )"

        mentions = page_selected
        placeholder_base = ", ".join(mentions)
        if len(placeholder_base) > 90:
            placeholder_base = placeholder_base[:87] + "..."
        return f"{placeholder_base} ( Страница {self.page + 1} )"

    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, row=1)
    async def back_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        embed = self.cog.build_settings_embed(self.guild)
        view = SettingsView(self.cog, self.author, self.guild)
        await self._edit_message(interaction, embed=embed, view=view)

    @disnake.ui.button(label="Очистить список ролей", style=disnake.ButtonStyle.secondary, row=1)
    async def clear_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        self.cog.set_auto_roles(self.guild.id, [])
        self.update_components()
        embed = self.cog.build_auto_roles_embed(self.guild)
        await self._edit_message(interaction, embed=embed, view=self)
        await self._send_success(interaction)

    @disnake.ui.button(label="Предыдущая", style=disnake.ButtonStyle.secondary, row=1)
    async def previous_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        if self.page > 0:
            self.page -= 1
        self.update_components()
        embed = self.cog.build_auto_roles_embed(self.guild)
        await self._edit_message(interaction, embed=embed, view=self)

    @disnake.ui.button(label="Следующая", style=disnake.ButtonStyle.secondary, row=1)
    async def next_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        if self.page < self.total_pages() - 1:
            self.page += 1
        self.update_components()
        embed = self.cog.build_auto_roles_embed(self.guild)
        await self._edit_message(interaction, embed=embed, view=self)

class AutoRolesSelect(disnake.ui.Select):
    def __init__(self, view: AutoRolesView) -> None:
        super().__init__(placeholder="Роли не выбраны", min_values=0, max_values=1, row=0)
        self._auto_roles_view = view

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        auto_view = self._auto_roles_view

        if auto_view.select_menu.disabled:
            await interaction.response.defer()
            return

        values = self.values
        selected_ids = {int(value) for value in values} if values else set()
        auto_view.apply_page_selection(selected_ids)
        auto_view.update_components()
        embed = auto_view.cog.build_auto_roles_embed(auto_view.guild)
        await auto_view._edit_message(interaction, embed=embed, view=auto_view)
        await auto_view._send_success(interaction)


class SystemColourView(BaseSettingsView):
    def __init__(self, cog: Settings, author: User, guild: disnake.Guild) -> None:
        super().__init__(cog, author, guild)
        self.select_menu = SystemColourSelect(self)
        self.add_item(self.select_menu)
        self._apply_button_appearance({"back": self.back_button})
        self.update_components()

    def update_components(self) -> None:
        current_raw = self.cog.get_system_colour_raw(self.guild.id)

        def mark_description(base: str | None, is_current: bool) -> str | None:
            if not is_current:
                return base
            if base:
                return f"{base} (текущий)"
            return "Текущий цвет"

        options: List[disnake.SelectOption] = [
            disnake.SelectOption(
                label="Стандартный (Blurple)",
                value="default",
                description=mark_description(
                    "Использовать стандартный цвет Discord.", current_raw is None
                ),
                emoji="💠",
                default=False,
            )
        ]

        preset_values: Set[int] = set()
        for preset in SYSTEM_COLOUR_PRESETS:
            label = str(preset.get("label", ""))
            value = preset.get("value")
            description = preset.get("description")
            emoji = preset.get("emoji")
            if not isinstance(value, int):
                continue

            preset_values.add(value)
            options.append(
                disnake.SelectOption(
                    label=label or f"#{value:06X}",
                    value=str(value),
                    description=mark_description(
                        str(description) if description else None, current_raw == value
                    ),
                    emoji=str(emoji) if emoji else None,
                    default=False,
                )
            )

        options.append(
            disnake.SelectOption(
                label="Кастомный цвет",
                value="custom",
                description=mark_description(
                    "Укажите собственный HEX-код цвета.",
                    current_raw is not None and current_raw not in preset_values,
                ),
                emoji="🖌️",
                default=False,
            )
        )

        current_label = self.cog.format_system_colour_label(current_raw)

        prompt_option = disnake.SelectOption(
            label="Выберите цвет",
            value="prompt",
            description=f"Текущий цвет: {current_label}",
            emoji="🎨",
            default=True,
        )

        self.select_menu.options = [prompt_option, *options]
        self.select_menu.placeholder = "Выберите цвет"

    def apply_selection(self, colour_value: int | None) -> None:
        self.cog.set_system_colour(self.guild.id, colour_value)
        self.update_components()

    @disnake.ui.button(label="Назад", style=disnake.ButtonStyle.secondary, row=1)
    async def back_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        embed = self.cog.build_settings_embed(self.guild)
        view = SettingsView(self.cog, self.author, self.guild)
        await self._edit_message(interaction, embed=embed, view=view)

    @disnake.ui.button(label="Сбросить цвет", style=disnake.ButtonStyle.secondary, row=1)
    async def reset_button(
        self, button: disnake.ui.Button, interaction: disnake.MessageInteraction
    ) -> None:
        self.apply_selection(None)
        embed = self.cog.build_system_colour_embed(self.guild)
        await self._edit_message(interaction, embed=embed, view=self)
        await self._send_success(interaction)


class SystemColourSelect(disnake.ui.Select):
    def __init__(self, view: SystemColourView) -> None:
        super().__init__(placeholder="Выберите цвет", min_values=1, max_values=1)
        self._colour_view = view

    async def callback(self, interaction: disnake.MessageInteraction) -> None:
        value = self.values[0]
        colour_view = self._colour_view

        if value == "prompt":
            await interaction.response.send_message(
                "Пожалуйста, выберите цвет из списка ниже.", ephemeral=True
            )
            return

        if value == "default":
            colour_value: int | None = None
        elif value == "custom":
            await interaction.response.send_modal(CustomColourModal(colour_view))
            return
        else:
            try:
                colour_value = int(value)
            except ValueError:
                colour_value = None

        colour_view.apply_selection(colour_value)
        embed = colour_view.cog.build_system_colour_embed(colour_view.guild)
        await colour_view._edit_message(interaction, embed=embed, view=colour_view)
        await colour_view._send_success(interaction)


class CustomColourModal(disnake.ui.Modal):
    _HEX_PATTERN = re.compile(r"^#?[0-9A-Fa-f]{6}$")

    def __init__(self, colour_view: SystemColourView) -> None:
        self._colour_view = colour_view
        self.colour_input = disnake.ui.TextInput(
            label="Введите HEX-код цвета",
            placeholder="#57F287",
            custom_id="custom_colour",
            min_length=6,
            max_length=7,
            style=disnake.TextInputStyle.short,
        )
        super().__init__(
            title="Кастомный цвет",
            components=[self.colour_input],
        )

    async def callback(self, interaction: disnake.ModalInteraction) -> None:
        raw_value = (
            interaction.text_values.get(self.colour_input.custom_id, "")
            if hasattr(interaction, "text_values")
            else self.colour_input.value or ""
        ).strip()

        if not raw_value:
            await interaction.response.send_message(
                "Пожалуйста, укажите шестнадцатеричный код цвета в формате #RRGGBB.",
                ephemeral=True,
            )
            return

        if not self._HEX_PATTERN.fullmatch(raw_value):
            await interaction.response.send_message(
                "Некорректный код цвета. Используйте формат #RRGGBB.",
                ephemeral=True,
            )
            return

        hex_part = raw_value.lstrip("#")
        colour_value = int(hex_part, 16)

        colour_view = self._colour_view
        colour_view.apply_selection(colour_value)
        embed = colour_view.cog.build_system_colour_embed(colour_view.guild)
        await colour_view._edit_message(interaction, embed=embed, view=colour_view)
        await colour_view._send_success(interaction)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Settings(bot))