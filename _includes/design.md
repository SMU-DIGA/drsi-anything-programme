### What is improved

A **program**: a policy that maps an observation to an action, the modules it grows (detectors, skills, planners),
and notes that serve as its memory (environment facts, failed ideas, a changelog). By default it uses no neural
network, never reads the environment's source code and has no network access. In OSWorld it may also ask one frozen
small model typed multiple-choice questions.

### Improvers

Claude Code and Codex CLI run headless as coding agents that edit, run and probe. A chat model (DeepSeek) replies with
whole files over several rounds of train feedback. All share one history of attempts, so each sees the others'
failures.

### Keeping scores honest

- The policy runs in its own process and never sees the reward, the seed or the environment object.
- Improvers get train seeds only; a program that reads the data, the splits or the engine is rejected.
- Promotion uses hidden dev seeds; test is used once, after the run.
- Known limit: the agents run as the same OS user; container isolation is planned.

### Composition

Specialists on subsets of a benchmark start from one common program; their edits are joined by a three-way merge,
and the merged program faces the same dev gate (ScienceWorld, Atari-5).

### Planned

Editing the weights of an LLM the program calls, directly by the improver
([weight-space programming](https://rikiyat.github.io/blog/weight-space-programming/)); a cross-task skill library;
improving the improvers themselves.
