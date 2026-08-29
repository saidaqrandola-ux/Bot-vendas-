import discord
import config


def is_ceo(member: discord.Member) -> bool:
    return any(role.id == config.CEO_ROLE_ID for role in getattr(member, "roles", []))


def is_atendente(member: discord.Member) -> bool:
    return is_ceo(member) or any(role.id == config.ATENDENTE_ROLE_ID for role in getattr(member, "roles", []))


def cargo_requerido_ceo():
    """Decorator para slash commands restritos ao CEO."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if is_ceo(interaction.user):
            return True
        await interaction.response.send_message(
            "🚫 Apenas o CEO pode usar este comando.", ephemeral=True
        )
        return False

    import discord.app_commands as app_commands

    return app_commands.check(predicate)


def cargo_requerido_atendente():
    """Decorator para slash commands restritos a Atendente ou CEO."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if is_atendente(interaction.user):
            return True
        await interaction.response.send_message(
            "🚫 Apenas atendentes ou o CEO podem usar este comando.", ephemeral=True
        )
        return False

    import discord.app_commands as app_commands

    return app_commands.check(predicate)
