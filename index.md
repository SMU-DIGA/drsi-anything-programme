---
title: NS-RSI-Anything
permalink: /
---

# NS-RSI-Anything

<p class="lead">Recursive self-improvement of LLM-written programs for games, embodied robotics and computer use.</p>

An LLM writes a program that solves a task: a game bot, a robot controller or a desktop agent. LLMs then
improve that program over many generations, using only feedback from interacting with the environment.
The object being improved is **software**, not network weights. It consists of a policy, its detectors and
skills, and a notes file that serves as the program's memory.

```
incumbent program ──► K improvers edit it in parallel (Codex CLI · Claude Code · chat APIs)
                        │ each tests its own edits on the train seeds
                        ▼
                independent re-evaluation ──► best candidate vs. incumbent on hidden dev seeds
                        │ paired bootstrap promotion gate
                        ▼
                new incumbent ──► optional simplification ──► next generation
```

The project builds on [RSI-Anything](https://github.com/Gen-Verse/RSI-Anything), which contributes the
cross-domain self-improvement loop and frozen evaluation protocol. It also builds on
[Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/), which shows that a
coding agent editing programs can compete with deep RL on Atari, MuJoCo and VizDoom.

## Latest progress

<ul class="log">
{% for post in site.posts limit:5 %}
  <li>
    <time datetime="{{ post.date | date_to_xmlschema }}">{{ post.date | date: "%Y-%m-%d" }}</time>
    · <a class="title" href="{{ post.url | relative_url }}">{{ post.title }}</a>
    <p class="summary">{{ post.summary }}</p>
  </li>
{% endfor %}
</ul>

[All progress updates →]({{ '/progress/' | relative_url }})

## Status

| Component | Status |
|---|---|
| RSI loop: archive, promotion gate, simplification, resume, env-step ledger | <span class="status done">done</span> |
| Isolated evaluator (policy runs in a separate process, no access to reward or seed) | <span class="status done">done</span> |
| Improvers: Codex CLI, Claude Code, OpenAI-compatible chat APIs | <span class="status done">done</span> |
| Games: Atari (RAM / image), VizDoom | <span class="status done">done</span> |
| Robotics: MuJoCo locomotion, MetaWorld | <span class="status done">done</span> |
| Robotics: LIBERO, ManiSkill3 | <span class="status wip">simulators verified, adapters in progress</span> |
| Robotics: SimplerEnv, RoboTwin 2.0 | <span class="status planned">planned</span> |
| Computer use: OSWorld | <span class="status planned">planned</span> |
| Cross-task skill library (L2), self-improving improver (L3) | <span class="status planned">planned</span> |

## Documents

- [Design](design/): the loop, isolation, improvers, levels of recursion, evaluation protocol
- [Environments](environments/): games, embodied benchmarks, OSWorld, and why each was chosen
- [Roadmap](roadmap/): phases and open research questions
