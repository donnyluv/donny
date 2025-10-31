from pathlib import Path

import disnake
from disnake.ext import commands

import config

# Включаем интенты, необходимые для работы префиксных команд.
intents = disnake.Intents.default()
intents.message_content = True

# Создаем экземпляр бота с префиксом "!".
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Сообщаем в консоль о том, что бот успешно запустился."""
    print(f"Бот готов к работе как {bot.user} (ID: {bot.user.id})")


def load_extensions() -> None:
    """Загружаем все файлы-коги из папки cogs."""
    for path in sorted(Path("cogs").glob("*.py")):
        if path.name.startswith("__") or path.name.startswith("_"):
            continue
        bot.load_extension(f"cogs.{path.stem}")


if __name__ == "__main__":
    load_extensions()
    bot.run(config.TOKEN)