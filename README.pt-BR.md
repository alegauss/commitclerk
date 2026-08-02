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
| 🏠 **Escreve como o seu repositório** | Lê os seus últimos 200 commits para aprender os tipos, escopos, formato de corpo e idioma que o seu time realmente usa, e mostra ao modelo os commits passados que mexeram nesses mesmos arquivos como exemplos. A mensagem pertence ao *seu* histórico em vez de ser genericamente correta. Local, sem chamada extra à API. |
| 📦 **Escopo ciente de monorepo** | Cada arquivo no stage é rastreado até o manifesto de workspace mais próximo, então uma mudança contida em um pacote vira `fix(billing-api): …`. Espalhada por vários pacotes, ela se recusa a nomear um e esconder o resto. |
| 👀 **Dry run** | `--dry-run` imprime a mensagem e não commita nada. |
| 🔧 **Independente de modelo** | OpenAI, Anthropic ou um modelo local do Ollama via `--provider`, qualquer modelo via `--model`, e qualquer endpoint compatível com a OpenAI via `--base-url`. |
| 💬 **Você pode dizer o porquê** | `--context "this reverts the caching experiment"` para um commit, e um `.clerk/context.md` commitado para os fatos permanentes do repositório. A única coisa que um diff nunca mostra, dita uma vez em vez de adivinhada. |
| ⚙️ **Configuração por projeto** | Um `.clerk.json` commitado escolhe provedor, modelo, endpoint e orçamentos para o time inteiro, então a convenção deixa de ser flags que cada pessoa redigita. Flags e variáveis de ambiente continuam vencendo. |
| 🎫 **Trailers de ticket** | Ligue o `ticket_refs` e a chave da issue no seu branch (`feat/PROJ-123-…`) vira um trailer `Refs: PROJ-123` — Jira, Linear e GitHub de fábrica. Desligado por padrão, e lido do branch em vez de pedido ao modelo, então não há como ser inventado. |
| 🚫 **Veto por arquivo, não por repositório** | Um `.clerkignore` (mesma sintaxe do `.gitignore`) retém o **conteúdo** do arquivo que casar: o modelo recebe o nome, as contagens de linha e um placeholder. É isso que permite a um time de segurança dizer sim a um repo com três arquivos sensíveis, em vez de não ao repo inteiro. Roda antes do scan de segredos, então também é a saída limpa para um falso positivo. |
| ✈️ **Funciona com a rede fora** | O `--offline` escreve uma mensagem determinística sem chamada de API, sem chave e sem modelo — tipo pelas classes de arquivo, escopo pelo manifest do workspace, bullets agrupados por diretório. Nunca chuta `feat:` nem `fix:`, então é rascunho, não substituto. Uma queda da API ou uma chave vencida deixa de quebrar o fluxo de git. |
| 🛡️ **Se recusa a vazar um segredo** | Um `.env` no stage é escaneado *antes* da primeira requisição, não depois: formatos conhecidos de chave e tokens de alta entropia em linhas adicionadas param a execução com o código de saída `3`, nomeando arquivo e linha e nunca o próprio trecho. Esta ferramenta fica a montante de todo hook de secret-scanning que você já tem, então era justamente o ponto cego. `--redact` mascara em vez de recusar; `--no-scan` desliga. |
| 🔒 **Funciona offline, se você quiser** | `--provider ollama` não precisa de chave de API e fala com o `localhost` — seu diff nunca sai da máquina. |
| 🔁 **Sobrevive a um rate limit** | Respostas transitórias (`429`/`5xx`) são repetidas com backoff e jitter, respeitando o `Retry-After`, em vez de perder o commit — e, se o modelo rejeitar um parâmetro, a requisição é corrigida e reenviada. |
| 🗂️ **Classifica o que mudou** | Cada arquivo é tipado como `code` · `test` · `docs` · `generated` · `config` · `vendor` · `binary`, então um lockfile ou um bump de `vendor/` nunca vira o assunto da sua mensagem de commit. |
| 🧭 **Vê o que o diff esconde** | Renomeações, mudanças de permissão, remoções e o *tamanho* de arquivos binários vêm do `git --stat --summary`, então um `git mv` é descrito como um move, não como uma reescrita. |
| 📐 **Justo em commits grandes** | Diffs que estouram o orçamento são cortados por arquivo, não no fim, então o último arquivo alterado nunca fica invisível para o modelo — e lockfiles e bumps de `vendor/` são reduzidos a uma linha, para não sufocarem a sua mudança de verdade. |
| 🔬 **Vai além da janela de contexto** | Para o commit de 5 000 linhas que não cabe em orçamento nenhum, o `--deep` resume cada arquivo grande demais em uma requisição barata só dele e escreve a mensagem a partir desses resumos mais os diffs reais dos arquivos menores — assim o final da mudança é *descrito* em vez de cortado fora. Opcional, porque custa uma requisição por arquivo grande. |

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
clerk [-m TÍTULO] [--context NOTA] [--dry-run] [--provider NOME] [--base-url URL]
      [--model MODELO] [--timeout S] [--max-chars N] [--deep] [--no-house-style]
      [--no-examples] [--redact] [--no-scan] [--offline] [--version]
```

A instalação cria três pontos de entrada idênticos: `clerk`, `commitclerk` e
`git clerk` — o git roda qualquer `git-<nome>` do seu `PATH` como subcomando,
então `git add -A && git clerk` se lê como git, e não como um apêndice. Se
preferir rodar a partir de um clone do repositório, troque `clerk` por
`python -m commitclerk`; se você baixou o arquivo único, use `python commitclerk.py`.

| Flag | Padrão | O que faz |
|---|---|---|
| `-m`, `--message TÍTULO` | — | Usa `TÍTULO` literalmente como título do commit; a IA escreve apenas os bullets do corpo. |
| `--context NOTA` | — | Uma frase de intenção que o diff não mostra, por exemplo `"this reverts the caching experiment"`. Fatos permanentes do repositório vão no `.clerk/context.md`. |
| `--dry-run` | desligado | Imprime a mensagem gerada e sai sem commitar. |
| `--provider NOME` | `openai` (ou `$CLERK_PROVIDER`) | Qual provedor chamar: `openai`, `anthropic` ou `ollama` (local, sem chave). |
| `--base-url URL` | `https://api.openai.com/v1` (ou `$OPENAI_BASE_URL`) | Aponta para qualquer endpoint **compatível com a OpenAI** — Ollama, LM Studio, vLLM, llama.cpp, OpenRouter, Groq, Together, Azure. |
| `--model MODELO` | o padrão do provedor — `gpt-4o-mini` (ou `$OPENAI_MODEL`) no `openai` | Modelo a chamar. |
| `--timeout S` | `60` | Segundos de espera por requisição à API. Aumente para um modelo local lento. |
| `--max-chars N` | `60000` | Orçamento de caracteres do diff. Um diff maior é cortado **por arquivo**, de modo que todo arquivo alterado chega ao modelo; arquivos gerados e vendorizados são reduzidos antes a uma linha. |
| `--deep` | desligado | Para o commit que não cabe em orçamento nenhum: resume cada arquivo **grande demais** em uma requisição barata só dele e depois escreve a mensagem a partir desses resumos mais os diffs reais dos arquivos menores. Custa uma requisição extra por arquivo grande — e nada quando o diff já cabe. |
| `--no-house-style` | desligado | Pula o `git log` por trás tanto do fingerprint de house style quanto dos exemplos extraídos do histórico. Útil quando o histórico é importado ou gerado por máquina, ou para manter o texto de mensagens antigas fora da rede. |
| `--no-examples` | desligado | Não envia **texto** de mensagens de commit antigas, mas mantém o fingerprint, que leva apenas contagens e formatos. É a metade estreita do `--no-house-style`, para um time que aceita compartilhar uma estatística sobre o próprio histórico, mas não o histórico. Implícito no `--no-house-style`. |
| `--offline` | desligado | Escreve a mensagem localmente: sem chamada de API, sem chave, sem rede. Tipo pelas classes de arquivo, escopo pelo manifest do workspace, bullets agrupados por diretório. **Nunca** emite `feat:` nem `fix:` — esses afirmam intenção, que nada local enxerga —, então trate como rascunho. Útil no avião, durante uma queda da API ou com a chave vencida. |
| `--redact` | desligado | Quando o scan pré-envio encontra um suspeito de segredo, mascara na requisição e segue em frente em vez de recusar. **O commit não muda e continua contendo o segredo** — isto protege o que é enviado, não o que é commitado. |
| `--no-scan` | desligado | Não escaneia o diff staged em busca de segredos antes de enviá-lo. Desliga o `--redact` junto, já que não sobra nada para mascarar. |
| `--version` | — | Mostra a versão e sai. |

Todo padrão dessa tabela também pode vir de um [arquivo de
configuração](#configuração) — `.clerk.json` no repositório, ou
`~/.config/clerk/config.json` para a sua máquina. Uma flag sempre vence os dois.

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

# Um commit de 5000 linhas que não cabe em orçamento nenhum: resuma os arquivos
# grandes em vez de cortá-los, para o final da mudança também ser descrito
clerk --deep

# Um modelo local, para o diff nunca sair da sua máquina — sem chave de API
clerk --provider ollama

# Um modelo local lento: espere mais por requisição
clerk --provider ollama --timeout 300

# Fork recente, com um histórico importado que você não quer copiar
clerk --no-house-style

# Copie as convenções, mas mantenha o texto das mensagens antigas fora da rede
clerk --no-examples

# O scan apontou algo que você sabe ser um fixture: mascare e siga em frente
# (o commit continua contendo — isto só protege a requisição)
clerk --redact

# No avião, durante uma queda ou com a chave vencida: rascunho local determinístico
clerk --offline

# Offline, mas você sabe a intenção — o melhor dos dois, e ainda sem chamada de API
clerk --offline -m "fix: stop the retry storm"

# Diga a única coisa que o diff não mostra
clerk --context "this reverts the caching experiment we ran last sprint"

# Fixe a escolha do time uma vez, no repositório, em vez de a cada commit
echo '{"provider": "anthropic", "timeout": 120}' > .clerk.json
```

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Commit feito (ou `--dry-run` imprimiu a mensagem). |
| `1` | Nada no stage — rode `git add` antes. |
| `2` | Problema de configuração — a chave da API do provedor não está definida, `--provider` aponta para um provedor que não existe, ou um arquivo de configuração não pode ser lido como está escrito. |
| `3` | O scan pré-envio encontrou um suspeito de segredo no diff staged. **Nada foi enviado.** Tem código próprio para que um wrapper consiga distinguir "você quase vazou uma chave" de "sua chave de API não está definida". |
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

Ainda assim, existe um commit que orçamento nenhum resolve: um upgrade vendorizado,
uma passada de formatador, uma refatoração enorme. Repartir 60 000 caracteres com
justiça entre doze arquivos gigantes mostra ao modelo os primeiros 5% de cada um, e
todo o resto vira um marcador de corte sobre o qual a mensagem só pode ficar calada.
Para esse caso existe o `--deep`: cada arquivo que o repartidor por arquivo estava
prestes a cortar ganha uma requisição barata só dele, responde em no máximo duas
linhas, e a mensagem final é escrita a partir desses resumos mais os diffs **reais**
dos arquivos menores. São N+1 requisições, por isso é opcional — e um commit que já
cabe no orçamento não gasta nenhuma. Um resumo que não puder ser obtido nunca é
inventado: aquele arquivo volta a ser cortado como sempre foi, e a falha é avisada
na saída de erro.

Há um terceiro ponto cego, estrutural: um diff unificado não diz que um arquivo foi
*renomeado* (a menos que o repositório tenha detecção de rename ligada), que a
permissão dele mudou, nem qual o tamanho de um arquivo binário. O `commitclerk`
envia `git diff --staged --find-renames --stat --summary` junto com o diff, então
esses fatos são afirmados em vez de adivinhados — e, como esse resumo é pequeno, ele
sobrevive inteiro mesmo quando um diff grande foi cortado.

O mesmo conjunto de regras mantém títulos no imperativo e abaixo de 72 caracteres, corpos com 2 a 6 bullets sobre o *porquê* em vez de repetir o diff arquivo por arquivo, e proíbe emojis, headers e blocos de código.

## Configuração

Um ajuste pode vir de cinco lugares. Eles são consultados em uma ordem fixa, e o
primeiro que tiver resposta vence:

**flag de linha de comando → variável de ambiente → `.clerk.json` no repositório →
`~/.config/clerk/config.json` → padrão embutido**

### O arquivo de configuração

O `.clerk.json` fica na **raiz do repositório** e existe para ser commitado: é
assim que a convenção de um time deixa de ser flags que cada pessoa redigita. O
mesmo arquivo em `~/.config/clerk/config.json` define os seus padrões pessoais em
todos os repositórios, e qualquer projeto que discorde sobrescreve.

```json
{
  "provider": "anthropic",
  "model": "claude-haiku-4-5",
  "timeout": 120,
  "max_chars": 90000,
  "house_style": true
}
```

| Chave | Tipo | Flag equivalente |
|---|---|---|
| `provider` | string | `--provider` |
| `model` | string | `--model` |
| `base_url` | string | `--base-url` |
| `timeout` | número | `--timeout` |
| `max_chars` | número | `--max-chars` |
| `scan` | booleano | `false` é `--no-scan` (a única configuração cujo padrão é **ligado**) |
| `house_style` | booleano | `false` é `--no-house-style` |
| `examples` | booleano | `false` é `--no-examples` (ignorado sob `"house_style": false`, que já recusa as duas coisas) |
| `deep` | booleano | `true` é `--deep` |
| `ticket_refs` | booleano | — (desligado por padrão; veja abaixo) |
| `ticket_pattern` | string | — (implica `ticket_refs`) |
| `assisted_by` | booleano | — (desligado por padrão; adiciona um trailer `Assisted-by:`, veja abaixo) |

O arquivo é procurado a partir da raiz do repositório, não do diretório em que
você está, então a ferramenta se comporta igual três níveis abaixo. Chaves de API
**não** são ajustes: são lidas apenas do ambiente, nunca de um arquivo. Uma chave
que a ferramenta não conhece é reportada no stderr e ignorada, para que uma
configuração escrita para uma versão mais nova continue funcionando; um arquivo
que não é JSON válido, ou um valor de tipo errado, é erro (saída `2`) em vez de um
ajuste descartado em silêncio.

> Um `.clerk.json` commitado pode definir `base_url`, que é **para onde o seu diff
> é enviado**. Leia-o como leria qualquer outro arquivo de onde você executa
> código — veja o [SECURITY.md](SECURITY.md).

### Mantendo o conteúdo de um arquivo fora da rede

Um repositório com três arquivos sensíveis não deveria ter que recusar a
ferramenta inteira. O `.clerkignore` na raiz do repositório move essa decisão
para **por arquivo**:

```gitignore
# .clerkignore — mesma sintaxe do .gitignore
secrets/
*.env
!.env.example
config/production.json
```

Um arquivo que casa mantém o cabeçalho do diff e as contagens de linha, e perde
o corpo. O modelo vê `- secrets/prod.env (config, excluded)` na lista de arquivos
e `[... excluded by .clerkignore, +12 -3, contents not shown ...]` onde estaria o
diff, então a mensagem pode dizer que o arquivo mudou sem o conteúdo dele sair da
máquina.

> **Os caminhos continuam sendo enviados.** Só o conteúdo é retido. Se o *nome* do
> arquivo também não pode ser revelado, use `--offline`, que não faz requisição
> nenhuma, ou simplesmente não rode a ferramenta naquele repositório.

Ele roda **antes** do scan de segredos, o que faz dele a saída limpa para um falso
positivo: conteúdo que nunca é transmitido não tem sobre o que ser recusado, então
você não precisa desligar o scan inteiro com `--no-scan`.

Suportado: comentários com `#`, linhas em branco, negação com `!` (vence a última
regra que casar), padrões ancorados com `/`, `/` no fim para diretório, `*` (para
numa `/`) e `**` (não para). O que esse subconjunto não consegue honrar — uma barra
invertida como separador, uma regra que não casa com nada — é **erro** (saída `2`)
nomeando a linha, nunca um padrão que silenciosamente não faz nada. Regra que não
faz nada é arquivo transmitido sem querer.

Como o `.clerk.json`, é procurado a partir da raiz do repositório e feito para ser
commitado: a exclusão é uma propriedade do repositório, e uma cópia pessoal
significaria que a execução de um colega transmite o que a sua reteve.

### Dizendo o que o diff não mostra

Um diff mostra *o que* mudou. Ele nunca mostra o porquê, e nenhuma leitura o
recupera. Duas formas de dizer:

```bash
# Desta vez
clerk --context "this reverts the caching experiment we ran last sprint"
```

```
.clerk/context.md   — fatos permanentes, commitados junto com o repositório

  A CLI instala como `clerk`; o produto se chama commitclerk.
  Tudo em docs/ é interno e não é publicado.
  A gente faz deploy às quintas, então um hotfix na sexta é incomum.
```

O `--context` é para este commit; o `.clerk/context.md` é para todos, lido
literalmente a cada execução. Os dois são estritamente aditivos ao prompt — só
informam a mensagem, nunca mudam o que a ferramenta faz — e ambos vêm com a
instrução de explicar o *porquê* em vez de virarem trabalho que este commit teria
feito. Mantenha o arquivo com poucas linhas: ele sai do mesmo orçamento do
`--max-chars` que o diff, e é cortado em 2 000 caracteres.

### Trailers de ticket

O nome do seu branch quase sempre já diz em qual ticket você está, e o diff nunca
diz. Ligue o `ticket_refs` e a chave da issue no branch vira um trailer `Refs:`,
para o vínculo entre o commit e o ticket deixar de ser redigitado:

```json
{ "ticket_refs": true }
```

```
Branch:  feat/PROJ-123-retry-webhooks

feat(webhooks): retry a failed delivery three times

- because a single 5xx should not drop the event

Refs: PROJ-123
```

O padrão embutido é `[A-Z]{2,10}-\d+|#\d+`, que cobre Jira, Linear e GitHub.
Defina `ticket_pattern` com a sua própria regex para qualquer outro formato —
fazer isso já liga o recurso, então não há uma segunda chave para lembrar. Isso
vem **desligado até você pedir**: um `Refs:` num repositório sem rastreador é
ruído, e a ferramenta não acrescenta cerimônia ao seu histórico sem ser chamada.

A chave é lida do branch e anexada à mensagem pronta, nunca enviada ao modelo, então
não há como ser parafraseada ou inventada. Um branch sem chave não gera trailer, um
trailer que você já escreveu não é repetido, e um bloco de trailers existente é
completado em vez de duplicado.

### Registrando que um commit teve assistência de IA

Algumas organizações já exigem isso. Com `"assisted_by": true`, a mensagem final
ganha um trailer:

```
Assisted-by: commitclerk 0.2.1 (gpt-4o-mini)
```

**Desligado por padrão, e sem flag** — pelo mesmo motivo que o `ticket_refs` não
tem uma. Se o seu histórico carrega proveniência é algo que o repositório decide
uma vez, não algo que cada commit reabre, e uma marca d'água não solicitada no
git log de outra pessoa é um non-goal deste projeto.

O `--offline` não chama modelo nenhum, então ele diz isso:

```
Assisted-by: commitclerk 0.2.1 (offline, no model)
```

Nomear um modelo ali seria a ferramenta registrando trabalho que não aconteceu,
que é a única coisa que ela existe para não fazer — e mantém os dois casos
distinguíveis para o `git log --grep="Assisted-by"`, que é o motivo inteiro de
registrar.

A chave é fixa e não configurável: uma que variasse por repositório derrubaria
esse grep. Com o `ticket_refs` também ligado, o `Refs:` vem primeiro — aquele é
sobre o trabalho, este sobre como a mensagem foi escrita. Os dois são anexados
depois que o modelo respondeu, então nenhum pode ser parafraseado ou inventado, e
uma re-execução não repete nenhum dos dois.

### Variáveis de ambiente

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

- **Conteúdo do repositório é enviado como dado, não como instrução.** Um contribuidor pode escrever `Ignore previous instructions…` num comentário, e uma mensagem de commit antiga pode carregar a mesma carga e ser reenviada a cada commit futuro perto daqueles arquivos. As duas regiões são cercadas por um sentinela nomeado pelo sha256 do que ele envolve — o conteúdo não consegue fechar a própria cerca — e todo system prompt diz que texto cercado é material a descrever, nunca instrução a obedecer. Isso aumenta o custo de uma injeção; não é prova, e o [`SECURITY.md`](SECURITY.md#prompt-injection-from-repository-content) documenta a ameaça e os limites em vez de omiti-los.
- **Um `.clerkignore` retém o conteúdo de um arquivo por inteiro.** Mesma sintaxe do `.gitignore`, lido da raiz do repositório. Um arquivo que casa chega ao modelo como caminho, contagens de linha e um placeholder `[... excluded ...]` — nunca o corpo. Aplicado antes do scan de segredos e antes de qualquer requisição. **Os caminhos em si continuam sendo enviados**; só o conteúdo é retido. Veja [Mantendo o conteúdo de um arquivo fora da rede](#mantendo-o-conteúdo-de-um-arquivo-fora-da-rede).
- **Nada é enviado antes de o diff staged ser escaneado em busca de segredos.** Antes da primeira requisição, toda linha *adicionada* é checada contra formatos conhecidos de credencial (`sk-`, `ghp_`, `github_pat_`, `AKIA`, `xox…`, `AIza`, `-----BEGIN … PRIVATE KEY-----`, JWTs) e contra tokens de alta entropia. Um acerto **recusa a execução** com código de saída `3`, nomeando o arquivo, a linha e qual detector disparou — nunca o trecho em si, porque um terminal é justamente de onde um segredo acaba copiado. Isso roda sobre o diff *como está no stage*, antes do corte e antes das requisições extras do `--deep`, então não existe caminho que envie primeiro e cheque depois. `--redact` mascara e continua; `--no-scan` ou `"scan": false` desliga.
- **Seu diff staged é enviado para a API que você configurou** — `https://api.openai.com/v1` por padrão, ou a API da Anthropic com `--provider anthropic`, ou o que `--base-url` ou um `.clerk.json` do repositório apontar. Em um repositório cujo conteúdo não pode sair da sua máquina, use `--provider ollama` (modelo local, sem chave, nada pela rede) ou simplesmente não use a ferramenta ali. Confira a política da sua empresa antes.
- **Algumas das suas *mensagens* de commit recentes também são enviadas.** O bloco de house style leva contagens e formatos medidos a partir dos últimos 200 títulos e corpos — tipos, escopos, formato do corpo, tamanho mediano do título, chaves de trailer, idioma —, não as mensagens em si, exceto nomes de escopo e chaves de trailer, que aparecem literalmente porque contá-los não serviria de nada. Além disso, os dois ou três commits passados que mexeram nos mesmos arquivos do seu diff staged são enviados **literalmente** como exemplos de estilo: título mais corpo cortado em 400 caracteres, com os blocos de trailer (e os e-mails dentro deles) removidos antes. Nenhum diff, autor, e-mail, data ou SHA do histórico é lido. São dois fluxos de dados diferentes e cada um tem a sua chave: `--no-examples` corta as mensagens literais e mantém as contagens, e `--no-house-style` pula o `git log` e as duas coisas.
- Nada além disso é transmitido, armazenado ou registrado pela ferramenta: sem telemetria, sem analytics, sem configuração remota.
- A chave da API é lida do ambiente e nunca é gravada em disco.
- O custo é uma única chamada à API por commit. Com o modelo padrão de qualquer um dos provedores e um diff típico, é uma fração de centavo.
- **O `--deep` muda esses dois números.** Ele gasta uma requisição extra por arquivo grande demais para o orçamento, e cada uma dessas requisições leva o diff daquele arquivo **inteiro**, em vez da fatia cortada que o `--max-chars` teria enviado. Mesmo endpoint, mesma chave, mesmo provedor — mais código seu, e N+1 chamadas em vez de uma. É desligado por padrão exatamente por isso, e um commit que já cabe no orçamento não dispara nada disso.

## Roadmap

O backlog completo está em **[`docs/ROADMAP.md`](docs/ROADMAP.md)**, com a
justificativa de projeto de cada item em [`docs/IMPROVEMENTS.md`](docs/IMPROVEMENTS.md)
e o posicionamento e os não-objetivos em [`docs/STRATEGY.md`](docs/STRATEGY.md).

Ideias que dariam boas primeiras contribuições:

- [ ] Instalador de hook `prepare-commit-msg` (T36)
- [ ] Modo `--edit` interativo, abrindo a mensagem no `$EDITOR` antes de commitar (T31)
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
