"""Основной файл запуска Discord-бота на библиотеке disnake."""

import logging
import sys
from pathlib import Path

import disnake
from aiohttp import ClientConnectorError
from disnake.errors import LoginFailure, PrivilegedIntentsRequired
from disnake.ext import commands
from disnake.ext.commands import errors as commands_errors

import config

# Настраиваем базовые параметры логирования для удобной отладки.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

# Определяем список интентов. Для большинства базовых задач подойдут стандартные интенты.
intents = disnake.Intents.default()
intents.message_content = True  # Необходимо для работы префиксных команд.

# Создаем экземпляр бота с нужным префиксом команд.
bot = commands.Bot(command_prefix="!", intents=intents)


def load_cogs(bot_instance: commands.Bot) -> None:
    """Автоматически загружает все расширения (когии) из папки cogs."""
    cogs_path = Path("cogs")
    for file in cogs_path.glob("*.py"):
        if file.name.startswith("__") or file.name.startswith("_"):
            logging.debug(
                "Файл %s пропущен при загрузке когов (служебное имя)", file.name
            )
            continue

        extension = f"cogs.{file.stem}"

        try:
            bot_instance.load_extension(extension)
        except commands_errors.NoEntryPointError:
            logging.warning(
                "Модуль %s не содержит функцию setup и будет пропущен", extension
            )
        except commands_errors.ExtensionNotFound:
            logging.exception(
                "Модуль %s не найден, проверьте файл или импорт", extension
            )
        except commands_errors.ExtensionFailed:
            logging.exception(
                "Ког %s не удалось инициализировать из-за ошибки при исполнении", extension
            )
        except commands_errors.ExtensionError:
            logging.exception(
                "Неизвестная ошибка при загрузке %s", extension
            )
        else:
            logging.info("Ког %s успешно загружен", extension)


@bot.event
async def on_connect():
    """Фиксируем успешное соединение с Discord перед авторизацией."""
    logging.info("Установлено соединение с сервером Discord")


@bot.event
async def on_ready():
    """Сообщаем в консоль о готовности бота после авторизации."""
    logging.info("Бот авторизовался как %s (ID: %s)", bot.user, bot.user.id)


@bot.event
async def on_disconnect():
    """Логируем ситуацию, когда бот потерял соединение."""
    logging.warning("Соединение с Discord потеряно, ожидаем переподключение…")


def _prepare_token(raw_token: str) -> str:
    """Проверяет токен и возвращает его очищенную версию."""
    token = (raw_token or "").strip()
    placeholder = "ВСТАВЬТЕ_СЮДА_СВОЙ_ТОКЕН"

    if not token or token == placeholder:
        logging.error(
            "Токен не указан. Откройте config.py и вставьте действительный токен вместо заглушки."
        )
        raise ValueError("TOKEN is missing")

    return token


if __name__ == "__main__":
    load_cogs(bot)
    try:
        prepared_token = _prepare_token(config.TOKEN)
    except ValueError:
        sys.exit(1)

    logging.info("Запускаем бота и пытаемся авторизоваться…")

    try:
        # Запускаем бота, используя токен из конфигурационного файла.
        bot.run(prepared_token)
    except LoginFailure:
        logging.exception(
            "Авторизация завершилась неудачно. Проверьте правильность токена и его актуальность."
        )
        sys.exit(1)
    except PrivilegedIntentsRequired:
        logging.exception(
            "Для этого бота необходимо включить привилегированные интенты в настройках приложения."
        )
        sys.exit(1)
    except ClientConnectorError:
        logging.exception(
            "Не удалось подключиться к серверам Discord. Проверьте подключение к интернету, доступ к домену discord.com и повторите попытку."
        )
        sys.exit(1)