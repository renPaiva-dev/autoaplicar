import json
import sqlite3
from datetime import datetime

from .config import DADOS
from .fontes.base import Vaga

# Ciclo de vida: nova -> avaliada -> aprovada/rejeitada -> aplicada/pulada/erro
ESQUEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id TEXT PRIMARY KEY,
    fonte TEXT, titulo TEXT, empresa TEXT, local TEXT,
    url TEXT, url_aplicar TEXT, descricao TEXT,
    nota INTEGER, analise TEXT,
    status TEXT DEFAULT 'nova',
    obs TEXT,
    criado_em TEXT, atualizado_em TEXT
)
"""


class Banco:
    def __init__(self, caminho=DADOS / "vagas.db"):
        DADOS.mkdir(exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.row_factory = sqlite3.Row
        self.con.execute(ESQUEMA)

    def existe(self, vaga_id: str) -> bool:
        return self.con.execute("SELECT 1 FROM vagas WHERE id=?", (vaga_id,)).fetchone() is not None

    def inserir(self, v: Vaga):
        agora = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT OR IGNORE INTO vagas (id, fonte, titulo, empresa, local, url, url_aplicar,"
            " descricao, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (v.id, v.fonte, v.titulo, v.empresa, v.local, v.url, v.url_aplicar or v.url,
             v.descricao, agora, agora),
        )
        self.con.commit()

    def avaliar(self, vaga_id: str, nota: int, analise: dict):
        self._update(vaga_id, nota=nota, analise=json.dumps(analise, ensure_ascii=False),
                     status="avaliada")

    def status(self, vaga_id: str, status: str, obs: str | None = None):
        self._update(vaga_id, status=status, obs=obs)

    def _update(self, vaga_id: str, **campos):
        campos["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        sets = ", ".join(f"{k}=?" for k in campos)
        self.con.execute(f"UPDATE vagas SET {sets} WHERE id=?", (*campos.values(), vaga_id))
        self.con.commit()

    def listar(self, status: str | None = None, nota_minima: int | None = None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM vagas WHERE 1=1", []
        if status:
            sql += " AND status=?"
            args.append(status)
        if nota_minima is not None:
            sql += " AND nota>=?"
            args.append(nota_minima)
        return self.con.execute(sql + " ORDER BY nota DESC, criado_em DESC", args).fetchall()

    def obter(self, vaga_id: str) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM vagas WHERE id=?", (vaga_id,)).fetchone()
