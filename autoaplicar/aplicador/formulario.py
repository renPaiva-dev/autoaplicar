"""Leitura e preenchimento genérico de formulários (qualquer site).

Cada campo visível recebe um atributo data-aa="cN" para ser localizado depois.
Grupos de radio viram um único campo com opções.
"""

import re
import unicodedata

from playwright.sync_api import Page

JS_EXTRAIR = r"""
(rootSel) => {
  const root = (rootSel && document.querySelector(rootSel)) || document;
  window.__aaN = window.__aaN || 0;
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                    && getComputedStyle(el).visibility !== 'hidden';
  const limpa = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 300);
  const porIds = ids => (ids || '').split(/\s+/).map(i => document.getElementById(i)?.innerText || '').join(' ');
  const marca = el => el.dataset.aa || (el.dataset.aa = 'c' + (++window.__aaN));

  function rotulo(el) {
    let t = '';
    if (el.labels && el.labels.length) t = [...el.labels].map(l => l.innerText).join(' ');
    if (!t && el.getAttribute('aria-labelledby')) t = porIds(el.getAttribute('aria-labelledby'));
    if (!t) t = el.getAttribute('aria-label') || '';
    if (!t) { const l = el.closest('label'); if (l) t = l.innerText; }
    if (!t) {
      let p = el.parentElement;
      for (let i = 0; i < 3 && p && !limpa(t); i++, p = p.parentElement) {
      if (limpa(p.innerText).length <= 160) t = p.innerText || '';
    }
    }
    if (!limpa(t)) t = el.placeholder || el.name || '';
    // rótulo curto demais ("Attach", "Upload"): tenta o rótulo do bloco, depois o texto ao redor
    if (limpa(t).length < 12) {
      const a = el.parentElement && el.parentElement.closest('[aria-labelledby]');
      const bloco = a && limpa(porIds(a.getAttribute('aria-labelledby')));
      if (bloco) t = bloco + ' (' + limpa(t) + ')';
    }
    let p = el.parentElement;
    for (let i = 0; i < 4 && p && limpa(t).length < 12; i++, p = p.parentElement) {
      const extra = limpa(p.innerText);
      if (extra.length > limpa(t).length && extra.length <= 160) t = extra;
    }
    return limpa(t);
  }

  function perguntaGrupo(el) {
    const c = el.closest('fieldset, [role=radiogroup], [role=group]');
    if (c) {
      const lg = c.querySelector('legend');
      const t = (lg && lg.innerText) || c.getAttribute('aria-label') || porIds(c.getAttribute('aria-labelledby'));
      if (limpa(t)) return limpa(t);
      return limpa(c.innerText);
    }
    let p = el.parentElement;
    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
      if (p.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`).length > 1) return limpa(p.innerText);
    }
    return rotulo(el);
  }

  // rótulo de uma opção de radio/checkbox: só o texto próximo, não o da pergunta inteira
  function rotuloOpcao(el) {
    if (el.labels && el.labels.length) return limpa([...el.labels].map(l => l.innerText).join(' '));
    const t = el.getAttribute('aria-label') || (el.parentElement && el.parentElement.innerText) || el.value;
    return limpa(t).slice(0, 150);
  }

  const campos = [], grupos = {};
  const nomesCheckbox = {};
  root.querySelectorAll('input[type=checkbox][name]').forEach(el => {
    nomesCheckbox[el.name] = (nomesCheckbox[el.name] || 0) + 1;
  });
  let login = false;
  root.querySelectorAll('input, select, textarea').forEach(el => {
    let tipo = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea'
             : (el.getAttribute('type') || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image', 'search'].includes(tipo)) return;
    if (el.disabled || el.readOnly) return;
    const marcavel = tipo === 'radio' || tipo === 'checkbox';
    const labelVisivel = el.labels && [...el.labels].some(vis);
    if (tipo !== 'file' && !vis(el) && !(marcavel && labelVisivel)) return;
    if (tipo === 'password') { login = true; return; }
    // inputs "fantasma" usados por componentes JS só para validação (ex.: react-select)
    const cs = getComputedStyle(el);
    if (tipo !== 'file' && !marcavel && (el.getAttribute('aria-hidden') === 'true' || cs.opacity === '0')) return;
    if (el.getAttribute('role') === 'combobox' && tipo !== 'select') tipo = 'combobox';
    const id = marca(el);
    let obrigatorio = el.required || el.getAttribute('aria-required') === 'true';

    // radios com o mesmo name, e checkboxes com o mesmo name, viram uma pergunta com opções
    const emGrupo = tipo === 'radio' || (tipo === 'checkbox' && el.name && nomesCheckbox[el.name] > 1);
    if (emGrupo) {
      const chave = tipo + ':' + (el.name || id);
      if (!grupos[chave]) {
        const pergunta = perguntaGrupo(el);
        grupos[chave] = { campo_id: id, tipo: tipo === 'radio' ? 'radio' : 'checkboxes', rotulo: pergunta,
                          opcoes: [], ids_opcoes: [], obrigatorio: obrigatorio || /[*✱]/.test(pergunta),
                          valor_atual: '' };
        campos.push(grupos[chave]);
      }
      const g = grupos[chave], op = rotuloOpcao(el);
      g.opcoes.push(op); g.ids_opcoes.push(id);
      if (el.checked) g.valor_atual = g.valor_atual ? g.valor_atual + ' | ' + op : op;
      return;
    }
    const r = rotulo(el);
    obrigatorio = obrigatorio || /[*✱]\s*$/.test(r) || r.includes('✱');
    const c = { campo_id: id, tipo, rotulo: r, nome: el.name || el.id || '', obrigatorio, valor_atual: '' };
    if (tipo === 'select') {
      c.opcoes = [...el.options].map(o => limpa(o.text)).filter(Boolean).slice(0, 80);
      const o = el.options[el.selectedIndex];
      if (o && o.value !== '' && el.selectedIndex > 0) c.valor_atual = limpa(o.text);
    } else if (tipo === 'checkbox') {
      c.valor_atual = el.checked ? 'sim' : 'nao';
    } else if (tipo === 'file') {
      c.valor_atual = el.files && el.files.length ? el.files[0].name : '';
    } else {
      c.valor_atual = (el.value || '').slice(0, 300);
    }
    campos.push(c);
  });

  const botoes = [];
  root.querySelectorAll('button, [role=button], input[type=submit], a').forEach(b => {
    if (!vis(b) || b.disabled || b.getAttribute('aria-disabled') === 'true') return;
    const t = limpa(b.innerText || b.value || b.getAttribute('aria-label'));
    if (!t || t.length > 60) return;
    if (!b.dataset.aab) b.dataset.aab = 'b' + (++window.__aaN);
    botoes.push({ id: b.dataset.aab, texto: t });
  });

  const erros = [...root.querySelectorAll('[role=alert], [aria-invalid=true], [class*=error], [class*=erro]')]
    .filter(vis).map(e => limpa(e.innerText)).filter(Boolean).slice(0, 8);

  return { campos, botoes, erros, login };
}
"""

TEXTO_CANDIDATAR = ["candidatura simplificada", "easy apply", "quero me candidatar", "candidatar-se",
                    "candidate-se", "candidatar", "apply now", "apply for this job", "apply", "aplicar",
                    "inscrever-se", "enviar curriculo"]
TEXTO_ENVIAR = ["enviar candidatura", "submit application", "submit your application", "enviar sua candidatura",
                "finalizar candidatura", "concluir candidatura", "send application", "enviar", "submit",
                "finalizar", "concluir"]
TEXTO_PROXIMO = ["avancar", "proximo", "proxima etapa", "next", "continuar", "continue", "revisar",
                 "review", "salvar e continuar", "prosseguir", "seguir"]
TEXTO_SUCESSO = ["candidatura enviada", "application submitted", "application was sent", "your application has been",
                 "recebemos sua candidatura", "candidatura realizada", "candidatura concluida",
                 "thank you for applying", "thanks for applying", "obrigado por se candidatar", "voce se candidatou"]


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", s)).strip()


def achar_botao(botoes: list[dict], textos: list[str]) -> dict | None:
    """Botão cujo texto começa com um dos textos (na ordem de prioridade da lista)."""
    for alvo in textos:
        for b in botoes:
            t = normalizar(b["texto"])
            if t == alvo or t.startswith(alvo + " "):
                return b
    return None


OPCAO_VISIVEL = "[role=option]:visible"


def extrair(page: Page, raiz: str | None, ids_ignorar: set[str] = frozenset()) -> dict:
    dados = page.evaluate(JS_EXTRAIR, raiz)
    # Dropdowns customizados só mostram as opções quando abertos: abre, lê e fecha.
    for c in dados["campos"]:
        if c["tipo"] == "combobox" and c["campo_id"] not in ids_ignorar:
            c["opcoes"] = _opcoes_combobox(page, c["campo_id"])
    return dados


def _opcoes_combobox(page: Page, campo_id: str) -> list[str]:
    loc = page.locator(f'[data-aa="{campo_id}"]')
    try:
        loc.click(timeout=3000)
        page.wait_for_timeout(400)
        opcoes = [t.strip() for t in page.locator(OPCAO_VISIVEL).all_inner_texts()][:80]
        loc.press("Escape")
        return [o for o in opcoes if o]
    except Exception:
        return []


def _melhor_opcao(valor: str, opcoes: list[str]) -> int | None:
    v = normalizar(valor)
    norm = [normalizar(o) for o in opcoes]
    if v in norm:
        return norm.index(v)
    for i, o in enumerate(norm):
        if o and (o.startswith(v) or v.startswith(o)):
            return i
    for i, o in enumerate(norm):
        if v and v in o:
            return i
    return None


def _marcar(loc, marcar: bool = True):
    """check() falha em checkboxes estilizados; nesse caso clica via JS e confere."""
    try:
        (loc.check if marcar else loc.uncheck)(force=True, timeout=3000)
    except Exception:
        if loc.is_checked() != marcar:
            loc.evaluate("el => el.click()")
        if loc.is_checked() != marcar:
            raise


def preencher(page: Page, campo: dict, valor: str, curriculo_pdf) -> str | None:
    """Preenche um campo. Retorna mensagem de erro ou None."""
    loc = page.locator(f'[data-aa="{campo["campo_id"]}"]')
    tipo = campo["tipo"]
    try:
        if tipo == "file":
            if valor == "CURRICULO":
                loc.set_input_files(str(curriculo_pdf))
                return None
            return "arquivo não suportado"
        if tipo == "select":
            i = _melhor_opcao(valor, campo.get("opcoes", []))
            if i is None:
                return f"opção '{valor}' não existe"
            loc.select_option(label=campo["opcoes"][i])
        elif tipo == "radio":
            i = _melhor_opcao(valor, campo.get("opcoes", []))
            if i is None:
                return f"opção '{valor}' não existe"
            _marcar(page.locator(f'[data-aa="{campo["ids_opcoes"][i]}"]'))
        elif tipo == "checkboxes":
            for parte in (p.strip() for p in valor.split("|")):
                i = _melhor_opcao(parte, campo.get("opcoes", []))
                if i is None:
                    return f"opção '{parte}' não existe"
                _marcar(page.locator(f'[data-aa="{campo["ids_opcoes"][i]}"]'))
        elif tipo == "checkbox":
            _marcar(loc, normalizar(valor) in ("sim", "true", "yes", "s"))
        elif tipo == "combobox":
            loc.click(timeout=3000)
            loc.fill(valor)
            page.wait_for_timeout(900)
            visiveis = page.locator(OPCAO_VISIVEL)
            textos = visiveis.all_inner_texts()
            i = _melhor_opcao(valor, textos) if textos else None
            if i is not None:
                visiveis.nth(i).click(timeout=3000)
            elif textos:
                loc.press("Escape")
                return f"opção '{valor}' não existe"
            else:
                loc.press("Enter")
        else:
            loc.fill(valor)
    except Exception as e:  # noqa: BLE001 - qualquer falha vira aviso para revisão manual
        return str(e).splitlines()[0][:120]
    return None
