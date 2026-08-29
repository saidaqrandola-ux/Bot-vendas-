import asyncio
import logging

import discord
from discord.ext import commands

import config
import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("loja-bot")

INTENTS = discord.Intents.default()
INTENTS.message_content = True  # necessário para ler anexos de comprovante em mensagens
INTENTS.members = True  # necessário para checar cargos (CEO/Atendente) corretamente

bot = commands.Bot(command_prefix="!", intents=INTENTS)

COGS = [
    "cogs.tickets",
    "cogs.store",
    "cogs.orders",
    "cogs.admin",
]


@bot.event
async def on_ready():
    log.info(f"Conectado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        log.info(f"{len(synced)} slash commands sincronizados.")
    except Exception as e:
        log.exception(f"Erro ao sincronizar comandos: {e}")


async def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "❌ DISCORD_TOKEN não configurado. Defina a variável de ambiente DISCORD_TOKEN (.env ou Railway Variables)."
        )

    db.init_db()
    log.info("Banco de dados inicializado.")

    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            log.info(f"Cog carregado: {cog}")
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
