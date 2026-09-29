import html
import re
from dataclasses import dataclass


@dataclass
class Vaga:
    fonte: str
    id_externo: str
    titulo: str
    empresa: str
    local: str
    url: str
    descricao: str
    url_aplicar: str = ""

    @property
    def id(self) -> str:
        return f"{self.fonte}:{self.id_externo}"


def html_para_texto(conteudo: str) -> str:
    conteudo = html.unescape(conteudo or "")
    conteudo = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", conteudo, flags=re.I)
    conteudo = re.sub(r"<[^>]+>", "", conteudo)
    conteudo = html.unescape(conteudo)
    return re.sub(r"\n\s*\n+", "\n\n", conteudo).strip()


def titulo_excluido(titulo: str, excluir: list[str]) -> bool:
    t = titulo.lower()
    return any(p.lower() in t for p in excluir)
