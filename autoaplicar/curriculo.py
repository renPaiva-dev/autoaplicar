import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from .config import DADOS
from .ia import IA, Perfil


def ler_pdf(caminho: Path) -> str:
    if not caminho.exists():
        raise SystemExit(f"Currículo não encontrado: {caminho}  (ajuste 'curriculo_pdf' no config.yaml)")
    texto = "\n".join((p.extract_text() or "") for p in PdfReader(caminho).pages).strip()
    if len(texto) < 200:
        raise SystemExit(
            "Extraí pouquíssimo texto do PDF. Ele provavelmente é uma imagem escaneada; "
            "exporte o currículo como PDF com texto selecionável."
        )
    return texto


def perfil(caminho: Path, ia: IA) -> Perfil:
    """Extrai o perfil com IA, com cache por hash do PDF (só refaz se o arquivo mudar)."""
    h = hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]
    cache = DADOS / "perfil.json"
    if cache.exists():
        dados = json.loads(cache.read_text(encoding="utf-8"))
        if dados.get("hash") == h:
            return Perfil.model_validate(dados["perfil"])
    p = ia.extrair_perfil()
    cache.write_text(json.dumps({"hash": h, "perfil": p.model_dump()}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return p
