# fj AI-Native Natural Language Auto Completion

## Design Proposal v1.0

---

# Vision

Traditional CLI completion predicts **the next token**.

```
git checkout ma<TAB>
```

↓

```
main
master
```

`fj` should instead predict **the user's intent**.

```
fj summarize<TAB>
```

↓

```
summarize this repository

summarize the current file

summarize recent commits

summarize this pull request
```

Or even

```
fj<TAB>
```

↓

```
explain this project

find all TODOs

review recent changes

generate architecture documentation
```

The objective is to transform **Tab** into an **AI-powered command prediction engine**, similar to GitHub Copilot but optimized for CLI workflows.

---

# Goals

## Primary

Predict what the user wants to accomplish rather than how they type it.

## Secondary

* complete partial natural language
* leverage project context
* remain responsive (<300ms perceived latency)
* preserve traditional shell completion when appropriate
* continuously improve from user behavior

---

# Non-goals

* Replacing shell parsing
* Generating arbitrary shell commands
* Acting as a chat interface
* Performing task execution during completion

Completion predicts only.

Execution begins after Enter.

---

# High-Level Architecture

```
                  +----------------+
                  |  Bash / Zsh    |
                  +-------+--------+
                          |
                      Press TAB
                          |
             shell completion protocol
                          |
                   fj __complete
                          |
        +-----------------+-----------------+
        |                                   |
        |        Completion Engine          |
        |                                   |
        +-----------------+-----------------+
                          |
          +---------------+---------------+
          |               |               |
          |               |               |
     Context         Candidate       Ranking
     Builder         Providers       Engine
          |               |               |
          +---------------+---------------+
                          |
                   Completion List
                          |
                    Shell Displays
```

---

# Completion Pipeline

```
TAB

↓

Collect Context

↓

Determine Completion Mode

↓

Generate Candidates

↓

Rank

↓

Deduplicate

↓

Return Top K
```

---

# Completion Modes

## Mode 1 — Static

Traditional completion.

```
fj --m<TAB>

↓

--model
```

No LLM.

Latency <10ms.

---

## Mode 2 — Intent Completion (Primary)

```
fj explain memo<TAB>
```

↓

```
memory management

memory leak

memorization algorithm

memory hierarchy

memory allocator
```

---

## Mode 3 — Task Prediction

Input

```
fj
```

↓

```
summarize this repository

review staged changes

find dead code

generate README

explain project architecture
```

This becomes the default experience.

---

# Context Builder

The completion engine should never rely only on the current command.

Instead it constructs a rich execution context.

```
CompletionContext
```

Example

```python
class CompletionContext:

    cwd

    git_repo

    git_branch

    staged_files

    modified_files

    current_directory_files

    language

    project_type

    editor

    open_files

    recent_history

    clipboard

    terminal_size

    operating_system

    time_of_day

    previous_completion
```

Not every provider uses every field.

---

# Context Providers

## Repository

```
Git repository

Branch

HEAD

Recent commits

Git status
```

---

## Filesystem

```
Current directory

Nearby files

Ignored files

Project root
```

---

## Language Detection

```
Python

Rust

Go

Java

C++
```

---

## IDE Context (optional)

Future integrations

```
VSCode

Cursor

JetBrains
```

Provide

* active file
* selection
* diagnostics

---

## History

Recent commands

```
fj summarize README

fj explain src/api.py

fj review PR
```

Useful for personalization.

---

# Candidate Providers

Every provider independently proposes candidates.

```
Provider

↓

Candidates
```

## 1. Static Provider

```
help

version

config

login
```

---

## 2. History Provider

Learns frequently used prompts.

```
summarize repository

review PR

fix tests
```

---

## 3. File Provider

Current project files.

```
README.md

docs/

src/

tests/
```

---

## 4. Git Provider

```
current branch

latest commit

PR title

modified files
```

---

## 5. LLM Provider

The most important provider.

Input

```
Context

+

Current text
```

Output

```
Top N predicted user intents
```

---

# Prompt Design

System Prompt

```
You are an autocomplete engine.

Predict the user's intended command.

Rules

Return 5 candidates.

Each candidate is a continuation.

Do not explain.

Do not execute.

Do not include markdown.

Prefer repository-aware suggestions.

Each line must be independently executable.
```

---

User Prompt

```
Repository

Python

Project

fj-ai

Files

README.md
src/
tests/

Recent history

fj summarize README
fj explain parser

Current input

fj review
```

LLM Output

```
review recent changes

review staged files

review architecture

review code quality

review test coverage
```

---

# Candidate Model

```python
@dataclass
class Candidate:

    text: str

    score: float

    provider: str

    latency_ms: int

    confidence: float
```

---

# Ranking

Every provider returns candidates.

Ranking merges them.

```
History

0.91

LLM

0.82

Static

0.73

Git

0.66
```

Final order

```
review recent changes

review staged files

review architecture

review code quality
```

---

# Ranking Signals

Score should combine

```
Provider confidence

LLM confidence

History frequency

Repository relevance

Prefix similarity

Context relevance

Recency
```

---

# Latency Budget

A completion should feel instantaneous.

| Stage           | Target     |
| --------------- | ---------- |
| Context         | 30 ms      |
| Cache lookup    | 5 ms       |
| Local reranking | 10 ms      |
| LLM             | 150–250 ms |
| Total           | <300 ms    |

---

# Caching

Key

```
Repository

Branch

Input Prefix

Project Hash
```

Example

```
fj explain

↓

cached predictions
```

Expire

```
git checkout

git pull

directory changed

history updated
```

---

# Streaming Completion

Immediately display cached or deterministic candidates while an asynchronous LLM request refreshes the cache. Since most shells don't support updating an already-open completion menu, the refreshed results are primarily useful for the *next* Tab press. This keeps the interaction feeling responsive without blocking on network latency.

---

# Personalization

The engine should gradually learn.

History

```
review PR

review tests

review benchmark
```

Eventually

```
fj rev<TAB>
```

↓

```
review benchmark

review PR

review staged changes
```

No LLM required.

---

# Plugin Architecture

```python
class CompletionProvider:

    async def complete(
        self,
        context: CompletionContext
    ) -> list[Candidate]:
        ...
```

Providers

```
StaticProvider

HistoryProvider

FilesystemProvider

GitProvider

LLMProvider

WorkspaceProvider

PluginProvider
```

Third-party plugins register new providers.

---

# Privacy Modes

### Local

Only local models.

```
Ollama

MLX

vLLM

llama.cpp
```

---

### Hybrid

Local context

Cloud inference

---

### Offline

No network.

Only history/static completion.

---

# Future Extensions

### Multi-line completion

```
fj create an MCP server

↓

that exposes GitHub issues
```

---

### Agent-aware completion

The engine understands installed tools.

```
You have

Claude Code

Codex

Docker

kubectl
```

↓

```
deploy the current service to staging

inspect failing GitHub Actions

explain Kubernetes manifests
```

---

### Predictive workspace

Without typing.

```
fj<TAB>
```

↓

```
review files modified today

summarize yesterday's work

generate release notes

find technical debt

update project documentation
```

---

# Example User Journey

```
$ cd fj-ai

$ fj<TAB>
```

```
summarize this repository

review today's changes

find TODO comments

explain completion engine

generate API documentation
```

User selects

```
review today's changes
```

Next

```
$ fj review<TAB>
```

```
review staged files

review recent commits

review architecture

review tests

review performance regressions
```

The experience feels less like navigating a CLI grammar and more like interacting with an AI assistant that anticipates the next task.

## Design Principles

1. **Intent over syntax**: predict the user's goal, not just the next token.
2. **Context first**: repository, workspace, and history are first-class inputs.
3. **Composable providers**: every source of knowledge contributes candidates independently.
4. **Fast by default**: rely on caching, asynchronous refresh, and lightweight reranking to keep perceived latency low.
5. **Privacy by choice**: support local-only, hybrid, and cloud-backed completion.
6. **Extensible**: allow plugins to add context sources, candidate providers, and ranking signals without changing the core engine.

This architecture positions `fj` not as another CLI with shell completion, but as an **AI-native command prediction platform**, where pressing **Tab** surfaces the most probable next task rather than merely the next valid argument.

