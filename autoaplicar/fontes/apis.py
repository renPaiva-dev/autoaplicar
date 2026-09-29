"""Fontes com API pública JSON (não precisam de navegador nem login para buscar)."""

import httpx

from .base import Vaga, html_para_texto

HTTP = httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0 (autoaplicar)"}, follow_redirects=True)


def _local_ok(local: str, remoto: bool, busca: dict) -> bool:
    alvo = (busca.get("localizacao") or "").lower()
    if not alvo or alvo in ("brasil", "brazil"):
        return True
    return alvo in local.lower() or (remoto and busca.get("aceitar_remoto", True))


def _titulo_ok(titulo: str, palavras: list[str]) -> bool:
    return not palavras or any(p.lower() in titulo.lower() for p in palavras)


def gupy(busca: dict) -> list[Vaga]:
    vagas, vistos = [], set()
    limite = busca.get("max_vagas_por_fonte", 30)
    for termo in busca.get("termos", []):
        r = HTTP.get("https://employability-portal.gupy.io/api/v1/jobs",
                     params={"jobName": termo, "limit": min(limite, 100), "offset": 0})
        r.raise_for_status()
        for j in r.json().get("data", []):
            if j["id"] in vistos:
                continue
            vistos.add(j["id"])
            remoto = j.get("isRemoteWork") or j.get("workplaceType") == "remote"
            local = ", ".join(x for x in (j.get("city"), j.get("state")) if x) + (" (remoto)" if remoto else "")
            if not _local_ok(local, remoto, busca):
                continue
            vagas.append(Vaga(
                fonte="gupy", id_externo=str(j["id"]), titulo=j["name"],
                empresa=j.get("careerPageName", ""), local=local, url=j["jobUrl"],
                descricao=html_para_texto(j.get("description", "")),
            ))
    return vagas


def greenhouse(busca: dict, cfg: dict) -> list[Vaga]:
    vagas = []
    for empresa in cfg.get("empresas", []):
        r = HTTP.get(f"https://boards-api.greenhouse.io/v1/boards/{empresa}/jobs", params={"content": "true"})
        if r.status_code == 404:
            print(f"  [greenhouse] empresa '{empresa}' não encontrada")
            continue
        r.raise_for_status()
        achadas = []
        for j in r.json().get("jobs", []):
            local = (j.get("location") or {}).get("name", "")
            if not _titulo_ok(j["title"], cfg.get("palavras_titulo", [])):
                continue
            if not _local_ok(local, "remote" in local.lower(), busca):
                continue
            achadas.append(Vaga(
                fonte="greenhouse", id_externo=f"{empresa}-{j['id']}", titulo=j["title"],
                empresa=j.get("company_name") or empresa, local=local, url=j["absolute_url"],
                descricao=html_para_texto(j.get("content", "")),
            ))
        vagas += achadas[:busca.get("max_vagas_por_fonte", 30)]
    return vagas


def lever(busca: dict, cfg: dict) -> list[Vaga]:
    vagas = []
    for empresa in cfg.get("empresas", []):
        r = HTTP.get(f"https://api.lever.co/v0/postings/{empresa}", params={"mode": "json"})
        if r.status_code == 404:
            print(f"  [lever] empresa '{empresa}' não encontrada")
            continue
        r.raise_for_status()
        achadas = []
        for j in r.json():
            cat = j.get("categories") or {}
            local = cat.get("location", "") or ""
            remoto = j.get("workplaceType") == "remote"
            if not _titulo_ok(j["text"], cfg.get("palavras_titulo", [])):
                continue
            if not _local_ok(local, remoto, busca):
                continue
            listas = "\n\n".join(
                f"{l.get('text', '')}\n{html_para_texto(l.get('content', ''))}" for l in j.get("lists", [])
            )
            achadas.append(Vaga(
                fonte="lever", id_externo=j["id"], titulo=j["text"], empresa=empresa, local=local,
                url=j["hostedUrl"], url_aplicar=j.get("applyUrl", ""),
                descricao=f"{j.get('descriptionPlain', '')}\n\n{listas}\n\n{j.get('additionalPlain', '')}",
            ))
        vagas += achadas[:busca.get("max_vagas_por_fonte", 30)]
    return vagas
