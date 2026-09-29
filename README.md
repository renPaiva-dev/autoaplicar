# autoaplicar

Busca vagas em vários sites, dá uma nota de compatibilidade com o seu currículo usando o Claude
e preenche os formulários de candidatura. **Nada é enviado sem a sua confirmação.**

```
perfil → login → buscar → revisar → aplicar
```

| Etapa | O que faz |
|---|---|
| `perfil` | Lê o seu PDF e mostra o que a IA entendeu (confira antes de tudo) |
| `login` | Abre o navegador para você entrar no LinkedIn, Indeed, Gupy, Catho e InfoJobs. As sessões ficam salvas em `dados/navegador/` |
| `buscar` | Coleta as vagas, descarta títulos excluídos e dá uma nota de 0 a 100 para cada uma |
| `revisar` | Mostra as vagas acima de `nota_minima` com pontos fortes e lacunas; você aprova ou rejeita |
| `aplicar` | Abre cada vaga aprovada, clica em candidatar, preenche as etapas e **para antes de enviar** para você conferir |
| `listar` | Tabela das vagas e seus status (`--status aplicada`, etc.) |

## Instalação

```bash
python3 -m venv .venv          # ou: uv venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

cp config.example.yaml config.yaml   # edite: termos, localização, empresas, respostas_padrao
cp ~/Downloads/meu-curriculo.pdf curriculo.pdf
export ANTHROPIC_API_KEY=sk-ant-...  # https://console.anthropic.com
```

## Uso

```bash
.venv/bin/python main.py perfil
.venv/bin/python main.py login
.venv/bin/python main.py buscar                 # todas as fontes
.venv/bin/python main.py buscar --fontes gupy,greenhouse
.venv/bin/python main.py revisar
.venv/bin/python main.py aplicar
.venv/bin/python main.py aplicar --id gupy:12601484
```

### Currículo em inglês

Se `curriculo_pdf_en` estiver no config, vagas escritas em inglês recebem esse PDF, e as outras
recebem o `curriculo_pdf`. A IA identifica o idioma da vaga na etapa `buscar`. As respostas de texto
dos formulários sempre saem no idioma da vaga.

Para editar a versão em inglês, altere `curriculo-en.html` e gere o PDF de novo:

```bash
.venv/bin/python -c "from playwright.sync_api import sync_playwright; from pathlib import Path
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_page(); p.goto(Path('curriculo-en.html').resolve().as_uri())
    p.pdf(path='curriculo-en.pdf', format='A4', prefer_css_page_size=True); b.close()"
```

### Durante o `aplicar`

- A cada etapa aparece uma tabela com o que foi preenchido e a origem de cada resposta
  (`curriculo`, `respostas_padrao`, `inferido`...).
- Quando a IA não sabe responder com segurança (pretensão salarial, documentos, termos de
  consentimento), **ela pergunta a você no terminal**. A resposta é salva em `dados/respostas.json`
  e reaproveitada nas próximas vagas.
- Quando chega ao botão final: `s` envia, `m` indica que você enviou manualmente, `p` pula a vaga.
  Você pode corrigir qualquer campo direto no navegador antes de responder.
- Se aparecer login, captcha ou uma etapa que o programa não reconhece, ele pede para você resolver
  no navegador e depois continua.

## Fontes

| Fonte | Como busca | Observações |
|---|---|---|
| Gupy | API pública do portal | Candidatar exige conta Gupy (faça `login`) |
| Greenhouse | API pública, por empresa (`fontes.greenhouse.empresas`) | Formulário na própria página. Não precisa de login |
| Lever | API pública, por empresa | Formulário em `/apply`. Não precisa de login |
| LinkedIn | Navegador logado, só vagas com *Candidatura simplificada* | Preenche o modal etapa por etapa |
| Indeed | Navegador | Pode exibir verificação anti-robô; resolva no navegador |
| Catho, InfoJobs | Navegador, por template de URL + regex de links | Configurável em `fontes.navegador`; dá para adicionar outros sites do mesmo jeito |

## Custos e limites

- Cada vaga avaliada custa uma chamada ao Claude (`claude-opus-5-5`, effort `low`); cada etapa de
  formulário custa outra. O currículo vai em cache de prompt, o que barateia as chamadas repetidas.
  Use `excluir_titulos`, `palavras_titulo` e `max_vagas_por_fonte` para não avaliar vagas irrelevantes.
- `limite_aplicacoes` e `pausa` existem para não parecer robô. **O LinkedIn e o Indeed proíbem
  automação nos termos de uso** e podem restringir a sua conta; use limites baixos.

## Status atual

Testado de verdade:
- as buscas por API na Gupy, Greenhouse e Lever;
- a leitura e o preenchimento dos formulários da Greenhouse e da Lever (texto, upload, selects,
  radios, checkboxes e dropdowns customizados);
- o fluxo de `aplicar` até a tela de confirmação, com a IA simulada.

Ainda não testado, porque depende do seu login:
- a busca no LinkedIn, Indeed, Catho e InfoJobs;
- o modal do Easy Apply;
- os formulários da Gupy.

Esses sites mudam de layout com frequência. Se algo parar de funcionar, os pontos de ajuste são:
- os seletores em [autoaplicar/fontes/sites.py](autoaplicar/fontes/sites.py);
- as listas `TEXTO_*` (textos dos botões) em [autoaplicar/aplicador/formulario.py](autoaplicar/aplicador/formulario.py).

Limitações conhecidas: formulários dentro de `<iframe>` não são lidos (você preenche manualmente
quando o programa pausar), e campos de arquivo que não sejam o currículo ficam para você.

## Estrutura

```
main.py                         CLI
autoaplicar/ia.py               prompts e chamadas ao Claude (perfil, nota, respostas)
autoaplicar/curriculo.py        leitura do PDF
autoaplicar/db.py               SQLite (dados/vagas.db)
autoaplicar/navegador.py        Chromium com perfil persistente
autoaplicar/fontes/             apis.py (Gupy/Greenhouse/Lever), sites.py (navegador)
autoaplicar/aplicador/          formulario.py (lê/preenche campos), fluxo.py (etapas + confirmação)
```
