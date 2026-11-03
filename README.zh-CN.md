# NS-RSI-Anything

**Neuro-Symbolic Recursive Self-Improvement across General Domains（跨通用领域的神经-符号递归自我改进）**：LLM（神经）编写程序（符号）来完成任务，再递归地改进这个程序，覆盖游戏、具身机器人和计算机操作。

**[项目主页与进度日志](https://smu-diga.github.io/ns-rsi-anything-programme/)** · [English](README.md) · [方案设计](https://smu-diga.github.io/ns-rsi-anything-programme/#design) · [环境选型](https://smu-diga.github.io/ns-rsi-anything-programme/#environments) · [路线图](https://smu-diga.github.io/ns-rsi-anything-programme/#roadmap)

LLM 先写出一个能完成任务的程序，比如游戏 bot、机器人控制器或桌面 agent。之后多个 LLM 根据环境交互反馈，逐代改进这个程序。被改进的对象是**代码**，不是神经网络权重。一个程序包括策略、状态检测与技能函数，以及一份作为程序记忆的 `NOTES.md`。

## 循环

1. 当前最优程序复制给 K 个 improver（Codex CLI、Claude Code、DeepSeek 等聊天 API），它们并行修改，并在 train seeds 上自测。
2. 评测器独立地重新评测每个候选，不采信 improver 自己报告的分数。
3. 最好的候选在隐藏的 dev seeds 上与当前程序配对比较，通过 bootstrap 晋升门槛才替换当前程序。
4. 可选的简化轮：让 improver 精简代码，dev 分数不下降才保留。
5. test seeds 只在实验结束时使用一次。

## 思路来源

- [RSI-Anything](https://github.com/Gen-Verse/RSI-Anything)：跨领域递归自我改进（提出、预测、选择、评价、保留），以及冻结评测协议和晋升门槛。
- [Learning Beyond Gradients](https://trinkle23897.github.io/learning-beyond-gradients/)：coding agent 迭代修改手写程序，在 Atari、MuJoCo、VizDoom 上不靠梯度也能取得有竞争力的成绩。

## 进度

| 模块 | 状态 |
|---|---|
| RSI 主循环、版本库、晋升门槛、断点续跑、环境步数统计 | Done |
| 隔离评测：策略运行在独立进程，拿不到 reward 和 seed | Done |
| Improver：Codex CLI、Claude Code、OpenAI 兼容 API（DeepSeek） | Done |
| 游戏：Atari，Breakout RAM（2 代后隐藏 dev seed 平均 849.9） | Running |
| 游戏：VizDoom | Done |
| 具身机器人：MuJoCo 运动控制、MetaWorld、ManiSkill3 | Done |
| 具身机器人：LIBERO（Spatial state test 99.0%；Spatial vision dev 95.0%；LIBERO-10 state dev 100%） | Running |
| 具身机器人：SimplerEnv、RoboTwin 2.0 | Planned |
| 计算机操作：OSWorld（围绕固定 2B 小模型的智能体框架） | In progress |

状态：Done（已接入并测试）· Running（实验进行中）· In progress（开发中）· Planned（尚未开始）。

首次冒烟实验设置为 Breakout、RAM 输入、1 代、1 个 DeepSeek improver。隐藏 dev 集均分从随机初始程序的 2.1 提升到 13.0。程序还自己在 NOTES 里记下了发现的环境规律，比如需要先按 FIRE 发球、RAM 中挡板和球的位置字节。

本仓库只公开方案文档与实验结果，不包含实现代码。

添加进度记录：在 `_posts/` 下新建 `YYYY-MM-DD-标题.md`，格式见 [README.md](README.md#progress-log)。

许可证：MIT。
