# Native Expression Protocol

Apply to every chapter in every non-English report, and to English reports for the sentence-rhythm and heading rules. This protocol makes "no translationese" operational: it names the failure patterns, gives repair recipes, sets measurable budgets, and is enforced by `scripts/prose_lint.py`.

## Why the rule "avoid translationese" is not enough

A model composing in Chinese, Japanese, Korean, German, or any non-English language still plans in English-shaped propositions. The output is grammatical but reads as translated: metaphors are carried over literally, headings keep English article structure, sentences keep English length and clause order, and abstract nouns accumulate modifiers. Declarative advice does not catch this. Named patterns plus a mechanical scan do.

## 1. Metaphor provenance test

Before using any figurative expression, ask: **does this metaphor already exist in the report language, or am I translating an English one?**

| Test | Action |
|---|---|
| The metaphor is idiomatic in the target language | Use it |
| A different native metaphor expresses the same idea | Use the native one |
| No native metaphor exists | Drop the figure and state the idea plainly |

Never invent a compound by translating an English metaphor word-for-word. Common failures when writing Chinese:

| 直译（避免） | 来源 | 母语表达 |
|---|---|---|
| 问题的形状 | the shape of the problem | 问题的本质 / 问题全貌 |
| 攻击面（非安全语境） | attack surface | 着力点 / 优化对象 / 可下手的环节 |
| 承重假设 | load-bearing assumption | 关键前提 / 支撑性假设 |
| 判决性实验 / 判决性未知 | decisive experiment / unknown | 决定性实验 / 最关键的未知项 |
| 可核性 | verifiability | 可核查性 |
| 一次成本会计 | a cost accounting | 算一笔成本账 / 成本核算 |
| 机制地图 | mechanism map | 机制全景 / 技术格局 |
| 评测场失真 | the evaluation arena is distorted | 评测口径不一致 / 评测环境不可比 |
| 干净的证据 | clean evidence | 干净的对照 / 没有混杂的证据 |
| 指标可被投机 | metrics can be gamed | 指标可以被钻空子 / 可以刷高 |
| 谱系（技术演进） | lineage / phylogeny | 演进脉络 / 发展路径 |
| 令牌侧 / 评测侧 / 基线侧 | token-side / evaluation-side | 在令牌层面 / 从评测出发 / 就基线而言 |
| 需要读出来的结论 | conclusions to read out | 必须点明的结论 |
| 九十天顺序 | 90-day sequence | 九十天推进节奏 / 分阶段计划 |
| 房间里的大象 | elephant in the room | 明摆着却没人提的问题 |
| 低垂的果实 | low-hanging fruit | 唾手可得的收益 |
| 银弹 | silver bullet | 万能解法 |
| 在一天结束时 | at the end of the day | 归根结底 |

Keep established loanwords that the target-language technical community already uses (端到端、落地、对齐、第一性原理、端侧). The test is community usage, not etymology.

## 2. Heading rules

Headings are where translationese is most visible, because English article and "a/an" framing survives translation.

| Avoid | Reason | Prefer |
|---|---|---|
| 一个空的交集 | English "an empty intersection" | 空白的交集 / 尚无人占据的交集 |
| 一个统一的可核性声明 | article + coinage | 关于可核查性的统一说明 |
| 一个来自小标题的反例 | literal, opaque | 一个反例：极简方案为何够用 → 反例：极简方案为何够用 |
| 一个一致的空白 | article + vague adjective | 共同的空白 / 所有方案共有的空白 |
| 本报告如何推进 | "how this report proceeds" | 全文结构 / 阅读路径 |
| 最后一句 | "one last sentence" | 一句话结论 |
| 三条选项并存 | wrong measure word | 三个选项并存 |

Rules:

1. Do not open a Chinese/Japanese/Korean heading with a numeral-classifier phrase that only exists to mimic an article (一个 / 一次 / 一条 / 一種 / 하나의).
2. Name the topic or state the claim; a heading is a label or an assertion, not a sentence fragment carried from English.
3. Use the correct measure word: 机制/方案/选项/假设 take 类·个·项, not 条.
4. Keep the heading readable aloud as a native section title.

## 3. Sentence rhythm

Translated prose keeps English sentence length and subordination. Repair by restructuring, not by inserting punctuation.

- **Length budget**: in Chinese, keep most sentences under ~60 characters and none over ~100. Split at the logical seam instead of extending with 破折号 or 从而.
- **One proposition per sentence**: if a sentence carries a claim, its condition, its counter-example, and its implication, split into two or three.
- **Avoid 「的」 chains**: four or more 的 inside one clause signals stacked English modifiers. Convert modifiers into verbs or separate clauses.
  - 避免：这条机制的最有说服力的一点的证据的来源
  - 改为：这条机制最有说服力的证据来自……
- **Prefer active, topic-comment structures**: 该结论被四个团队验证 → 四个团队都验证了这个结论。Passive is acceptable when the agent is unknown or irrelevant; three or more 被 in one paragraph is a smell.
- **Punctuation budget**: 破折号 (——) is an English habit when used for every aside. Keep at most one per paragraph, and under ~5 per 1,000 characters; otherwise use 逗号、分号、冒号 or a new sentence.
- **Connectives**: use the target language's own discourse markers. Do not chain literal equivalents of "moreover / furthermore / in addition"; Chinese formal prose prefers 而、且、同时、反过来、也就是说、由此.

## 4. Abstract-noun discipline

English research prose nominalizes heavily ("the verification of the robustness of the mechanism"). Chinese prefers verbs.

- 避免：对该机制稳健性的验证的完成
- 改为：验证了该机制是否稳健

Rule: if a noun phrase contains two or more nominalized verbs, rewrite with verbs.

## 5. Quoted and borrowed wording

When a source's phrase is quoted (e.g. "irreversible input-side compression"), keep the quotation and mark it as the source's wording; do not let its structure leak into surrounding prose. Outside the quotation, describe the idea in native phrasing.

## 6. Read-aloud test (mandatory per chapter)

After drafting, read the chapter's headings and first sentence of each section as if speaking to a colleague in that language. Flag anything that:

- a native speaker would not say out loud;
- requires mentally translating back to English to parse;
- sounds like a conference-paper abstract translated by software.

Rewrite those passages before saving the chapter.

## 7. Mechanical scan

Run the linter during the Consistency & Polish pass and before Gate D:

```bash
python3 scripts/prose_lint.py --mode <mode> --workspace .
python3 scripts/prose_lint.py --mode <mode> --json      # machine-readable
python3 scripts/prose_lint.py --file <deliverable.md>   # final check
```

Findings:

| Severity | Meaning | Gate D |
|---|---|---|
| `high` | clear calque, coinage, or article-style heading | **blocks** until fixed or allowlisted with reason |
| `medium` | density and collocation smells (的-chain, passive/dash stacking, long sentence, `X侧`, measure word) | review each; fix or record why it stays |

Stats reported per file (`avg_sentence`, `dash/1k`, `passive/1k`) are budgets, not verdicts — use them to spot chapters that drifted.

**Deliberate usage:** if a flagged term is genuinely the field's standard term in that language, add it to `.omr/prose-lint-allow.txt` (one substring per line, `#` for comments) and note the justification in the continuity brief's term table. Never silence a finding by rewording only the linted surface while keeping the translated structure.

## 8. Anti-patterns

| Do not | Do instead |
|--------|------------|
| Draft the idea in English, then render it in the report language | Compose the sentence in the report language from the start |
| Invent a compound by translating an English metaphor | Use a native metaphor, or state it plainly |
| Open headings with 一个/一次/一条 to mimic "a/an" | Name the topic or assert the claim |
| Use 破折号 for every aside | Use commas, colons, semicolons, or split the sentence |
| Stack modifiers with repeated 的 | Convert modifiers into verbs or clauses |
| Keep a source's English clause structure in your own prose | Quote the phrase, then explain it natively |
| Treat linter findings as style opinions | Fix `high` findings; justify anything allowlisted |
