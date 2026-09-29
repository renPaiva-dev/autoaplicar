"""Chamadas ao Claude: extrair perfil do currículo, avaliar vagas e responder formulários."""

import json
from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel

MODELO = "claude-opus-5-5"

T = TypeVar("T", bound=BaseModel)


# ---------- Esquemas de saída ----------

class Experiencia(BaseModel):
    cargo: str
    empresa: str
    periodo: str
    resumo: str


class Perfil(BaseModel):
    nome: str
    email: str
    telefone: str
    cidade: str
    cargo_atual_ou_alvo: str
    anos_experiencia: float
    senioridade: Literal["estagio", "junior", "pleno", "senior", "especialista"]
    habilidades: list[str]
    idiomas: list[str]
    formacao: list[str]
    experiencias: list[Experiencia]
    links: list[str]


class Avaliacao(BaseModel):
    nota: int  # 0 a 100
    idioma: Literal["pt", "en", "outro"]  # idioma em que a vaga está escrita
    recomendacao: Literal["aplicar", "talvez", "nao_aplicar"]
    resumo: str
    pontos_fortes: list[str]
    lacunas: list[str]


class RespostaCampo(BaseModel):
    campo_id: str
    valor: str
    origem: Literal["curriculo", "respostas_padrao", "respostas_salvas", "inferido", "manter", "perguntar"]
    observacao: str


class RespostasFormulario(BaseModel):
    respostas: list[RespostaCampo]


# ---------- Prompts ----------

INSTRUCOES = """Você ajuda uma pessoa a se candidatar a vagas de emprego. Abaixo está o currículo dela \
e respostas fixas que ela forneceu. Regras:
- Nunca invente experiência, formação, certificações ou habilidades que não estejam no currículo \
ou nas respostas fornecidas. Honestidade é obrigatória: uma candidatura com dados falsos prejudica a pessoa.
- Pode reformular e destacar o que existe no currículo de acordo com a vaga.
- Responda no idioma da vaga (português ou inglês)."""

TAREFA_AVALIAR = """Avalie a compatibilidade entre o currículo e a vaga abaixo.
Nota de 0 a 100: 80+ = forte aderência (requisitos obrigatórios atendidos, senioridade adequada); \
60-79 = boa, com lacunas contornáveis; 40-59 = fraca; <40 = não combina.
Considere senioridade, requisitos obrigatórios vs desejáveis, localização/modelo de trabalho e idioma.
Seja realista: não infle a nota.
Em "idioma", informe o idioma em que o anúncio da vaga está escrito.

<vaga>
{vaga}
</vaga>"""

TAREFA_FORMULARIO = """Preencha os campos de um formulário de candidatura para a vaga abaixo.

<vaga>
{vaga}
</vaga>

<respostas_salvas>
Respostas que a pessoa já deu antes para perguntas parecidas (use quando a pergunta for equivalente):
{salvas}
</respostas_salvas>

<campos>
{campos}
</campos>

Para cada campo, retorne um item com o mesmo campo_id:
- valor: o texto a preencher. Para select/radio use EXATAMENTE o texto de uma das opções. \
Para checkbox use "sim" ou "nao"; para "checkboxes" (múltipla escolha) liste as opções separadas por " | ". Para campo de arquivo de currículo/CV/resume use "CURRICULO"; \
outros arquivos: origem "perguntar".
- Campos numéricos (ex.: anos de experiência com X) recebem só o número, calculado a partir do currículo.
- Cartas de apresentação / "por que você quer trabalhar aqui": escreva um texto curto (até 150 palavras), \
específico para a vaga, baseado só no currículo.
- Se o campo já tem um valor_atual correto, use origem "manter" e valor igual ao atual.
- Se a resposta não pode ser deduzida com segurança do currículo, das respostas padrão ou das salvas \
(ex.: pretensão salarial não informada, perguntas sobre documentos, dados pessoais ausentes), \
use origem "perguntar" e valor vazio. Não chute.
- Perguntas demográficas voluntárias (gênero, raça/etnia, deficiência, veterano, idade, orientação, \
pronomes): use a resposta de respostas_padrao/respostas_salvas se houver; senão escolha a opção \
"prefiro não responder"/"decline" se existir; senão, se for obrigatória, origem "perguntar"; se não \
for obrigatória, origem "manter" com valor vazio. Nunca deduza isso pelo nome ou pelo currículo.
- Termos de consentimento/privacidade obrigatórios: origem "perguntar" (a pessoa decide).
- observacao: uma frase curta explicando de onde veio a resposta."""


class IA:
    def __init__(self, texto_curriculo: str, respostas_padrao: dict):
        self.client = anthropic.Anthropic()
        contexto = (
            f"{INSTRUCOES}\n\n<curriculo>\n{texto_curriculo}\n</curriculo>\n\n"
            f"<respostas_padrao>\n{json.dumps(respostas_padrao, ensure_ascii=False, indent=1)}\n"
            "</respostas_padrao>"
        )
        # Bloco fixo (currículo) em cache: é reenviado em toda chamada.
        self.system = [{"type": "text", "text": contexto, "cache_control": {"type": "ephemeral"}}]

    def _perguntar(self, tarefa: str, esquema: type[T], esforco: str) -> T:
        resp = self.client.messages.parse(
            model=MODELO,
            max_tokens=16000,
            system=self.system,
            messages=[{"role": "user", "content": tarefa}],
            output_format=esquema,
            output_config={"effort": esforco},
            # Se o classificador de segurança recusar por engano, o servidor tenta outro modelo.
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("O modelo recusou a solicitação.")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise RuntimeError(f"Resposta incompleta da IA (stop_reason={resp.stop_reason}).")
        return resp.parsed_output

    def extrair_perfil(self) -> Perfil:
        return self._perguntar(
            "Extraia um perfil estruturado do currículo. Campos ausentes: string vazia / lista vazia.",
            Perfil, "low",
        )

    def avaliar_vaga(self, vaga_texto: str) -> Avaliacao:
        return self._perguntar(TAREFA_AVALIAR.format(vaga=vaga_texto), Avaliacao, "low")

    def responder_formulario(self, vaga_texto: str, campos: list[dict], salvas: dict) -> RespostasFormulario:
        tarefa = TAREFA_FORMULARIO.format(
            vaga=vaga_texto,
            salvas=json.dumps(salvas, ensure_ascii=False, indent=1) if salvas else "(nenhuma)",
            campos=json.dumps(campos, ensure_ascii=False, indent=1),
        )
        return self._perguntar(tarefa, RespostasFormulario, "medium")


def texto_vaga(v) -> str:
    """Formata uma vaga (linha do banco ou dict) para o prompt."""
    return (
        f"Título: {v['titulo']}\nEmpresa: {v['empresa']}\nLocal: {v['local']}\nURL: {v['url']}\n\n"
        f"{(v['descricao'] or '')[:20000]}"
    )
