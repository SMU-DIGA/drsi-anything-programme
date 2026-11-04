# DRSI-Anything

**Delegative Recursive Self-Improvement across General Domains（跨通用领域的委托式递归自我改进）**：LLM 不直接与环境交互，而是把"行动"委托给自己编写并不断递归改进的程序，覆盖游戏、具身机器人和计算机操作。神经-符号程序（代码，可调用小模型）是我们主要的委托形式，但只是委托的一种实现方式。项目原名 NS-RSI-Anything。

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
| 游戏：Atari RAM：Breakout 全部 test seed 864；Pong 21、Ms. Pac-Man 17,207、Montezuma 9,700（dev） | Running |
| 游戏：VizDoom | Done |
| 游戏：扑克（Leduc 变体，用 NashConv 评测；单挑无限注德州，复式对局） | Running |
| 具身机器人：MuJoCo 运动控制、MetaWorld、ManiSkill3 | Done |
| 具身机器人：LIBERO（Spatial state test 99.0%；LIBERO-10 state test 99.0%；Spatial vision dev 95.0%） | Running |
| 具身机器人：SimplerEnv、RoboTwin 2.0 | Planned |
| 计算机操作：OSWorld（纯代码 vs 代码 + 2B 小模型的类型化决策函数） | Running |

状态：Done（已接入并测试）· Running（实验进行中）· In progress（开发中）· Planned（尚未开始）。

主要结果（全部由 LLM 改进者编写和改进的程序取得，没有梯度训练，也没有示范数据）：

- **Breakout（RAM）：** 4 代后，在 64 个从未用过的 test seed 上全部拿到满分 864（初始程序 2.2）。
- **LIBERO（state）：** LIBERO-Spatial 和 LIBERO-10 都只用 1 代，400 局 test 成功率均为 99.0%。
- **Montezuma's Revenge / Ms. Pac-Man / Pong（RAM，隐藏 dev）：** 1 代后分别为 9,700 / 17,207 / 21。

本仓库只公开方案文档与实验结果，不包含实现代码。

添加进度记录：在 `_posts/` 下新建 `YYYY-MM-DD-标题.md`，格式见 [README.md](README.md#progress-log)。

许可证：MIT。
