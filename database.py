"""
Camada de acesso a dados (SQLite).
Usa sqlite3 puro (sem ORM) para manter o projeto simples de rodar no Railway.
"""

import sqlite3
import datetime
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT DEFAULT '',
    preco_venda REAL NOT NULL,
    preco_custo REAL NOT NULL DEFAULT 0,
    permite_personalizacao INTEGER NOT NULL DEFAULT 0,
    destaque INTEGER NOT NULL DEFAULT 0,
    oculto INTEGER NOT NULL DEFAULT 0,
    imagem_url TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS estoque (
    produto_id INTEGER NOT NULL,
    tamanho TEXT NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (produto_id, tamanho),
    FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id TEXT PRIMARY KEY,
    cliente_id INTEGER NOT NULL,
    cliente_tag TEXT,
    produto_id INTEGER,
    produto_nome TEXT,
    tamanho TEXT,
    quantidade INTEGER,
    personalizacao_nome TEXT,
    personalizacao_numero TEXT,
    nome_completo TEXT,
    endereco TEXT,
    numero TEXT,
    complemento TEXT,
    cidade TEXT,
    estado TEXT,
    pais TEXT,
    cep TEXT,
    telefone TEXT,
    cpf TEXT,
    email TEXT,
    cupom_codigo TEXT,
    desconto REAL DEFAULT 0,
    frete REAL DEFAULT 0,
    valor_total REAL DEFAULT 0,
    status TEXT DEFAULT 'aguardando_pagamento',
    comprovante_url TEXT,
    rastreio TEXT,
    atendente_id INTEGER,
    ticket_channel_id INTEGER,
    observacoes TEXT DEFAULT '',
    criado_em TEXT
);

CREATE TABLE IF NOT EXISTS cupons (
    codigo TEXT PRIMARY KEY,
    desconto_percentual REAL NOT NULL,
    validade TEXT,
    limite_usos INTEGER DEFAULT 0,
    usos INTEGER DEFAULT 0,
    valor_minimo REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS frete_regioes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_regiao TEXT NOT NULL,
    valor REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS contadores (
    nome TEXT PRIMARY KEY,
    valor INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    pedido_id TEXT,
    categoria TEXT,
    cliente_id INTEGER,
    atendente_id INTEGER,
    status TEXT DEFAULT 'aberto',
    criado_em TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ------------------------------------------------------------------
# Produtos / estoque
# ------------------------------------------------------------------
def criar_produto(nome, descricao, preco_venda, preco_custo, permite_personalizacao, imagem_url=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO produtos (nome, descricao, preco_venda, preco_custo, permite_personalizacao, imagem_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nome, descricao, preco_venda, preco_custo, int(permite_personalizacao), imagem_url),
        )
        return cur.lastrowid


def listar_produtos(apenas_visiveis=True):
    with get_conn() as conn:
        if apenas_visiveis:
            rows = conn.execute("SELECT * FROM produtos WHERE oculto = 0").fetchall()
        else:
            rows = conn.execute("SELECT * FROM produtos").fetchall()
        return [dict(r) for r in rows]


def obter_produto(produto_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()
        return dict(row) if row else None


def editar_produto(produto_id, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{k} = ?" for k in campos)
    valores = list(campos.values()) + [produto_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE produtos SET {colunas} WHERE id = ?", valores)


def remover_produto(produto_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
        conn.execute("DELETE FROM estoque WHERE produto_id = ?", (produto_id,))


def set_estoque(produto_id, tamanho, quantidade):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO estoque (produto_id, tamanho, quantidade) VALUES (?, ?, ?) "
            "ON CONFLICT(produto_id, tamanho) DO UPDATE SET quantidade = ?",
            (produto_id, tamanho, quantidade, quantidade),
        )


def ajustar_estoque(produto_id, tamanho, delta):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO estoque (produto_id, tamanho, quantidade) VALUES (?, ?, MAX(0, ?)) "
            "ON CONFLICT(produto_id, tamanho) DO UPDATE SET quantidade = MAX(0, quantidade + ?)",
            (produto_id, tamanho, delta, delta),
        )


def obter_estoque(produto_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tamanho, quantidade FROM estoque WHERE produto_id = ? ORDER BY tamanho", (produto_id,)
        ).fetchall()
        return {r["tamanho"]: r["quantidade"] for r in rows}


def tamanhos_disponiveis(produto_id):
    return {t: q for t, q in obter_estoque(produto_id).items() if q > 0}


# ------------------------------------------------------------------
# Pedidos
# ------------------------------------------------------------------
def _proximo_numero_pedido():
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO contadores (nome, valor) VALUES ('pedido', 1) "
            "ON CONFLICT(nome) DO UPDATE SET valor = valor + 1"
        )
        row = conn.execute("SELECT valor FROM contadores WHERE nome = 'pedido'").fetchone()
        return row["valor"]


def gerar_id_pedido():
    numero = _proximo_numero_pedido()
    return f"PED-{numero:05d}"


def criar_pedido(dados: dict):
    dados = dict(dados)
    dados["id"] = gerar_id_pedido()
    dados.setdefault("status", "aguardando_pagamento")
    dados["criado_em"] = datetime.datetime.utcnow().isoformat()
    colunas = ", ".join(dados.keys())
    placeholders = ", ".join("?" for _ in dados)
    with get_conn() as conn:
        conn.execute(f"INSERT INTO pedidos ({colunas}) VALUES ({placeholders})", list(dados.values()))
    return dados["id"]


def obter_pedido(pedido_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
        return dict(row) if row else None


def pedidos_do_cliente(cliente_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pedidos WHERE cliente_id = ? ORDER BY criado_em DESC", (cliente_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def atualizar_pedido(pedido_id, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{k} = ?" for k in campos)
    valores = list(campos.values()) + [pedido_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE pedidos SET {colunas} WHERE id = ?", valores)


def buscar_pedidos(status=None, limite=50):
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM pedidos WHERE status = ? ORDER BY criado_em DESC LIMIT ?", (status, limite)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pedidos ORDER BY criado_em DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]


def vendas_periodo(desde_iso=None):
    with get_conn() as conn:
        if desde_iso:
            rows = conn.execute(
                "SELECT * FROM pedidos WHERE criado_em >= ? AND status != 'cancelado'", (desde_iso,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pedidos WHERE status != 'cancelado'").fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Cupons
# ------------------------------------------------------------------
def criar_cupom(codigo, desconto_percentual, validade, limite_usos, valor_minimo):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cupons (codigo, desconto_percentual, validade, limite_usos, valor_minimo) "
            "VALUES (?, ?, ?, ?, ?)",
            (codigo.upper(), desconto_percentual, validade, limite_usos, valor_minimo),
        )


def obter_cupom(codigo):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cupons WHERE codigo = ?", (codigo.upper(),)).fetchone()
        return dict(row) if row else None


def listar_cupons():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cupons").fetchall()
        return [dict(r) for r in rows]


def editar_cupom(codigo, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{k} = ?" for k in campos)
    valores = list(campos.values()) + [codigo.upper()]
    with get_conn() as conn:
        conn.execute(f"UPDATE cupons SET {colunas} WHERE codigo = ?", valores)


def remover_cupom(codigo):
    with get_conn() as conn:
        conn.execute("DELETE FROM cupons WHERE codigo = ?", (codigo.upper(),))


def incrementar_uso_cupom(codigo):
    with get_conn() as conn:
        conn.execute("UPDATE cupons SET usos = usos + 1 WHERE codigo = ?", (codigo.upper(),))


# ------------------------------------------------------------------
# Frete
# ------------------------------------------------------------------
def adicionar_regiao_frete(nome_regiao, valor):
    with get_conn() as conn:
        conn.execute("INSERT INTO frete_regioes (nome_regiao, valor) VALUES (?, ?)", (nome_regiao, valor))


def listar_regioes_frete():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM frete_regioes ORDER BY nome_regiao").fetchall()
        return [dict(r) for r in rows]


def editar_regiao_frete(regiao_id, valor):
    with get_conn() as conn:
        conn.execute("UPDATE frete_regioes SET valor = ? WHERE id = ?", (valor, regiao_id))


def remover_regiao_frete(regiao_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM frete_regioes WHERE id = ?", (regiao_id,))


def valor_frete_para_estado(estado):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT valor FROM frete_regioes WHERE lower(nome_regiao) = lower(?)", (estado,)
        ).fetchone()
        return row["valor"] if row else None


# ------------------------------------------------------------------
# Tickets
# ------------------------------------------------------------------
def criar_ticket(channel_id, pedido_id, categoria, cliente_id):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tickets (channel_id, pedido_id, categoria, cliente_id, status, criado_em) "
            "VALUES (?, ?, ?, ?, 'aberto', ?)",
            (channel_id, pedido_id, categoria, cliente_id, datetime.datetime.utcnow().isoformat()),
        )


def obter_ticket(channel_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)).fetchone()
        return dict(row) if row else None


def atualizar_ticket(channel_id, **campos):
    if not campos:
        return
    colunas = ", ".join(f"{k} = ?" for k in campos)
    valores = list(campos.values()) + [channel_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE tickets SET {colunas} WHERE channel_id = ?", valores)
