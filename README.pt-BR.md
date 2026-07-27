<div align="center">

# ai-commit

**Escreva mensagens de commit melhores com um comando — a partir do seu diff staged e de um LLM.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Zero dependências](https://img.shields.io/badge/depend%C3%AAncias-zero-brightgreen.svg)](#requisitos)
[![CI](https://github.com/alegauss/ai-commit/actions/workflows/ci.yml/badge.svg)](https://github.com/alegauss/ai-commit/actions/workflows/ci.yml)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196.svg)](https://www.conventionalcommits.org/)

[Início rápido](#início-rápido) · [Uso](#uso) · [Por que existe](#por-que-existe) · [Contribuindo](CONTRIBUTING.md) · [English](README.md)

</div>

---

O `ai-commit` é um único arquivo Python — **sem pacotes para instalar, sem virtualenv, sem lockfile**. Ele lê o seu diff staged, pede ao LLM uma mensagem no padrão Conventional Commits, mostra o resultado e faz o commit.

```console
$ git add .
$ python ai_commit.py

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

**1. Obtenha o script**

```bash
git clone https://github.com/alegauss/ai-commit.git
cd ai-commit
```

Ou baixe só o arquivo:

```bash
curl -O https://raw.githubusercontent.com/alegauss/ai-commit/main/ai_commit.py
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
python ai_commit.py --dry-run   # confira antes
python ai_commit.py
```

## Uso

```
python ai_commit.py [-m TÍTULO] [--dry-run] [--model MODELO] [--max-chars N]
```

| Flag | Padrão | O que faz |
|---|---|---|
| `-m`, `--message TÍTULO` | — | Usa `TÍTULO` literalmente como título do commit; a IA escreve apenas os bullets do corpo. |
| `--dry-run` | desligado | Imprime a mensagem gerada e sai sem commitar. |
| `--model MODELO` | `gpt-4o-mini` (ou `$OPENAI_MODEL`) | Modelo da API Chat Completions. |
| `--max-chars N` | `60000` | Trunca o diff em `N` caracteres antes de enviar à API. |

### Exemplos

```bash
# A IA escreve a mensagem inteira
python ai_commit.py

# Você escolhe o título, a IA escreve o corpo — o modo mais confiável
python ai_commit.py -m "refactor: extract retry policy into its own module"

# Apenas prévia, nunca commita
python ai_commit.py --dry-run

# Um modelo mais forte para uma mudança grande ou sutil
python ai_commit.py --model gpt-4o

# Diff muito grande: envie mais contexto
python ai_commit.py --max-chars 120000
```

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Commit feito (ou `--dry-run` imprimiu a mensagem). |
| `1` | Nada no stage — rode `git add` antes. |
| `2` | `OPENAI_API_KEY` não está definida. |
| outros | Repassados do `git commit`. |

## Wrapper para Windows

O `run-commit.cmd` é um atalho para Windows: verifica a chave da API, roda `git add *` e chama o `ai_commit.py` repassando os argumentos.

```bat
run-commit.cmd -m "feat: add CSV export to the reports page"
```

Coloque o diretório do repositório (ou uma cópia dos dois arquivos) no `PATH` para chamá-lo de qualquer repositório.

> **Atenção:** o wrapper adiciona tudo ao stage com `git add *`. Se você prefere escolher o que entra no commit, faça o stage manualmente e chame `python ai_commit.py` direto. O script Python nunca faz stage sozinho.

No macOS e no Linux, use o script diretamente — um alias resolve:

```bash
alias aic='git add -A && python /caminho/para/ai_commit.py'
```

## Por que existe

A maioria dos geradores de mensagem de commit só enxerga o diff, e isso é um ponto cego real. Quando um commit adiciona texto a um `CHANGELOG`, `ROADMAP` ou `README` **descrevendo uma feature que foi entregue três commits atrás**, um gerador ingênuo lê esse texto e escreve:

```
feat: implement real-time collaboration
```

…para um commit que só mexeu em Markdown. Seu histórico passa a mentir, e o `git log --grep` e as ferramentas de release herdam a mentira.

O `ai-commit` trata isso de duas formas:

1. **Detecção de commits só de documentação.** Se todo arquivo no stage é documentação — `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, qualquer coisa em `docs/`, ou nomes conhecidos como `CHANGELOG`/`README`/`ROADMAP`/`CONTRIBUTING` — o prompt muda para um enquadramento de documentação: usa o prefixo `docs:` e descreve *a mudança na documentação em si* ("registrar X no changelog"), nunca "implementar X".

2. **`-m` como override.** Você sabe qual é a sua mudança. O `-m "<título>"` fixa o título e reduz o trabalho do modelo a resumir o diff. É o padrão recomendado para qualquer commit cuja intenção não é óbvia só pelo diff.

O mesmo conjunto de regras mantém títulos no imperativo e abaixo de 72 caracteres, corpos com 2 a 6 bullets sobre o *porquê* em vez de repetir o diff arquivo por arquivo, e proíbe emojis, headers e blocos de código.

## Privacidade e custo

- **Seu diff staged é enviado para a API da OpenAI.** Não use em repositórios cujo conteúdo não pode sair da sua máquina. Confira a política da sua empresa antes.
- Nada além disso é transmitido, armazenado ou registrado pela ferramenta: sem telemetria, sem analytics, sem configuração remota.
- A chave da API é lida do ambiente e nunca é gravada em disco.
- O custo é uma única chamada à API por commit. Com o `gpt-4o-mini` padrão e um diff típico, é uma fração de centavo.

## Roadmap

Ideias que dariam boas primeiras contribuições:

- [ ] Um wrapper `run-commit.sh` para POSIX equivalente ao `run-commit.cmd`
- [ ] Instalador de hook `prepare-commit-msg`
- [ ] Suporte a outros provedores (Anthropic, Azure OpenAI, Ollama / modelos locais)
- [ ] Modo `--edit` interativo, abrindo a mensagem no `$EDITOR` antes de commitar
- [ ] Arquivo de configuração com regras de commit por projeto

Pegue uma delas ou proponha a sua em uma [issue](https://github.com/alegauss/ai-commit/issues).

## Contribuindo

Contribuições são muito bem-vindas. Leia o [CONTRIBUTING.md](CONTRIBUTING.md) — em resumo: mantenha sem dependências, mantenha em um arquivo só, e abra uma issue antes de mudanças grandes.

Veja também o [Código de Conduta](CODE_OF_CONDUCT.md) e a [política de segurança](SECURITY.md).

## Licença

[MIT](LICENSE) © Alexandre Oliveira

---

<div align="center">
Se isso te livrar de mais um <code>git commit -m "fix stuff"</code>, deixe uma ⭐.
</div>
