"""Fluxo de candidatura: abre a vaga, clica em candidatar, preenche etapa por etapa
e SÓ envia depois da sua confirmação no terminal."""

import json

from playwright.sync_api import BrowserContext, Page
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from ..config import DADOS
from ..ia import IA, texto_vaga
from ..navegador import pagina, pausa
from . import formulario as f

console = Console()
ARQ_RESPOSTAS = DADOS / "respostas.json"
MAX_ETAPAS = 15


def carregar_respostas() -> dict:
    if ARQ_RESPOSTAS.exists():
        return json.loads(ARQ_RESPOSTAS.read_text(encoding="utf-8"))
    return {}


def salvar_resposta(salvas: dict, rotulo: str, valor: str):
    salvas[rotulo] = valor
    ARQ_RESPOSTAS.write_text(json.dumps(salvas, ensure_ascii=False, indent=1), encoding="utf-8")


def _clicar(ctx: BrowserContext, page: Page, botao_id: str) -> Page:
    """Clica e, se abrir aba nova, passa a usar ela."""
    antes = len(ctx.pages)
    page.locator(f'[data-aab="{botao_id}"]').first.click()
    page.wait_for_timeout(2500)
    if len(ctx.pages) > antes:
        nova = ctx.pages[-1]
        nova.wait_for_load_state()
        return nova
    return page


def _sucesso(page: Page) -> bool:
    try:
        t = f.normalizar(page.locator("body").inner_text(timeout=5000))
    except Exception:
        return False
    return any(s in t for s in f.TEXTO_SUCESSO)


def _perguntar_usuario(campo: dict, sugestao: str, salvas: dict) -> str:
    console.print(f"\n[yellow]?[/] [bold]{campo['rotulo']}[/]" + ("  [red](obrigatório)[/]" if campo["obrigatorio"] else ""))
    if campo.get("opcoes"):
        for i, o in enumerate(campo["opcoes"], 1):
            console.print(f"   {i}. {o}")
    valor = Prompt.ask("  Resposta (número da opção; várias: 1,3; Enter = preencher no navegador)", default=sugestao or "")
    opcoes = campo.get("opcoes") or []
    numeros = [n.strip() for n in valor.split(",")]
    if opcoes and all(n.isdigit() and 1 <= int(n) <= len(opcoes) for n in numeros):
        valor = " | ".join(opcoes[int(n) - 1] for n in numeros)
    if valor and campo["tipo"] != "file":
        salvar_resposta(salvas, campo["rotulo"], valor)
    return valor


PALAVRAS_EN = {"the", "and", "you", "with", "experience", "will", "our", "for", "are", "team", "skills", "work"}
PALAVRAS_PT = {"para", "com", "você", "experiência", "vaga", "empresa", "conhecimento", "atividades", "desejável"}


def idioma_vaga(row) -> str:
    """Idioma informado pela IA na avaliação; para vagas antigas, contagem de palavras comuns."""
    analise = json.loads(row["analise"] or "{}") if "analise" in row.keys() else {}
    if analise.get("idioma"):
        return analise["idioma"]
    palavras = (row["descricao"] or "").lower().split()
    en = sum(w in PALAVRAS_EN for w in palavras)
    pt = sum(w in PALAVRAS_PT for w in palavras)
    return "en" if en > pt * 2 else "pt"


def escolher_curriculo(row, cfg: dict):
    if idioma_vaga(row) == "en":
        if cfg.get("curriculo_pdf_en") and cfg["curriculo_pdf_en"].exists():
            return cfg["curriculo_pdf_en"]
        console.print("[yellow]Vaga em inglês, mas 'curriculo_pdf_en' não está configurado: "
                      "vou anexar o currículo em português.[/]")
    return cfg["curriculo_pdf"]


def _preencher_etapa(page: Page, campos: list[dict], row, ia: IA, cfg: dict, salvas: dict) -> None:
    para_ia = [{k: c(k) for k in ("campo_id", "tipo", "rotulo", "nome", "opcoes", "obrigatorio", "valor_atual") if k in c}
               for c in campos]
    with console.status(f"IA preenchendo {len(campos)} campo(s)..."):
        respostas = {r.campo_id: r for r in ia.responder_formulario(texto_vaga(row), para_ia, salvas).respostas}

    tabela = Table("Campo", "Valor", "Origem", show_lines=False, title="Preenchido nesta etapa")
    for c in campos:
        r = respostas.get(c["campo_id"])
        if r is None or r.origem == "manter":
            continue
        valor = r.valor
        if r.origem == "perguntar":
            if not c["obrigatorio"] and c["tipo"] in ("checkbox", "checkboxes", "file"):
                continue
            valor = _perguntar_usuario(c, "", salvas)
            if not valor:
                continue
        erro = f.preencher(page, c, valor, cfg["curriculo_atual"])
        pausa(cfg, 0.2)
        exibido = valor if len(valor) < 90 else valor[:87] + "..."
        tabela.add_row(c["rotulo"][:60], exibido, r.origem if not erro else f"[red]ERRO: {erro}[/]")
    if tabela.row_count:
        console.print(tabela)


def aplicar(ctx: BrowserContext, row, ia: IA, cfg: dict, salvas: dict) -> tuple[str, str]:
    """Retorna (status, observação). status: aplicada | pulada | erro."""
    cfg["curriculo_atual"] = escolher_curriculo(row, cfg)
    console.print(f"Currículo anexado: [bold]{cfg['curriculo_atual'].name}[/]")
    page = pagina(ctx)
    page.goto(row["url_aplicar"] or row["url"])
    pausa(cfg)

    # 1) Botão "Candidatar" (no LinkedIn: "Candidatura simplificada", que abre um modal)
    dados = f.extrair(page, None)
    botao = f.achar_botao(dados["botoes"], f.TEXTO_CANDIDATAR)
    raiz = None
    if row["fonte"] == "linkedin":
        if not botao:
            return "erro", "botão Candidatura simplificada não encontrado (vaga fechada ou já aplicada?)"
        raiz = '[role="dialog"]'
    if botao:
        page = _clicar(ctx, page, botao["id"])
        pausa(cfg)

    feitos: set[str] = set()
    impressao_anterior = None
    for _ in range(MAX_ETAPAS):
        dados = f.extrair(page, raiz, feitos)

        if dados["login"]:
            op = Prompt.ask("[yellow]O site pediu login/cadastro.[/] Faça no navegador, chegue ao formulário "
                            "e aperte Enter  (p = pular vaga)", default="")
            if op.lower() == "p":
                return "pulada", "login necessário"
            continue

        novos = [c for c in dados["campos"] if c["campo_id"] not in feitos]
        if novos:
            _preencher_etapa(page, novos, row, ia, cfg, salvas)
            feitos.update(c["campo_id"] for c in novos)

        enviar = f.achar_botao(dados["botoes"], f.TEXTO_ENVIAR)
        proximo = f.achar_botao(dados["botoes"], f.TEXTO_PROXIMO)

        if enviar:
            console.print(f"\n[bold green]Pronto para enviar[/] (botão: “{enviar['texto']}”). "
                          "Confira o formulário no navegador; pode corrigir o que quiser lá.")
            op = Prompt.ask("(s) enviar  (m) eu enviei manualmente  (p) pular vaga", choices=["s", "m", "p"],
                            default="p")
            if op == "p":
                return "pulada", "pulada na revisão"
            if op == "m":
                return "aplicada", "enviada manualmente"
            page = _clicar(ctx, page, enviar["id"])
            page.wait_for_timeout(3000)
            if _sucesso(page):
                return "aplicada", ""
            depois = f.extrair(page, raiz, feitos)
            if f.achar_botao(depois["botoes"], f.TEXTO_ENVIAR) and depois["erros"]:
                console.print(f"[red]O site apontou problemas:[/] {depois['erros']}")
                continue  # volta ao loop: você corrige no navegador e confirma de novo
            ok = Prompt.ask("Não vi a confirmação na página. A candidatura foi enviada?", choices=["s", "n"],
                            default="s")
            return ("aplicada", "") if ok == "s" else ("erro", "envio não confirmado")

        impressao = (page.url, tuple(sorted(c["rotulo"] for c in dados["campos"])))
        if proximo and impressao != impressao_anterior:
            impressao_anterior = impressao
            page = _clicar(ctx, page, proximo["id"])
            pausa(cfg, 0.5)
            continue

        # Travado: sem botão reconhecido, ou "próximo" não avançou (campo inválido, captcha, etc.)
        if dados["erros"]:
            console.print(f"[red]Mensagens na página:[/] {dados['erros']}")
        op = Prompt.ask("[yellow]Não consegui avançar sozinho.[/] Resolva no navegador (campo faltando, captcha, "
                        "etapa diferente) e aperte Enter  (m) já enviei  (p) pular", default="")
        if op.lower() == "p":
            return "pulada", "travou no formulário"
        if op.lower() == "m":
            return "aplicada", "enviada manualmente"
        impressao_anterior = None
    return "erro", f"mais de {MAX_ETAPAS} etapas"
