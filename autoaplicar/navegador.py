"""Navegador Chromium com perfil persistente: você faz login uma vez e as sessões ficam salvas."""

import random
import time
from contextlib import contextmanager

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .config import DADOS

PERFIL_NAVEGADOR = DADOS / "navegador"

SITES_LOGIN = {
    "LinkedIn": "https://www.linkedin.com/login",
    "Indeed": "https://secure.indeed.com/auth",
    "Gupy": "https://login.gupy.io/candidates/signin",
    "Catho": "https://www.catho.com.br/login/",
    "InfoJobs": "https://www.infojobs.com.br/login.aspx",
}


@contextmanager
def abrir(headless: bool = False):
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PERFIL_NAVEGADOR,
            headless=headless,
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.set_default_timeout(10000)
        try:
            yield ctx
        finally:
            ctx.close()


def pausa(cfg: dict, fator: float = 1.0):
    a, b = cfg.get("pausa", [1.5, 4.0])
    time.sleep(random.uniform(a, b) * fator)


def pagina(ctx: BrowserContext) -> Page:
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def texto(page: Page, seletores: list[str], limite: int = 20000) -> str:
    """Texto do primeiro seletor encontrado; cai para <main>/<body>."""
    for sel in [*seletores, "main", "body"]:
        loc = page.locator(sel).first
        try:
            if loc.count():
                t = loc.inner_text(timeout=3000).strip()
                if t:
                    return t[:limite]
        except Exception:
            continue
    return ""


def fazer_login(ctx: BrowserContext):
    page = pagina(ctx)
    for nome, url in SITES_LOGIN.items():
        page.goto(url)
        input(f"→ Faça login no {nome} no navegador e aperte Enter aqui (ou Enter para pular)... ")
