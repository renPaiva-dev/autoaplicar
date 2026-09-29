"""Fontes sem API: busca pelo navegador logado.

Os seletores desses sites mudam com frequência. Por isso a coleta de links usa padrões
de URL (mais estáveis que classes CSS) e o texto da vaga cai para <main>/<body> se
o seletor específico falhar.
"""

import re
import unicodedata
from urllib.parse import quote_plus

from playwright.sync_api import BrowserContext, Page

from ..navegador import pagina, pausa, texto
from .base import Vaga

JS_LINKS = "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"


def _rolar(page: Page, vezes: int = 5, seletor: str | None = None):
    for _ in range(vezes):
        if seletor and page.locator(seletor).count():
            page.locator(seletor).first.evaluate("el => el.scrollBy(0, el.scrollHeight)")
        else:
            page.mouse.wheel(0, 4000)
        page.wait_for_timeout(800)


def _logado(page: Page, site: str) -> bool:
    url = page.url
    if any(p in url for p in ("/login", "/authwall", "/checkpoint", "/uas/", "signin", "/auth")):
        print(f"  [{site}] parece que você não está logado. Rode: python main.py login")
        return False
    return True


def linkedin(ctx: BrowserContext, busca: dict, cfg: dict) -> list[Vaga]:
    page = pagina(ctx)
    ids: list[str] = []
    for termo in busca.get("termos", []):
        # f_AL=true: só "Candidatura simplificada"; f_TPR=r604800: última semana
        url = ("https://www.linkedin.com/jobs/search/?keywords=" + quote_plus(termo)
               + "&location=" + quote_plus(busca.get("localizacao", "")) + "&f_AL=true&f_TPR=r604800&sortBy=DD")
        page.goto(url)
        pausa(cfg)
        if not _logado(page, "linkedin"):
            return []
        _rolar(page, 6, ".jobs-search-results-list, .scaffold-layout__list")
        achados = page.evaluate(
            """() => {
                const ids = new Set();
                document.querySelectorAll('[data-job-id],[data-occludable-job-id]').forEach(e => {
                    const v = e.getAttribute('data-job-id') || e.getAttribute('data-occludable-job-id');
                    if (/^\\d+$/.test(v)) ids.add(v);
                });
                document.querySelectorAll('a[href*="/jobs/view/"]').forEach(a => {
                    const m = a.href.match(/\\/jobs\\/view\\/(\\d+)/); if (m) ids.add(m[1]);
                });
                return [...ids];
            }"""
        )
        ids += [i for i in achados if i not in ids]
    vagas = []
    for jid in ids[: busca.get("max_vagas_por_fonte", 30)]:
        url = f"https://www.linkedin.com/jobs/view/{jid}/"
        page.goto(url)
        pausa(cfg)
        titulo = texto(page, ["h1"], 300) or page.title()
        empresa = texto(page, [".job-details-jobs-unified-top-card__company-name",
                               ".jobs-unified-top-card__company-name", "a[href*='/company/']"], 200)
        local = texto(page, [".job-details-jobs-unified-top-card__primary-description-container",
                             ".job-details-jobs-unified-top-card__tertiary-description-container"], 300)
        desc = texto(page, ["#job-details", ".jobs-description__content", ".jobs-box__html-content"])
        vagas.append(Vaga("linkedin", jid, titulo, empresa, local.split("·")[0].strip(), url, desc))
    return vagas


def indeed(ctx: BrowserContext, busca: dict, cfg: dict) -> list[Vaga]:
    page = pagina(ctx)
    jks: list[str] = []
    for termo in busca.get("termos", []):
        page.goto("https://br.indeed.com/jobs?q=" + quote_plus(termo)
                  + "&l=" + quote_plus(busca.get("localizacao", "")) + "&sort=date&fromage=7")
        pausa(cfg)
        _rolar(page, 3)
        achados = page.evaluate(
            "() => [...new Set(Array.from(document.querySelectorAll('[data-jk]')).map(e => e.getAttribute('data-jk')))]"
        )
        jks += [j for j in achados if j and j not in jks]
        if not achados:
            print("  [indeed] nenhum resultado; se apareceu verificação anti-robô, resolva no navegador e rode de novo.")
    vagas = []
    for jk in jks[: busca.get("max_vagas_por_fonte", 30)]:
        url = f"https://br.indeed.com/viewjob?jk={jk}"
        page.goto(url)
        pausa(cfg)
        titulo = texto(page, ["h1"], 300) or page.title()
        empresa = texto(page, ["[data-company-name]", "[data-testid='inlineHeader-companyName']"], 200)
        local = texto(page, ["[data-testid='inlineHeader-companyLocation']", "[data-testid='job-location']"], 200)
        desc = texto(page, ["#jobDescriptionText"])
        vagas.append(Vaga("indeed", jk, titulo, empresa, local, url, desc))
    return vagas


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def generico(ctx: BrowserContext, nome: str, site: dict, busca: dict, cfg: dict) -> list[Vaga]:
    """Busca por template de URL + regex de links (config 'fontes.navegador')."""
    page = pagina(ctx)
    padrao = re.compile(site["link_regex"])
    links: list[str] = []
    for termo in busca.get("termos", []):
        url = site["url"].format(termo=quote_plus(termo), termo_slug=_slug(termo),
                                 local=quote_plus(busca.get("localizacao", "")))
        page.goto(url)
        pausa(cfg)
        _rolar(page, 3)
        for href in page.evaluate(JS_LINKS):
            href = href.split("#")[0]
            if padrao.search(href) and href not in links:
                links.append(href)
    vagas = []
    for url in links[: busca.get("max_vagas_por_fonte", 30)]:
        page.goto(url)
        pausa(cfg)
        titulo = texto(page, ["h1"], 300) or page.title()
        desc = texto(page, ["[class*='description']", "[class*='descricao']", "article"])
        id_ext = re.sub(r"\W+", "-", url.split("//", 1)[-1])[-120:]
        vagas.append(Vaga(nome, id_ext, titulo, "", "", url, desc))
    return vagas
