import datetime

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils.permissions import is_ceo, is_atendente


def _erro_ceo():
    return "🚫 Apenas o CEO pode usar este comando."


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    produto_group = app_commands.Group(name="produto", description="Gestão de produtos")
    estoque_group = app_commands.Group(name="estoque", description="Gestão de estoque")
    preco_group = app_commands.Group(name="preco", description="Gestão de preços de venda")
    custo_group = app_commands.Group(name="custo", description="Gestão de preço de custo")
    cupom_group = app_commands.Group(name="cupom-admin", description="Gestão de cupons (CEO)")
    frete_group = app_commands.Group(name="frete", description="Gestão de frete")

    # ---------------- /produto ----------------
    @produto_group.command(name="adicionar", description="Adicionar um novo produto (CEO)")
    async def produto_adicionar(
        self, interaction: discord.Interaction, nome: str, preco_venda: float, preco_custo: float,
        permite_personalizacao: bool, descricao: str = "", imagem_url: str = "",
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        produto_id = db.criar_produto(nome, descricao, preco_venda, preco_custo, permite_personalizacao, imagem_url)
        await interaction.response.send_message(f"✅ Produto **{nome}** criado com ID `{produto_id}`.", ephemeral=True)

    @produto_group.command(name="editar", description="Editar um produto existente (CEO)")
    async def produto_editar(
        self, interaction: discord.Interaction, produto_id: int, nome: str = "", descricao: str = "",
        imagem_url: str = "",
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        campos = {k: v for k, v in {"nome": nome, "descricao": descricao, "imagem_url": imagem_url}.items() if v}
        if not campos:
            return await interaction.response.send_message("Nada para editar.", ephemeral=True)
        db.editar_produto(produto_id, **campos)
        await interaction.response.send_message(f"✅ Produto `{produto_id}` atualizado.", ephemeral=True)

    @produto_group.command(name="remover", description="Remover um produto (CEO)")
    async def produto_remover(self, interaction: discord.Interaction, produto_id: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.remover_produto(produto_id)
        await interaction.response.send_message(f"🗑️ Produto `{produto_id}` removido.", ephemeral=True)

    @produto_group.command(name="listar", description="Listar todos os produtos, incluindo ocultos (CEO)")
    async def produto_listar(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        produtos = db.listar_produtos(apenas_visiveis=False)
        if not produtos:
            return await interaction.response.send_message("Nenhum produto cadastrado.", ephemeral=True)
        texto = "\n".join(
            f"`{p['id']}` {p['nome']} — venda R$ {p['preco_venda']:.2f} / custo R$ {p['preco_custo']:.2f} "
            f"{'🙈 oculto' if p['oculto'] else ''} {'⭐' if p['destaque'] else ''}"
            for p in produtos
        )
        await interaction.response.send_message(texto[:1900], ephemeral=True)

    @produto_group.command(name="destaque", description="Marcar/desmarcar produto como destaque (CEO)")
    async def produto_destaque(self, interaction: discord.Interaction, produto_id: int, destaque: bool):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, destaque=int(destaque))
        await interaction.response.send_message(f"⭐ Produto `{produto_id}` destaque = {destaque}.", ephemeral=True)

    @produto_group.command(name="ocultar", description="Ocultar/reexibir um produto no catálogo (CEO)")
    async def produto_ocultar(self, interaction: discord.Interaction, produto_id: int, ocultar: bool):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, oculto=int(ocultar))
        await interaction.response.send_message(f"🙈 Produto `{produto_id}` oculto = {ocultar}.", ephemeral=True)

    @produto_group.command(name="consultar", description="Consultar detalhes de um produto (atendente/CEO)")
    async def produto_consultar(self, interaction: discord.Interaction, produto_id: int):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este comando.", ephemeral=True)
        produto = db.obter_produto(produto_id)
        if not produto:
            return await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        estoque = db.obter_estoque(produto_id)
        texto_estoque = "\n".join(f"{t}: {q}" for t, q in estoque.items()) or "Sem estoque cadastrado."
        campos_publicos = f"👕 **{produto['nome']}** — R$ {produto['preco_venda']:.2f}\n📦 Estoque:\n{texto_estoque}"
        if is_ceo(interaction.user):
            campos_publicos += f"\n💵 Custo: R$ {produto['preco_custo']:.2f}"
        await interaction.response.send_message(campos_publicos, ephemeral=True)

    # ---------------- /estoque ----------------
    @estoque_group.command(name="consultar", description="Consultar estoque de um produto (atendente/CEO)")
    async def estoque_consultar(self, interaction: discord.Interaction, produto_id: int):
        await Admin.produto_consultar.callback(self, interaction, produto_id)

    @estoque_group.command(name="adicionar", description="Adicionar estoque de um tamanho (CEO)")
    async def estoque_adicionar(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.ajustar_estoque(produto_id, tamanho.upper(), quantidade)
        await interaction.response.send_message(f"📦 +{quantidade} no tamanho {tamanho.upper()}.", ephemeral=True)

    @estoque_group.command(name="remover", description="Remover estoque de um tamanho (CEO)")
    async def estoque_remover(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.ajustar_estoque(produto_id, tamanho.upper(), -quantidade)
        await interaction.response.send_message(f"📦 -{quantidade} no tamanho {tamanho.upper()}.", ephemeral=True)

    @estoque_group.command(name="ajustar", description="Definir o estoque exato de um tamanho (CEO)")
    async def estoque_ajustar(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.set_estoque(produto_id, tamanho.upper(), quantidade)
        await interaction.response.send_message(f"📦 Estoque de {tamanho.upper()} ajustado para {quantidade}.", ephemeral=True)

    @estoque_group.command(name="alerta", description="Ver produtos com estoque baixo ou esgotado (CEO)")
    async def estoque_alerta(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        import config

        linhas = []
        for p in db.listar_produtos(apenas_visiveis=False):
            estoque = db.obter_estoque(p["id"])
            for tamanho, qtd in estoque.items():
                if qtd == 0:
                    linhas.append(f"🔴 {p['nome']} ({tamanho}) — ESGOTADO")
                elif qtd <= config.ESTOQUE_BAIXO_LIMITE:
                    linhas.append(f"🟡 {p['nome']} ({tamanho}) — {qtd} restante(s)")
        await interaction.response.send_message("\n".join(linhas) or "✅ Nenhum alerta de estoque.", ephemeral=True)

    # ---------------- /preco e /custo ----------------
    @preco_group.command(name="ver", description="Ver preços de um produto (CEO)")
    async def preco_ver(self, interaction: discord.Interaction, produto_id: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        p = db.obter_produto(produto_id)
        if not p:
            return await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        await interaction.response.send_message(
            f"💰 Venda: R$ {p['preco_venda']:.2f} | 💵 Custo: R$ {p['preco_custo']:.2f} | "
            f"📈 Lucro unitário: R$ {p['preco_venda'] - p['preco_custo']:.2f}",
            ephemeral=True,
        )

    @preco_group.command(name="alterar", description="Alterar o preço de venda de um produto (CEO)")
    async def preco_alterar(self, interaction: discord.Interaction, produto_id: int, novo_preco_venda: float):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, preco_venda=novo_preco_venda)
        await interaction.response.send_message(f"💰 Preço de venda atualizado para R$ {novo_preco_venda:.2f}.", ephemeral=True)

    @custo_group.command(name="alterar", description="Alterar o preço de custo de um produto (CEO)")
    async def custo_alterar(self, interaction: discord.Interaction, produto_id: int, novo_preco_custo: float):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, preco_custo=novo_preco_custo)
        await interaction.response.send_message(f"💵 Preço de custo atualizado para R$ {novo_preco_custo:.2f}.", ephemeral=True)

    # ---------------- /cupom-admin ----------------
    @cupom_group.command(name="criar", description="Criar um cupom de desconto (CEO)")
    async def cupom_criar(
        self, interaction: discord.Interaction, codigo: str, desconto_percentual: float,
        validade: str = "", limite_usos: int = 0, valor_minimo: float = 0,
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.criar_cupom(codigo, desconto_percentual, validade, limite_usos, valor_minimo)
        await interaction.response.send_message(f"🎟️ Cupom **{codigo.upper()}** criado ({desconto_percentual}%).", ephemeral=True)

    @cupom_group.command(name="editar", description="Editar um cupom existente (CEO)")
    async def cupom_editar(
        self, interaction: discord.Interaction, codigo: str, desconto_percentual: float = -1,
        validade: str = "", limite_usos: int = -1, valor_minimo: float = -1,
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        campos = {}
        if desconto_percentual >= 0:
            campos["desconto_percentual"] = desconto_percentual
        if validade:
            campos["validade"] = validade
        if limite_usos >= 0:
            campos["limite_usos"] = limite_usos
        if valor_minimo >= 0:
            campos["valor_minimo"] = valor_minimo
        if not campos:
            return await interaction.response.send_message("Nada para editar.", ephemeral=True)
        db.editar_cupom(codigo, **campos)
        await interaction.response.send_message(f"✅ Cupom **{codigo.upper()}** atualizado.", ephemeral=True)

    @cupom_group.command(name="remover", description="Remover um cupom (CEO)")
    async def cupom_remover(self, interaction: discord.Interaction, codigo: str):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.remover_cupom(codigo)
        await interaction.response.send_message(f"🗑️ Cupom **{codigo.upper()}** removido.", ephemeral=True)

    @cupom_group.command(name="listar", description="Listar todos os cupons (CEO)")
    async def cupom_listar(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        cupons = db.listar_cupons()
        if not cupons:
            return await interaction.response.send_message("Nenhum cupom cadastrado.", ephemeral=True)
        texto = "\n".join(
            f"{c['codigo']} — {c['desconto_percentual']}% — usos {c['usos']}/{c['limite_usos'] or '∞'}" for c in cupons
        )
        await interaction.response.send_message(texto, ephemeral=True)

    # ---------------- /frete ----------------
    @frete_group.command(name="configurar", description="Definir/atualizar o valor de frete para uma região (CEO)")
    async def frete_configurar(self, interaction: discord.Interaction, regiao: str, valor: float):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        existentes = {r["nome_regiao"].lower(): r for r in db.listar_regioes_frete()}
        if regiao.lower() in existentes:
            db.editar_regiao_frete(existentes[regiao.lower()]["id"], valor)
        else:
            db.adicionar_regiao_frete(regiao, valor)
        await interaction.response.send_message(f"🚚 Frete de {regiao} definido como R$ {valor:.2f}.", ephemeral=True)

    @frete_group.command(name="adicionar", description="Adicionar uma nova região de frete (CEO)")
    async def frete_adicionar(self, interaction: discord.Interaction, regiao: str, valor: float):
        await Admin.frete_configurar.callback(self, interaction, regiao, valor)

    @frete_group.command(name="editar", description="Editar o valor de frete de uma região (CEO)")
    async def frete_editar(self, interaction: discord.Interaction, regiao: str, valor: float):
        await Admin.frete_configurar.callback(self, interaction, regiao, valor)

    @frete_group.command(name="remover", description="Remover uma região de frete (CEO)")
    async def frete_remover(self, interaction: discord.Interaction, regiao: str):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        for r in db.listar_regioes_frete():
            if r["nome_regiao"].lower() == regiao.lower():
                db.remover_regiao_frete(r["id"])
                return await interaction.response.send_message(f"🗑️ Região {regiao} removida.", ephemeral=True)
        await interaction.response.send_message("Região não encontrada.", ephemeral=True)

    @frete_group.command(name="regioes", description="Listar todas as regiões de frete configuradas (CEO)")
    async def frete_regioes(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        regioes = db.listar_regioes_frete()
        if not regioes:
            return await interaction.response.send_message("Nenhuma região configurada.", ephemeral=True)
        texto = "\n".join(f"{r['nome_regiao']}: R$ {r['valor']:.2f}" for r in regioes)
        await interaction.response.send_message(texto, ephemeral=True)

    # ---------------- /vendas ----------------
    @app_commands.command(name="vendas", description="Ver relatório de vendas (CEO)")
    @app_commands.choices(
        periodo=[
            app_commands.Choice(name="Hoje", value="hoje"),
            app_commands.Choice(name="7 dias", value="7dias"),
            app_commands.Choice(name="30 dias", value="30dias"),
            app_commands.Choice(name="Total", value="total"),
        ]
    )
    async def vendas(self, interaction: discord.Interaction, periodo: app_commands.Choice[str]):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        pedidos = self._pedidos_por_periodo(periodo.value)
        faturamento = sum(p["valor_total"] for p in pedidos)
        custos = sum(
            (db.obter_produto(p["produto_id"]) or {}).get("preco_custo", 0) * p["quantidade"] for p in pedidos
        )
        lucro = faturamento - custos
        produtos_vendidos = sum(p["quantidade"] for p in pedidos)
        embed = discord.Embed(title=f"📊 Vendas — {periodo.name}", color=discord.Color.green())
        embed.add_field(name="📦 Pedidos", value=str(len(pedidos)))
        embed.add_field(name="💰 Faturamento", value=f"R$ {faturamento:.2f}")
        embed.add_field(name="💵 Custos", value=f"R$ {custos:.2f}")
        embed.add_field(name="📈 Lucro", value=f"R$ {lucro:.2f}")
        embed.add_field(name="👕 Produtos vendidos", value=str(produtos_vendidos))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _pedidos_por_periodo(self, periodo: str):
        agora = datetime.datetime.utcnow()
        if periodo == "hoje":
            desde = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        elif periodo == "7dias":
            desde = agora - datetime.timedelta(days=7)
        elif periodo == "30dias":
            desde = agora - datetime.timedelta(days=30)
        else:
            desde = None
        return db.vendas_periodo(desde.isoformat() if desde else None)

    # ---------------- /dashboard ----------------
    @app_commands.command(name="dashboard", description="Ver o dashboard geral da loja (CEO)")
    async def dashboard(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        pedidos = self._pedidos_por_periodo("total")
        faturamento = sum(p["valor_total"] for p in pedidos)
        custos = sum(
            (db.obter_produto(p["produto_id"]) or {}).get("preco_custo", 0) * p["quantidade"] for p in pedidos
        )
        lucro = faturamento - custos
        pendentes = len(db.buscar_pedidos(status="aguardando_pagamento")) + len(db.buscar_pedidos(status="comprovante_enviado"))

        contagem_produtos = {}
        for p in pedidos:
            contagem_produtos[p["produto_nome"]] = contagem_produtos.get(p["produto_nome"], 0) + p["quantidade"]
        mais_vendido = max(contagem_produtos, key=contagem_produtos.get) if contagem_produtos else "-"

        esgotados = []
        for prod in db.listar_produtos(apenas_visiveis=False):
            estoque = db.obter_estoque(prod["id"])
            if estoque and all(q == 0 for q in estoque.values()):
                esgotados.append(prod["nome"])

        embed = discord.Embed(title="📊 Dashboard da loja", color=discord.Color.blurple())
        embed.add_field(name="💰 Faturamento", value=f"R$ {faturamento:.2f}")
        embed.add_field(name="📈 Lucro", value=f"R$ {lucro:.2f}")
        embed.add_field(name="📦 Pedidos", value=str(len(pedidos)))
        embed.add_field(name="👕 Produtos vendidos", value=str(sum(contagem_produtos.values())))
        embed.add_field(name="🔴 Produtos esgotados", value=", ".join(esgotados) or "Nenhum")
        embed.add_field(name="🟡 Pagamentos pendentes", value=str(pendentes))
        embed.add_field(name="🏆 Produto mais vendido", value=mais_vendido)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
