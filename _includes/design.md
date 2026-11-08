### What is improved

A **program**: a policy from observation to action, the skills it grows, and notes that carry memory across
generations. By default no neural network, no access to the environment's source, no network.

### Keeping scores honest

- The policy runs in its own process and never sees the reward, the seed or the environment.
- Improvers get train seeds only; a program or session that touches the data, the splits or the engine is rejected.
- Promotion uses hidden dev seeds; test is used once.

### Improvers and composition

Claude Code and Codex CLI run as coding agents; DeepSeek replies with whole files. All share one history of
attempts. Specialists can be trained on parts of a benchmark and merged back by a three-way merge, then gated like
any candidate.
