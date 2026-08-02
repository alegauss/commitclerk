<div align="center">

<img src="docs/logo.png" alt="logo do commitclerk" width="112" height="112">

# commitclerk

**Escreva mensagens de commit melhores com um comando — a partir do seu diff staged e de um LLM.**

[![PyPI](https://img.shields.io/pypi/v/commitclerk.svg)](https://pypi.org/project/commitclerk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-brightgreen.svg)](#requisitos)
[![CI](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml/badge.svg)](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org/)

[Site](https://alegauss.github.io/commitclerk/) · [Início rápido](#início-rápido) · [Uso](#uso) · [Por que existe](#por-que-existe) · [Configuração](#configuração) · [Contribuindo](CONTRIBUTING.md) · [English](README.md)

</div>

---

Um *clerk* (escrivão) registra o que de fato aconteceu. O `commitclerk` lê o seu diff staged, pede ao LLM uma mensagem no padrão Conventional Commits, mostra o resultado e faz o commit — com **zero dependências** — e ainda distribuído como [um único arquivo legível](dist/commitclerk.py) que você pode auditar antes de deixá-lo perto do seu código.

```console
$ git add .
$ clerk

--- commit message ---
fix: prevent duplicate webhook deliveries on retry

- Deduplicate by delivery id before enqueueing, so a provider retry no
  longer fans out into multiple downstream jobs.
- Store the id in the existing idempotency table instead of a new one,
  keeping the retention policy in a single place.
----------------------
[main a1b2c3d] fix: prevent duplicate webhook deliveries on retry
```

## Destaques

| | |
|---|---|
| 🪶 **Zero dependências** | Só biblioteca padrão (`urllib`, `subprocess`, `argparse`). Copie o arquivo e use. |
| 🔗 **Nativo do git** | Também instala como `git clerk`, então mora onde sua memória muscular de git já está. |
| ✍️ **O título pode ser seu** | `-m "feat: add X"` usa seu título literalmente e deixa a IA escrever só o corpo. |
| 📄 **Consciente de documentação** | Detecta commits de documentação — puros *e* misturados com código — e evita descrever features já entregues como se fossem novas. Veja [Por que existe](#por-que-existe). |
| 🧾 **Conventional Commits** | Gera prefixos `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `build:` / `perf:`. |
| 🏠 **Escreve como o seu repositório** | Lê os seus últimos 200 commits para aprender os tipos, escopos, formato de corpo e idioma que o seu time realmente usa, de modo que a mensagem pertença ao *seu* histórico em vez de ser genericamente correta. Local, sem chamada extra à API. |
| 👀 **Dry run** | `--dry-run` imprime a mensagem e não commita nada. |
| 🔧 **Independente de modelo** | OpenAI, Anthropic ou um modelo local do Ollama via `--provider`, qualquer modelo via `--model`, e qualquer endpoint compatível com a OpenAI via `--base-url`. |
| 🔒 **Funciona offline, se você quiser** | `--provider ollama` não precisa de chave de API e fala com o `localhost` — seu diff nunca sai da máquina. |
| 🔁 **Sobrevive a um rate limit** | Respostas transitórias (`429`/`5xx`) são repetidas com backoff e jitter, respeitando o `Retry-After`, em vez de perder o commit — e, se o modelo rejeitar um parâmetro, a requisição é corrigida e reenviada. |
| 🗂️ **Classifica o que mudou** | Cada arquivo é tipado como `code` · `test` · `docs` · `generated` · `config` · `vendor` · `binary`, então um lockfile ou um bump de `vendor/` nunca vira o assunto da sua mensagem de commit. |
| 🧭 **Vê o que o diff esconde** | Renomeações, mudanças de permissão, remoções e o *tamanho* de arquivos binários vêm do `git --stat --summary`, então um `git mv` é descrito como um move, não como uma reescrita. |
| 📐 **Justo em commits grandes** | Diffs que estouram o orçamento são cortados por arquivo, não no fim, então o último arquivo alterado nunca fica invisível para o modelo — e lockfiles e bumps de `vendor/` são reduzidos a uma linha, para não sufocarem a sua mudança de verdade. |

## Requisitos

- **Python 3.8+** — sem pacotes de terceiros
- **git** no `PATH`
- Uma **chave de API** — `OPENAI_API_KEY`, ou `ANTHROPIC_API_KEY` com `--provider anthropic`. Nenhuma chave com `--provider ollama`, que conversa com um modelo local.

## Início rápido

**1. Instale**

```bash
pipx install commitclerk    # recomendado
# ou
pip install commitclerk
```

Ou nem instale. O código-fonte é um pacote pequeno, e toda mudança é reconstruída em
um único arquivo autossuficiente, sem dependências, então isto também funciona:

```bash
curl -O https://raw.githubusercontent.com/alegauss/commitclerk/main/dist/commitclerk.py
python commitclerk.py --help
```

**2. Configure a chave**

```bash
# macOS / Linux
export OPENAI_API_KEY="sk-..."
```

```powershell
# Windows (PowerShell, persistindo para as próximas sessões)
setx OPENAI_API_KEY "sk-..."
```

**3. Faça o stage e commite**

```bash
git add .
clerk --dry-run   # confira antes
clerk             # ou: git clerk
```

## Uso

```
clerk [-m TÍTULO] [--dry-run] [--provider NOME] [--base-url URL] [--model MODELO]
      [--timeout S] [--max-chars N] [--no-house-style] [--version]
```

A instalação cria três pontos de entrada idênticos: `clerk`, `commitclerk` e
`git clerk` — o git roda qualquer `git-<nome>` do seu `PATH` como subcomando,
então `git add -A && git clerk` se lê como git, e não como um apêndice. Se
preferir rodar a partir de um clone do repositório, troque `clerk` por
`python -m commitclerk`; se você baixou o arquivo único, use `python commitclerk.py`.

| Flag | Padrão | O que faz |
|---|---|---|
| `-m`, `--message TÍTULO` | — | Usa `TÍTULO` literalmente como título do commit; a IA escreve apenas os bullets do corpo. |
| `--dry-run` | desligado | Imprime a mensagem gerada e sai sem commitar. |
| `--provider NOME` | `openai` (ou `$CLERK_PROVIDER`) | Qual provedor chamar: `openai`, `anthropic` ou `ollama` (local, sem chave). |
| `--base-url URL` | `https://api.openai.com/v1` (ou `$OPENAI_BASE_URL`) | Aponta para qualquer endpoint **compatível com a OpenAI** — Ollama, LM Studio, vLLM, llama.cpp, OpenRouter, Groq, Together, Azure. |
| `--model MODELO` | o padrão do provedor — `gpt-4o-mini` (ou `$OPENAI_MODEL`) no `openai` | Modelo a chamar. |
| `--timeout S` | `60` | Segundos de espera por requisição à API. Aumente para um modelo local lento. |
| `--max-chars N` | `60000` | Orçamento de caracteres do diff. Um diff maior é cortado **por arquivo**, de modo que todo arquivo alterado chega ao modelo; arquivos gerados e vendorizados são reduzidos antes a uma linha. |
| `--no-house-style` | desligado | Pula o `git log` que mede as convenções do próprio repositório. Útil quando o histórico é importado, gerado por máquina ou simplesmente não é um estilo que você queira copiar. |
| `--version` | — | Mostra a versão e sai. |

### Exemplos

```bash
# A IA escreve a mensagem inteira
clerk

# Você escolhe o título, a IA escreve o corpo — o modo mais confiável
clerk -m "refactor: extract retry policy into its own module"

# Apenas prévia, nunca commita
clerk --dry-run

# Um modelo mais forte para uma mudança grande ou sutil
clerk --model gpt-4o

# Diff muito grande: aumente o orçamento para cortar menos de cada arquivo
clerk --max-chars 120000

# Um modelo local, para o diff nunca sair da sua máquina — sem chave de API
clerk --provider ollama

# Um modelo local lento: espere mais por requisição
clerk --provider ollama --timeout 300

# Fork recente, com um histórico importado que você não quer copiar
clerk --no-house-style
```

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Commit feito (ou `--dry-run` imprimiu a mensagem). |
| `1` | Nada no stage — rode `git add` antes. |
| `2` | Problema de configuração — a chave da API do provedor não está definida, ou `--provider` aponta para um provedor que não existe. |
| outros | Repassados do `git commit`. |

## Wrappers

Dois atalhos fazem as mesmas três coisas: verificam a chave da API, adicionam tudo ao stage com `git add -A` e executam o `commitclerk` repassando os argumentos.

```bat
REM Windows
run-commit.cmd -m "feat: add CSV export to the reports page"
```

```bash
# macOS / Linux
./run-commit.sh -m "feat: add CSV export to the reports page"
```

Coloque o diretório do repositório (ou uma cópia do wrapper e do `commitclerk.py` baixado) no `PATH` para chamá-lo de qualquer repositório — os wrappers adicionam o próprio diretório ao `PYTHONPATH`, então os dois formatos funcionam.

> **Atenção:** os wrappers adicionam tudo ao stage, inclusive arquivos novos, removidos e começados por ponto. Se você prefere escolher o que entra no commit, faça o stage manualmente e chame `python -m commitclerk` direto. O código Python nunca faz stage sozinho.

> **Stage parcial:** se um arquivo no stage também tiver alterações não staged (típico do `git add -p`), o `commitclerk` avisa em uma linha no stderr — a mensagem descreve a versão que está no stage, não o arquivo em disco. É só aviso: nunca bloqueia.

Se você prefere não usar wrapper nenhum, um alias resolve:

```bash
alias ac='git add -A && clerk'
```

## Por que existe

A maioria dos geradores de mensagem de commit só enxerga o diff, e isso é um ponto cego real. Quando um commit adiciona texto a um `CHANGELOG`, `ROADMAP` ou `README` **descrevendo uma feature que foi entregue três commits atrás**, um gerador ingênuo lê esse texto e escreve:

```
feat: implement real-time collaboration
```

…para um commit que só mexeu em Markdown. Seu histórico passa a mentir, e o `git log --grep` e as ferramentas de release herdam a mentira.

O `commitclerk` trata isso de duas formas:

1. **Detecção de documentação, em dois sabores.** Se todo arquivo no stage é documentação — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, qualquer coisa em `docs/`, ou nomes conhecidos como `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — o prompt muda para um enquadramento de documentação: usa o prefixo `docs:` e descreve *a mudança na documentação em si* ("registrar X no changelog"), nunca "implementar X".

   O caso difícil é o commit **misto**, que também é o mais comum: uma entrada grande de CHANGELOG *mais* uma correção de uma linha. Nele, o prompt nomeia os arquivos de documentação, informa a fatia das linhas alteradas que é documentação, e instrui o modelo a tirar o prefixo do tipo apenas das linhas que não são documentação — então um ajuste de docstring ao lado de 48 linhas de changelog volta como `docs:`, não como `feat:`. Um commit que de fato implementa uma feature *e* a documenta continua recebendo `feat:`; a proteção confere o código, não apenas proíbe a palavra.

2. **`-m` como override.** Você sabe qual é a sua mudança. O `-m "<título>"` fixa o título e reduz o trabalho do modelo a resumir o diff. É o padrão recomendado para qualquer commit cuja intenção não é óbvia só pelo diff.

Há um segundo ponto cego: *proporção*. Uma correção de três linhas que também
regenera o `package-lock.json` é uma correção de bug, mas o lockfile é 12 000 linhas
do diff. O `commitclerk` classifica cada arquivo no stage — `code`, `test`, `docs`,
`generated`, `config`, `vendor`, `binary` —, anota a lista de arquivos com essas
classes e instrui o modelo a tirar o tipo do commit dos arquivos que são o *ponto*
da mudança, nunca fazendo de arquivos gerados, vendorizados ou binários o assunto.

A classificação também decide o que vale a pena enviar. O corpo do diff de um
arquivo gerado ou vendorizado é substituído por uma única linha que o nomeia e conta
suas alterações, e isso acontece *antes* do orçamento por arquivo, então o espaço
sobra para o código. Em um repositório real, um bump de lockfile com 300 pacotes ao
lado de uma correção de duas linhas caiu de 39 505 caracteres de diff para 342 — com
a correção de duas linhas intacta.

Há um terceiro ponto cego, estrutural: um diff unificado não diz que um arquivo foi
*renomeado* (a menos que o repositório tenha detecção de rename ligada), que a
permissão dele mudou, nem qual o tamanho de um arquivo binário. O `commitclerk`
envia `git diff --staged --find-renames --stat --summary` junto com o diff, então
esses fatos são afirmados em vez de adivinhados — e, como esse resumo é pequeno, ele
sobrevive inteiro mesmo quando um diff grande foi cortado.

O mesmo conjunto de regras mantém títulos no imperativo e abaixo de 72 caracteres, corpos com 2 a 6 bullets sobre o *porquê* em vez de repetir o diff arquivo por arquivo, e proíbe emojis, headers e blocos de código.

## Configuração

Ainda não existe arquivo de configuração. Tudo é flag ou variável de ambiente, e
**a flag sempre vence a variável**:

| Variável | Usada por | O que define |
|---|---|---|
| `OPENAI_API_KEY` | `openai` | A chave da API. Obrigatória; lida só do ambiente, nunca gravada em disco. |
| `OPENAI_MODEL` | `openai` | Modelo padrão, quando `--model` não é passado. |
| `OPENAI_BASE_URL` | `openai` | Endpoint padrão, quando `--base-url` não é passado. |
| `ANTHROPIC_API_KEY` | `anthropic` | A chave da API. Obrigatória com `--provider anthropic`. |
| `ANTHROPIC_MODEL` | `anthropic` | Modelo padrão, quando `--model` não é passado. |
| `ANTHROPIC_BASE_URL` | `anthropic` | Endpoint padrão, quando `--base-url` não é passado. |
| `OLLAMA_MODEL` | `ollama` | Modelo padrão, quando `--model` não é passado. |
| `OLLAMA_BASE_URL` | `ollama` | Endpoint padrão, quando `--base-url` não é passado. |
| `CLERK_PROVIDER` | todos | Provedor padrão, quando `--provider` não é passado. |

Os provedores são uma tabela de quatro campos no [`commitclerk/providers.py`](commitclerk/providers.py)
— URL, headers, payload da requisição e extrator da resposta. Adicionar um é
acrescentar uma entrada na tabela, não criar uma camada de abstração.

### Provedores

| `--provider` | Endpoint | Chave | Modelo padrão |
|---|---|---|---|
| `openai` | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `anthropic` | `https://api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |
| `ollama` | `http://localhost:11434/v1/chat/completions` | nenhuma | `qwen2.5-coder` |

```bash
# Anthropic, com o padrão barato
ANTHROPIC_API_KEY="sk-ant-..." clerk --provider anthropic

# Anthropic, modelo mais forte para uma mudança sutil
clerk --provider anthropic --model claude-opus-5 -m "refactor: split the retry policy out"

# Torne-o o padrão deste shell
export CLERK_PROVIDER=anthropic
```

Os dois padrões são deliberadamente modelos pequenos e baratos — uma mensagem de
commit é um resumo curto de um diff, não um problema de raciocínio, e isso roda em
todo commit. Use o `--model` quando a mudança for sutil o bastante para precisar.

```bash
# Fixe um modelo para um repositório, sem mexer no ambiente global
OPENAI_MODEL=gpt-4o clerk -m "fix: reject expired tokens on refresh"
```

### Endpoints compatíveis com a OpenAI

A maioria dos fornecedores fala o mesmo protocolo da OpenAI, então o `--base-url`
cobre todos eles sem código novo e sem dependência nova. Um servidor local do
Ollama já tem preset — `--provider ollama`, que aponta para o `localhost` e não
pede chave — então o `--base-url` serve para todo o resto:

```bash
# LM Studio (local)
OPENAI_API_KEY=lmstudio clerk --base-url http://localhost:1234/v1 --model seu-modelo-carregado

# Um gateway hospedado (OpenRouter, Groq, Together, Azure, …)
clerk --base-url https://openrouter.ai/api/v1 --model anthropic/claude-3.5-sonnet
```

Duas ressalvas honestas: modelos locais pequenos escrevem corpos visivelmente
piores que um modelo hospedado de ponta — o `-m "<título>"` ajuda muito nesses
casos — e um endpoint customizado é **outro destino para o seu diff**, então
aponte para algum lugar em que você confia.

## Privacidade e custo

- **Seu diff staged é enviado para a API que você configurou** — `https://api.openai.com/v1` por padrão, ou a API da Anthropic com `--provider anthropic`, ou o que `--base-url` apontar. Em um repositório cujo conteúdo não pode sair da sua máquina, use `--provider ollama` (modelo local, sem chave, nada pela rede) ou simplesmente não use a ferramenta ali. Confira a política da sua empresa antes.
- **Um resumo das suas *mensagens* de commit recentes também é enviado.** O bloco de house style leva contagens e formatos medidos a partir dos últimos 200 títulos e corpos — tipos, escopos, formato do corpo, tamanho mediano do título, chaves de trailer, idioma —, não as mensagens em si. Nomes de escopo e chaves de trailer são a exceção e aparecem literalmente, já que contá-los não serviria de nada. Nenhum diff, autor, e-mail, data ou SHA do histórico é lido. `--no-house-style` pula o `git log`.
- Nada além disso é transmitido, armazenado ou registrado pela ferramenta: sem telemetria, sem analytics, sem configuração remota.
- A chave da API é lida do ambiente e nunca é gravada em disco.
- O custo é uma única chamada à API por commit. Com o modelo padrão de qualquer um dos provedores e um diff típico, é uma fração de centavo.

## Roadmap

O backlog completo está em **[`docs/ROADMAP.md`](docs/ROADMAP.md)**, com a
justificativa de projeto de cada item em [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md)
e o posicionamento e os não-objetivos em [`docs/STRATEGY.md`](docs/STRATEGY.md).

Ideias que dariam boas primeiras contribuições:

- [ ] Instalador de hook `prepare-commit-msg` (T36)
- [ ] Modo `--edit` interativo, abrindo a mensagem no `$EDITOR` antes de commitar (T31)
- [ ] Arquivo de configuração com regras de commit por projeto (T25)
- [ ] `clerk --lint`: validar uma mensagem existente sem chamar a API, como hook `commit-msg` (T28)
- [ ] Um GIF ou asciinema de demonstração para o topo deste README (T49)

Pegue uma delas ou proponha a sua em uma [issue](https://github.com/alegauss/commitclerk/issues).

## Contribuindo

Contribuições são muito bem-vindas. Leia o [CONTRIBUTING.md](CONTRIBUTING.md) — em resumo: mantenha sem dependências, mantenha em um arquivo só, e abra uma issue antes de mudanças grandes.

Veja também o [Código de Conduta](CODE_OF_CONDUCT.md) e a [política de segurança](SECURITY.md).

## Licença

[MIT](LICENSE) © Alexandre Oliveira

---

<div align="center">
Se isso te livrar de mais um <code>git commit -m "fix stuff"</code>, deixe uma ⭐.
</div>
