"""Candidatura automática a vagas com base no seu currículo.

Fluxo:  perfil → login → buscar → revisar → aplicar
"""

import argparse
import json

import anthropic
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from autoaplicar import config, curriculo, navegador
from autoaplicar.db import Banco
from autoaplicar.fontes import apis, sites
from autoaplicar.fontes.base import titulo_excluido
from autoaplicar.ia import IA, texto_vaga

console = Console()
FONTES_API = ("gupy", "greenhouse", "lever")
FONTES_NAVEGADOR = ("linkedin", "indeed")


def preparar():
    cfg = config.carregar()
    texto_cv = curriculo.ler_pdf(cfg["curriculo_pdf"])
    return cfg, texto_cv, IA(texto_cv, cfg["respostas_padrao"])


def cmd_perfil(_args):
    cfg, _, ia = preparar()
    with console.status("Lendo currículo com IA..."):
        p = curriculo.perfil(cfg["curriculo_pdf"], ia)
    console.print_json(json.dumps(p.model_dump(), ensure_ascii=False))
    console.print("[dim]Se algo estiver errado, corrija o PDF: a IA usa o texto do currículo em todas as respostas.[/]")


def cmd_login(_args):
    config.carregar()
    with navegador.abrir() as ctx:
        navegador.fazer_login(ctx)


def coletar(cfg: dict, escolhidas: set[str]) -> list:
    busca, fontes = cfg["busca"], cfg["fontes"]
    vagas = []

    def rodar(nome, fn, ativa=None):
        if nome not in escolhidas or not (fontes.get(nome) if ativa is None else ativa):
            return
        with console.status(f"Buscando em {nome}..."):
            try:
                achadas = fn()
            except Exception as e:  # noqa: BLE001 - uma fonte quebrada não derruba as outras
                console.print(f"  [red]{nome}: {e}[/]")
                return
        console.print(f"  {nome}: {len(achadas)} vaga(s)")
        vagas.extend(achadas)

    rodar("gupy", lambda: apis.gupy(busca))
    rodar("greenhouse", lambda: apis.greenhouse(busca, fontes["greenhouse"]))
    rodar("lever", lambda: apis.lever(busca, fontes["lever"]))

    precisa_navegador = escolhidas & (set(FONTES_NAVEGADOR) | set(fontes.get("navegador") or {}))
    if precisa_navegador:
        with navegador.abrir() as ctx:
            rodar("linkedin", lambda: sites.linkedin(ctx, busca, cfg))
            rodar("indeed", lambda: sites.indeed(ctx, busca, cfg))
            for nome, site in (fontes.get("navegador") or {}).items():
                rodar(nome, lambda n=nome, s=site: sites.generico(ctx, n, s, busca, cfg), ativa=True)
    return vagas


def cmd_buscar(args):
    cfg, _, ia = preparar()
    todas = set(FONTES_API) | set(FONTES_NAVEGADOR) | set(cfg["fontes"].get("navegador") or {})
    escolhidas = set(args.fontes.split(",")) if args.fontes else todas
    db = Banco()

    vagas = coletar(cfg, escolhidas)
    excluir = cfg["busca"].get("excluir_titulos", [])
    novas = [v for v in vagas if not db.existe(v.id) and not titulo_excluido(v.titulo, excluir)]
    console.print(f"\n{len(vagas)} encontradas, {len(novas)} novas para avaliar.")

    for v in novas:
        db.inserir(v)
    pendentes = db.listar(status="nova")
    for i, row in enumerate(pendentes, 1):
        if len(row["descricao"] or "") < 100:
            db.status(row["id"], "erro", "descrição vazia")
            continue
        with console.status(f"[{i}/{len(pendentes)}] Avaliando: {row['titulo'][:60]}"):
            try:
                a = ia.avaliar_vaga(texto_vaga(row))
            except (anthropic.APIError, RuntimeError, ValidationError) as e:
                console.print(f"  [red]erro ao avaliar {row['id']}: {e}[/]")
                continue
        db.avaliar(row["id"], a.nota, a.model_dump())
        cor = "green" if a.nota >= cfg["nota_minima"] else "dim"
        console.print(f"  [{cor}]{a.nota:3d}[/]  {row['titulo'][:70]} — {row['empresa'][:30]}")
    console.print(f"\nPróximo passo: [bold]python main.py revisar[/]")


def mostrar_vaga(row):
    a = json.loads(row["analise"] or "{}")
    corpo = (
        f"[bold]{row['empresa']}[/] · {row['local']} · {row['fonte']}\n{row['url']}\n\n"
        f"[bold]Nota {row['nota']}[/] ({a.get('recomendacao')}) — {a.get('resumo', '')}\n\n"
        f"[green]+[/] " + "\n[green]+[/] ".join(a.get("pontos_fortes", [])) + "\n"
        f"[red]-[/] " + "\n[red]-[/] ".join(a.get("lacunas", []))
    )
    console.print(Panel(corpo, title=row["titulo"], expand=False))


def cmd_revisar(_args):
    cfg = config.carregar()
    db = Banco()
    linhas = db.listar(status="avaliada", nota_minima=cfg["nota_minima"])
    if not linhas:
        console.print("Nada para revisar. Rode [bold]python main.py buscar[/].")
        return
    for row in linhas:
        mostrar_vaga(row)
        op = Prompt.ask("(a)provar  (r)ejeitar  (d)epois  (s)air", choices=["a", "r", "d", "s"], default="a")
        if op == "s":
            break
        if op == "a":
            db.status(row["id"], "aprovada")
        elif op == "r":
            db.status(row["id"], "rejeitada")
    console.print(f"Próximo passo: [bold]python main.py aplicar[/]")


def cmd_aplicar(args):
    cfg, _, ia = preparar()
    db = Banco()
    if args.id:
        row = db.obter(args.id)
        if row is None:
            raise SystemExit(f"Vaga {args.id} não encontrada.")
        fila = [row]
    else:
        fila = db.listar(status="aprovada")[: cfg["limite_aplicacoes"]]
    if not fila:
        console.print("Nenhuma vaga aprovada. Rode [bold]python main.py revisar[/].")
        return

    from autoaplicar.aplicador import fluxo
    salvas = fluxo.carregar_respostas()
    with navegador.abrir() as ctx:
        for i, row in enumerate(fila, 1):
            console.rule(f"[{i}/{len(fila)}] {row['titulo']} — {row['empresa']}")
            try:
                status, obs = fluxo.aplicar(ctx, row, ia, cfg, salvas)
            except KeyboardInterrupt:
                console.print("\nInterrompido.")
                break
            except Exception as e:  # noqa: BLE001 - registra e segue para a próxima vaga
                status, obs = "erro", str(e).splitlines()[0][:200]
            db.status(row["id"], status, obs)
            console.print(f"→ [bold]{status}[/] {obs}")
            navegador.pausa(cfg, 2)


def cmd_listar(args):
    db = Banco()
    t = Table("id", "nota", "status", "título", "empresa", "obs")
    for r in db.listar(status=args.status):
        t.add_row(r["id"][:40], str(r["nota"] or "-"), r["status"], (r["titulo"] or "")[:45],
                  (r["empresa"] or "")[:25], (r["obs"] or "")[:30])
    console.print(t)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("perfil", help="mostra o que a IA entendeu do seu currículo")
    sub.add_parser("login", help="abre o navegador para você logar nos sites (uma vez)")
    b = sub.add_parser("buscar", help="busca vagas e dá nota de compatibilidade")
    b.add_argument("--fontes", help="ex.: gupy,linkedin (padrão: todas ativas no config)")
    sub.add_parser("revisar", help="aprova/rejeita vagas acima da nota mínima")
    a = sub.add_parser("aplicar", help="preenche e envia (com sua confirmação) as vagas aprovadas")
    a.add_argument("--id", help="aplicar a uma vaga específica")
    l = sub.add_parser("listar", help="lista vagas no banco")
    l.add_argument("--status")
    args = p.parse_args()
    {"perfil": cmd_perfil, "login": cmd_login, "buscar": cmd_buscar, "revisar": cmd_revisar,
     "aplicar": cmd_aplicar, "listar": cmd_listar}[args.cmd](args)


if __name__ == "__main__":
    main()
