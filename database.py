import sqlite3
import bcrypt
from datetime import datetime, timedelta


DB_NAME = "reclamacoes_frutas.db"


def conectar():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL,
        perfil TEXT NOT NULL,
        ativo INTEGER DEFAULT 1,
        data_criacao TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_empresa TEXT NOT NULL,
        cif_nif TEXT,
        nome_contato TEXT,
        email TEXT,
        telefone TEXT,
        cidade TEXT,
        pais TEXT,
        ativo INTEGER DEFAULT 1,
        data_criacao TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_lote TEXT UNIQUE NOT NULL,
        produto TEXT NOT NULL,
        variedade TEXT,
        finca TEXT,
        data_colheita TEXT,
        data_confeccao TEXT,
        camara_fria TEXT,
        temperatura_saida TEXT,
        observacoes TEXT,
        data_criacao TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reclamacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_reclamacao TEXT UNIQUE NOT NULL,
        cliente_id INTEGER,
        nome_cliente TEXT,
        email_cliente TEXT,
        telefone_cliente TEXT,
        numero_pedido TEXT,
        numero_albaran TEXT,
        codigo_lote TEXT,
        produto TEXT,
        variedade TEXT,
        data_entrega TEXT,
        tipo_reclamacao TEXT,
        categoria TEXT,
        gravidade TEXT,
        descricao TEXT,
        quantidade_afetada TEXT,
        solucao_desejada TEXT,
        status TEXT,
        setor_responsavel TEXT,
        prazo_resposta TEXT,
        data_abertura TEXT NOT NULL,
        data_fechamento TEXT,
        satisfacao_cliente INTEGER,
        observacoes TEXT,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reclamacao_id INTEGER NOT NULL,
        status_anterior TEXT,
        status_novo TEXT NOT NULL,
        comentario TEXT,
        usuario TEXT,
        data_alteracao TEXT NOT NULL,
        FOREIGN KEY(reclamacao_id) REFERENCES reclamacoes(id)
    )
    """)

    conn.commit()
    conn.close()


def gerar_hash_senha(senha):
    senha_bytes = senha.encode("utf-8")
    hash_bytes = bcrypt.hashpw(senha_bytes, bcrypt.gensalt())
    return hash_bytes.decode("utf-8")


def verificar_senha(senha, senha_hash):
    return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8"))


def criar_usuario_admin_padrao():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM usuarios WHERE email = ?", ("admin@admin.com",))
    existe = cursor.fetchone()

    if not existe:
        senha_hash = gerar_hash_senha("admin123")
        cursor.execute("""
        INSERT INTO usuarios (nome, email, senha_hash, perfil, ativo, data_criacao)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Administrador",
            "admin@admin.com",
            senha_hash,
            "admin",
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    conn.commit()
    conn.close()


def autenticar_usuario(email, senha):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, nome, email, senha_hash, perfil 
    FROM usuarios 
    WHERE email = ? AND ativo = 1
    """, (email,))

    usuario = cursor.fetchone()
    conn.close()

    if usuario:
        id_usuario, nome, email, senha_hash, perfil = usuario

        if verificar_senha(senha, senha_hash):
            return {
                "id": id_usuario,
                "nome": nome,
                "email": email,
                "perfil": perfil
            }

    return None


def inserir_cliente(nome_empresa, cif_nif, nome_contato, email, telefone, cidade, pais):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO clientes (
        nome_empresa, cif_nif, nome_contato, email, telefone, cidade, pais, ativo, data_criacao
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nome_empresa,
        cif_nif,
        nome_contato,
        email,
        telefone,
        cidade,
        pais,
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def listar_clientes():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, nome_empresa, cif_nif, nome_contato, email, telefone, cidade, pais
    FROM clientes
    WHERE ativo = 1
    ORDER BY nome_empresa
    """)

    dados = cursor.fetchall()
    conn.close()
    return dados


def inserir_lote(codigo_lote, produto, variedade, finca, data_colheita, data_confeccao, camara_fria, temperatura_saida, observacoes):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO lotes (
        codigo_lote, produto, variedade, finca, data_colheita, data_confeccao,
        camara_fria, temperatura_saida, observacoes, data_criacao
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        codigo_lote,
        produto,
        variedade,
        finca,
        str(data_colheita) if data_colheita else "",
        str(data_confeccao) if data_confeccao else "",
        camara_fria,
        temperatura_saida,
        observacoes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def listar_lotes():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, codigo_lote, produto, variedade, finca, data_colheita, data_confeccao, camara_fria
    FROM lotes
    ORDER BY data_criacao DESC
    """)

    dados = cursor.fetchall()
    conn.close()
    return dados


def gerar_codigo_reclamacao():
    conn = conectar()
    cursor = conn.cursor()

    ano = datetime.now().year

    cursor.execute("""
    SELECT COUNT(*) FROM reclamacoes
    WHERE codigo_reclamacao LIKE ?
    """, (f"REC-{ano}-%",))

    total = cursor.fetchone()[0] + 1
    conn.close()

    return f"REC-{ano}-{total:04d}"


def classificar_categoria(tipo_reclamacao):
    produto = [
        "Fruta podrida",
        "Fruta blanda",
        "Falta de color",
        "Calibre irregular",
        "Daño mecánico"
    ]

    logistica = [
        "Retraso en entrega",
        "Carga incompleta",
        "Rotura cadena de frío"
    ]

    administrativa = [
        "Error de facturación",
        "Error de etiquetado"
    ]

    atendimento = [
        "Mal servicio"
    ]

    if tipo_reclamacao in produto:
        return "Produto"
    elif tipo_reclamacao in logistica:
        return "Logística"
    elif tipo_reclamacao in administrativa:
        return "Administrativa"
    elif tipo_reclamacao in atendimento:
        return "Atendimento"
    else:
        return "Comercial"


def classificar_gravidade(tipo_reclamacao):
    alta = [
        "Fruta podrida",
        "Rotura cadena de frío",
        "Carga incompleta",
        "Retraso en entrega"
    ]

    media = [
        "Fruta blanda",
        "Daño mecánico",
        "Error de facturación",
        "Error de etiquetado",
        "Calibre irregular"
    ]

    if tipo_reclamacao in alta:
        return "Alta"
    elif tipo_reclamacao in media:
        return "Média"
    else:
        return "Baixa"


def definir_setor_responsavel(categoria):
    if categoria == "Produto":
        return "Qualidade"
    elif categoria == "Logística":
        return "Logística"
    elif categoria == "Administrativa":
        return "Administração"
    elif categoria == "Atendimento":
        return "Atendimento"
    else:
        return "Comercial"


def definir_prazo_resposta(gravidade):
    agora = datetime.now()

    if gravidade == "Alta":
        prazo = agora + timedelta(hours=24)
    elif gravidade == "Média":
        prazo = agora + timedelta(hours=48)
    else:
        prazo = agora + timedelta(hours=72)

    return prazo.strftime("%Y-%m-%d %H:%M:%S")


def inserir_reclamacao(
    cliente_id,
    nome_cliente,
    email_cliente,
    telefone_cliente,
    numero_pedido,
    numero_albaran,
    codigo_lote,
    produto,
    variedade,
    data_entrega,
    tipo_reclamacao,
    descricao,
    quantidade_afetada,
    solucao_desejada
):
    codigo_reclamacao = gerar_codigo_reclamacao()
    categoria = classificar_categoria(tipo_reclamacao)
    gravidade = classificar_gravidade(tipo_reclamacao)
    setor_responsavel = definir_setor_responsavel(categoria)
    prazo_resposta = definir_prazo_resposta(gravidade)
    status = "Nova"
    data_abertura = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO reclamacoes (
        codigo_reclamacao, cliente_id, nome_cliente, email_cliente, telefone_cliente,
        numero_pedido, numero_albaran, codigo_lote, produto, variedade, data_entrega,
        tipo_reclamacao, categoria, gravidade, descricao, quantidade_afetada,
        solucao_desejada, status, setor_responsavel, prazo_resposta, data_abertura
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        codigo_reclamacao,
        cliente_id,
        nome_cliente,
        email_cliente,
        telefone_cliente,
        numero_pedido,
        numero_albaran,
        codigo_lote,
        produto,
        variedade,
        str(data_entrega) if data_entrega else "",
        tipo_reclamacao,
        categoria,
        gravidade,
        descricao,
        quantidade_afetada,
        solucao_desejada,
        status,
        setor_responsavel,
        prazo_resposta,
        data_abertura
    ))

    reclamacao_id = cursor.lastrowid

    cursor.execute("""
    INSERT INTO historico_status (
        reclamacao_id, status_anterior, status_novo, comentario, usuario, data_alteracao
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        reclamacao_id,
        "",
        "Nova",
        "Reclamação criada no sistema",
        "Sistema",
        data_abertura
    ))

    conn.commit()
    conn.close()

    return codigo_reclamacao


def listar_reclamacoes():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        id,
        codigo_reclamacao,
        nome_cliente,
        produto,
        variedade,
        tipo_reclamacao,
        categoria,
        gravidade,
        status,
        setor_responsavel,
        data_abertura,
        prazo_resposta
    FROM reclamacoes
    ORDER BY data_abertura DESC
    """)

    dados = cursor.fetchall()
    conn.close()
    return dados


def buscar_reclamacao_por_id(reclamacao_id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM reclamacoes
    WHERE id = ?
    """, (reclamacao_id,))

    dados = cursor.fetchone()
    conn.close()
    return dados


def atualizar_status_reclamacao(reclamacao_id, novo_status, comentario, usuario):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT status FROM reclamacoes WHERE id = ?", (reclamacao_id,))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        return False

    status_anterior = resultado[0]

    data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data_fechamento = None
    if novo_status in ["Fechada", "Resolvida", "Cancelada", "Improcedente"]:
        data_fechamento = data_agora

    cursor.execute("""
    UPDATE reclamacoes
    SET status = ?, data_fechamento = COALESCE(?, data_fechamento)
    WHERE id = ?
    """, (novo_status, data_fechamento, reclamacao_id))

    cursor.execute("""
    INSERT INTO historico_status (
        reclamacao_id, status_anterior, status_novo, comentario, usuario, data_alteracao
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        reclamacao_id,
        status_anterior,
        novo_status,
        comentario,
        usuario,
        data_agora
    ))

    conn.commit()
    conn.close()

    return True


def obter_indicadores_dashboard():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM reclamacoes")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reclamacoes WHERE status NOT IN ('Fechada', 'Resolvida', 'Cancelada', 'Improcedente')")
    abertas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reclamacoes WHERE status IN ('Fechada', 'Resolvida')")
    resolvidas = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reclamacoes WHERE gravidade = 'Alta'")
    alta = cursor.fetchone()[0]

    conn.close()

    return {
        "total": total,
        "abertas": abertas,
        "resolvidas": resolvidas,
        "alta": alta
    }