# autoaplicar

Ferramenta de linha de comando que busca vagas de emprego em vários sites, compara cada uma com o
seu currículo usando o [Claude](https://www.anthropic.com/claude) e preenche os formulários de
candidatura por você.

**Nenhuma candidatura é enviada sem a sua confirmação.** O programa preenche tudo, para no botão
final e espera você conferir.

```text
perfil → login → buscar → revisar → aplicar
```

## Funcionalidades

- **Busca em várias fontes:** Gupy, Greenhouse, Lever, LinkedIn (Easy Apply), Indeed, Catho e
  InfoJobs. Outros sites podem ser adicionados só pelo arquivo de configuração.
- **Nota de compatibilidade:** cada vaga recebe uma nota de 0 a 100, com pontos fortes, lacunas e
  recomendação.
- **Preenchimento genérico de formulários:** texto, upload do currículo, selects, radios,
  checkboxes e dropdowns customizados (react-select), inclusive em formulários de várias etapas.
- **Sem inventar dados:** a IA só usa o que está no currículo e nas respostas que você configurou.
  Quando não sabe algo, pergunta a você no terminal e guarda a resposta para as próximas vagas.
- **Currículo bilíngue:** vagas em inglês recebem o seu PDF em inglês, se você configurar um.
- **Histórico local:** vagas, notas e status ficam em um banco SQLite, e nenhuma vaga é avaliada duas vezes.

## Requisitos

- Python 3.10 ou mais recente (testado com 3.12 e 3.13)
- Uma chave da API da Anthropic ([console.anthropic.com](https://console.anthropic.com))
- O seu currículo em PDF com texto selecionável (PDF escaneado não funciona)

## Instalação

```bash
git clone https://github.com/renPaiva-dev/aa.git
cd aa

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

cp config.example.yaml config.yaml
cp /caminho/do/seu-curriculo.pdf curriculo.pdf
export ANTHROPIC_API_KEY=sk-ant-...
```

Depois edite o `config.yaml`: termos de busca, localização, fontes ativas e `respostas_padrao`
(telefone, links, pretensão salarial etc.).

## Uso

| Comando | O que faz |
| --- | --- |
| `python main.py perfil` | Lê o PDF e mostra o que a IA entendeu do seu currículo. Rode primeiro e confira |
| `python main.py login` | Abre o navegador para você entrar no LinkedIn, Indeed, Gupy, Catho e InfoJobs. As sessões ficam salvas |
| `python main.py buscar` | Coleta vagas de todas as fontes ativas e dá uma nota para cada uma |
| `python main.py buscar --fontes gupy,lever` | Busca só nas fontes indicadas |
| `python main.py revisar` | Mostra as vagas acima de `nota_minima`; você aprova, rejeita ou deixa para depois |
| `python main.py aplicar` | Candidata-se às vagas aprovadas, até `limite_aplicacoes` por execução |
| `python main.py aplicar --id gupy:12345` | Candidata-se a uma vaga específica |
| `python main.py listar [--status aplicada]` | Lista as vagas do banco e o status de cada uma |

Os status de uma vaga são: `nova` → `avaliada` → `aprovada` / `rejeitada` → `aplicada` / `pulada` / `erro`.

### Durante o `aplicar`

- O navegador abre visível, para você acompanhar tudo.
- A cada etapa, o terminal mostra uma tabela com o que foi preenchido e de onde veio cada resposta
  (`curriculo`, `respostas_padrao`, `respostas_salvas`, `inferido`).
- Se a IA não puder responder algo com segurança (pretensão salarial, termos de consentimento,
  documentos), ela pergunta a você. A resposta fica salva em `dados/respostas.json`.
- Perguntas demográficas voluntárias (gênero, raça, deficiência) nunca são deduzidas. O programa
  usa a sua resposta configurada ou escolhe "prefiro não responder".
- No botão final, você escolhe: `s` envia, `m` registra que você enviou manualmente e `p` pula a vaga.
  Antes de responder, você pode corrigir qualquer campo direto no navegador.
- Se aparecer login, captcha ou uma etapa desconhecida, o programa pausa até você resolver no navegador.

## Configuração

Todas as opções estão comentadas em [`config.example.yaml`](config.example.yaml). As principais:

| Opção | Para que serve |
| --- | --- |
| `curriculo_pdf` / `curriculo_pdf_en` | Currículo principal e versão opcional em inglês, anexada em vagas escritas em inglês |
| `busca.termos`, `busca.localizacao` | O que buscar e onde |
| `busca.excluir_titulos` | Descarta vagas pelo título antes de chamar a IA (ex.: "sênior"), o que economiza chamadas |
| `nota_minima` | Nota a partir da qual a vaga aparece em `revisar` |
| `limite_aplicacoes`, `pausa` | Ritmo das candidaturas, para não parecer robô |
| `fontes.greenhouse.empresas`, `fontes.lever.empresas` | Empresas a acompanhar (o token está na URL do quadro de vagas) |
| `fontes.navegador` | Sites sem API, definidos por um template de URL e uma regex de links de vagas |
| `respostas_padrao` | Respostas fixas para perguntas comuns. Deixe vazio o que preferir responder na hora |

### Adicionar outro site de vagas

Sites sem API podem ser adicionados em `fontes.navegador`, sem escrever código:

```yaml
fontes:
  navegador:
    meusite:
      url: "https://www.exemplo.com.br/vagas?q={termo}"   # também aceita {termo_slug} e {local}
      link_regex: "exemplo\\.com\\.br/vaga/\\d+"
```

## Fontes suportadas

| Fonte | Como busca | Login para candidatar |
| --- | --- | --- |
| Gupy | API pública do portal | Sim |
| Greenhouse | API pública, por empresa | Não |
| Lever | API pública, por empresa | Não |
| LinkedIn | Navegador; só vagas com *Candidatura simplificada* | Sim |
| Indeed | Navegador | Sim |
| Catho, InfoJobs | Navegador (template de URL + regex) | Sim |

## Privacidade

- O texto do currículo, as descrições das vagas e as perguntas dos formulários são enviados à API da
  Anthropic para gerar as notas e as respostas. Nada é enviado a outros serviços.
- Os dados pessoais ficam só na sua máquina e estão no `.gitignore`: `config.yaml`, PDFs, `dados/`
  (banco, respostas salvas e perfil do navegador com as sessões logadas).
- Nunca publique a pasta `dados/`: ela contém os cookies das suas contas.

## Custos

Cada vaga avaliada consome uma chamada ao Claude (`claude-opus-5-5`, com esforço baixo), e cada etapa
de formulário consome outra. O currículo é enviado com cache de prompt, o que barateia as chamadas
repetidas. Para gastar menos, use `excluir_titulos`, `palavras_titulo` e `max_vagas_por_fonte`.

## Avisos

- **LinkedIn e Indeed proíbem automação nos termos de uso** e podem restringir a sua conta. Use por
  sua conta e risco, com limites baixos.
- Os sites mudam de layout com frequência, e os seletores podem quebrar. Os pontos de ajuste são
  [`autoaplicar/fontes/sites.py`](autoaplicar/fontes/sites.py) (busca) e as listas `TEXTO_*` em
  [`autoaplicar/aplicador/formulario.py`](autoaplicar/aplicador/formulario.py) (textos dos botões).
- A IA pode errar. Revise cada candidatura antes de confirmar o envio.

## Status do projeto

| Parte | Situação |
| --- | --- |
| Busca via API (Gupy, Greenhouse, Lever) | Testada |
| Formulários Greenhouse e Lever | Testados |
| Busca no LinkedIn, Indeed, Catho e InfoJobs | Implementada; ainda não validada com conta logada |
| Easy Apply do LinkedIn e formulários da Gupy | Implementados; ainda não validados com conta logada |

Limitações conhecidas:

- Formulários dentro de `<iframe>` não são lidos; quando o programa pausar, você os preenche manualmente.
- Uploads que não sejam o currículo (carta em PDF, portfólio) ficam para você.

## Estrutura

```text
main.py                        CLI (perfil, login, buscar, revisar, aplicar, listar)
config.example.yaml            modelo de configuração
autoaplicar/
  ia.py                        prompts e chamadas ao Claude (perfil, nota, respostas de formulário)
  curriculo.py                 extração de texto do PDF
  db.py                        banco SQLite (dados/vagas.db)
  navegador.py                 Chromium com perfil persistente (Playwright)
  fontes/apis.py               Gupy, Greenhouse, Lever
  fontes/sites.py              LinkedIn, Indeed e sites genéricos via navegador
  aplicador/formulario.py      leitura e preenchimento genérico de campos
  aplicador/fluxo.py           etapas da candidatura e confirmação de envio
```

## Contribuindo

Issues e pull requests são bem-vindos, principalmente seletores atualizados para os sites de vagas
e suporte a novas fontes.
