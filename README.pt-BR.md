<div align="center">

# commitclerk

**Escreva mensagens de commit melhores com um comando — a partir do seu diff staged e de um LLM.**

[![PyPI](https://img.shields.io/pypi/v/commitclerk.svg)](https://pypi.org/project/commitclerk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-brightgreen.svg)](#requisitos)
[![CI](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml/badge.svg)](https://github.com/alegauss/commitclerk/actions/workflows/ci.yml)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org/)

[Início rápido](#início-rápido) · [Uso](#uso) · [Por que existe](#por-que-existe) · [Contribuindo](CONTRIBUTING.md) · [English](README.md)

</div>

---

Um *clerk* (escrivão) registra o que de fato aconteceu. O `commitclerk` lê o seu diff staged, pede ao LLM uma mensagem no padrão Conventional Commits, mostra o resultado e faz o commit — em um único arquivo Python com **zero dependências**, pequeno o bastante para você ler inteiro antes de deixá-lo perto do seu código.

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
| 📄 **Consciente de documentação** | Detecta commits só de documentação e evita descrever features já entregues como se fossem novas. Veja [Por que existe](#por-que-existe). |
| 🧾 **Conventional Commits** | Gera prefixos `feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:` / `build:` / `perf:`. |
| 👀 **Dry run** | `--dry-run` imprime a mensagem e não commita nada. |
| 🔧 **Independente de modelo** | Qualquer modelo da API Chat Completions via `--model` ou `$OPENAI_MODEL`. |

## Requisitos

- **Python 3.8+** — sem pacotes de terceiros
- **git** no `PATH`
- Uma **chave da API da OpenAI** em `OPENAI_API_KEY`

## Início rápido

**1. Instale**

```bash
pipx install commitclerk    # recomendado
# ou
pip install commitclerk
```

Ou nem instale — é um arquivo só, sem dependências, então isto também funciona:

```bash
curl -O https://raw.githubusercontent.com/alegauss/commitclerk/main/commitclerk.py
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
clerk [-m TÍTULO] [--dry-run] [--model MODELO] [--max-chars N] [--version]
```

A instalação cria três pontos de entrada idênticos: `clerk`, `commitclerk` e
`git clerk` — o git roda qualquer `git-<nome>` do seu `PATH` como subcomando,
então `git add -A && git clerk` se lê como git, e não como um apêndice. Se
preferir rodar o arquivo direto, troque `clerk` por `python commitclerk.py` em
todos os exemplos abaixo.

| Flag | Padrão | O que faz |
|---|---|---|
| `-m`, `--message TÍTULO` | — | Usa `TÍTULO` literalmente como título do commit; a IA escreve apenas os bullets do corpo. |
| `--dry-run` | desligado | Imprime a mensagem gerada e sai sem commitar. |
| `--model MODELO` | `gpt-4o-mini` (ou `$OPENAI_MODEL`) | Modelo da API Chat Completions. |
| `--max-chars N` | `60000` | Trunca o diff em `N` caracteres antes de enviar à API. |
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

# Diff muito grande: envie mais contexto
clerk --max-chars 120000
```

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Commit feito (ou `--dry-run` imprimiu a mensagem). |
| `1` | Nada no stage — rode `git add` antes. |
| `2` | `OPENAI_API_KEY` não está definida. |
| outros | Repassados do `git commit`. |

## Wrappers

Dois atalhos fazem as mesmas três coisas: verificam a chave da API, adicionam tudo ao stage com `git add -A` e chamam o `commitclerk.py` repassando os argumentos.

```bat
REM Windows
run-commit.cmd -m "feat: add CSV export to the reports page"
```

```bash
# macOS / Linux
./run-commit.sh -m "feat: add CSV export to the reports page"
```

Coloque o diretório do repositório (ou uma cópia do wrapper e do `commitclerk.py`) no `PATH` para chamá-lo de qualquer repositório.

> **Atenção:** os wrappers adicionam tudo ao stage, inclusive arquivos novos, removidos e começados por ponto. Se você prefere escolher o que entra no commit, faça o stage manualmente e chame `python commitclerk.py` direto. O script Python nunca faz stage sozinho.

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

1. **Detecção de commits só de documentação.** Se todo arquivo no stage é documentação — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, qualquer coisa em `docs/`, ou nomes conhecidos como `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — o prompt muda para um enquadramento de documentação: usa o prefixo `docs:` e descreve *a mudança na documentação em si* ("registrar X no changelog"), nunca "implementar X".

2. **`-m` como override.** Você sabe qual é a sua mudança. O `-m "<título>"` fixa o título e reduz o trabalho do modelo a resumir o diff. É o padrão recomendado para qualquer commit cuja intenção não é óbvia só pelo diff.

O mesmo conjunto de regras mantém títulos no imperativo e abaixo de 72 caracteres, corpos com 2 a 6 bullets sobre o *porquê* em vez de repetir o diff arquivo por arquivo, e proíbe emojis, headers e blocos de código.

## Privacidade e custo

- **Seu diff staged é enviado para a API da OpenAI.** Não use em repositórios cujo conteúdo não pode sair da sua máquina. Confira a política da sua empresa antes.
- Nada além disso é transmitido, armazenado ou registrado pela ferramenta: sem telemetria, sem analytics, sem configuração remota.
- A chave da API é lida do ambiente e nunca é gravada em disco.
- O custo é uma única chamada à API por commit. Com o `gpt-4o-mini` padrão e um diff típico, é uma fração de centavo.

## Roadmap

O backlog completo está em **[`docs/ROADMAP.md`](docs/ROADMAP.md)**, com a
justificativa de projeto de cada item em [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md)
e o posicionamento e os não-objetivos em [`docs/STRATEGY.md`](docs/STRATEGY.md).

Ideias que dariam boas primeiras contribuições:

- [ ] Instalador de hook `prepare-commit-msg` (T36)
- [ ] Suporte a outros provedores — Anthropic, Azure OpenAI, Ollama / modelos locais (T1–T4)
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
