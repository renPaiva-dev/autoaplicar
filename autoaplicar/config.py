from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"


def _caminho(p: str | Path) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else RAIZ / p


def carregar(caminho: str | Path = RAIZ / "config.yaml") -> dict:
    caminho = Path(caminho)
    if not caminho.exists():
        raise SystemExit(
            f"Arquivo {caminho.name} não encontrado. Rode: cp config.example.yaml config.yaml"
        )
    cfg = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    cfg["curriculo_pdf"] = _caminho(cfg.get("curriculo_pdf") or "curriculo.pdf")
    # opcional: versão em inglês, usada no upload quando a vaga for em inglês
    cfg["curriculo_pdf_en"] = _caminho(cfg["curriculo_pdf_en"]) if cfg.get("curriculo_pdf_en") else None
    cfg.setdefault("busca", {})
    cfg.setdefault("fontes", {})
    cfg.setdefault("respostas_padrao", {})
    cfg.setdefault("nota_minima", 65)
    cfg.setdefault("limite_aplicacoes", 10)
    cfg.setdefault("pausa", [1.5, 4.0])
    DADOS.mkdir(exist_ok=True)
    return cfg
#a