# 锁定工具链与探针构建

## 环境

Windows x64、Git、Python 3.12。编译器为外部 ACTS 3.3.0，版本、官方 URL、压缩包、关键二进制摘要和随机种子记录在 `toolchain.lock.json`。编译器会随机选择部分等价编码及校验信息，因此固定种子后再验证完整字节一致性。更新工具链必须单独提交并重新验证。

```console
python -m tools.toolchain
python -m tools.build
```

首次安装会下载官方发布包、验证 SHA-256 并保存至忽略的 `.tools/`。若已有同版本工具，可使用 `python -m tools.build --acts <acts.exe>`，仍须通过锁定摘要校验。

构建把 `src/hbot/` 模块和共享场景生成的原生自测打包到单一 GSC 对象，显式固定文件命名空间为 `hbot_probe`。执行两次独立编译并比较完整产物，再反编译检查 VM、命名空间、入口、对应配置的开关缺省值、模式边界和观察模式约束。普通产物写入 `dist/`，包括原创字节码、检查文本、编译输出和 `manifest.json`。

清单包含源码提交、工作区是否有改动、每个 GSC 源文件／场景／生成器／构建器的摘要、实际编译源码摘要、构建配置、整体输入摘要、工具链与产物摘要。`native_memory_contracts`、`game_load` 和 `behavior` 保持 `not_run`，直到单独记录游戏内结果。重复编译一致只证明本次环境下的字节码一致。

决策观察模块加入后，构建另包含 15 个共享决策场景生成的 126 条 GSC 断言；`native_decision_contracts` 与 `shadow_decision` 分别记录原生断言和运行集成验证，均初始为 `not_run`。两种构建均检查决策模块不读取世界实体／实时位置，不写入目击，也不执行动作。细节见 [决策观察](shadow-decision.md)。

## 不依赖控制台的人工测试包

```console
python -m tools.build --profile manual-test
```

这是明确选择的测试配置。构建器只在临时源码副本中把 probe、memory、selftest、debug 四个开关的缺省值改为 1，不修改仓库源码或个人设置，不改变感知和记忆算法。逐项要求原始缺省值为 0 且只出现一次，源码漂移就拒绝构建。人工包保存到 `dist/manual-test/`，普通包仍在 `dist/`；两者固定安装同一路径，不能并行安装。

清单通过 `build_profile=manual-test` 和 `diagnostics_default_enabled=true` 显式区分；反编译检查分别要求 1 或 0，不允许人工包通过普通包的开关检查。CI 编译并检查两种配置。运行变量已有显式值时仍优先于缺省值。人工包默认输出诊断但不控制行为，详细步骤见 [人工测试 01](manual-test-01.md)。

## 观察探针

唯一安装路径为 `jupiter/Assets/Scripts/mp/hbot_probe.gscc`。内部资源身份为 `scripts/mp/hbot_probe.gsc`，命名空间 `hbot_probe`。普通 observer 配置默认关闭，仅在地图初始化前设置 `hbot_probe_enabled 1` 后启动；人工包按上节明确开启。

只在 TDM 白名单中工作，通过游戏内文字输出总人机数、存活人机数、真人数量和记忆总量，不输出玩家名称或标识，不控制移动、瞄准、武器或伤害。`game_ended` 通知结束任务；同一地图的重复初始化由标记拦截。记忆观察另需 `hbot_memory_enabled 1`，原生自测可由 `hbot_memory_selftest 1` 单独启用；记忆观察启动前也自动运行原生自测，失败即停止。详见 [TDM 记忆验证](tdm-memory.md)。

焦点诊断由 `hbot_debug_enabled 1` 单独开启（代码默认 0），需要同时启用记忆。`hbot_debug_bot` / `hbot_debug_human` 默认 1，选择各自当前序号；读取仅发生于初始化。构建另检查诊断模块不能读取实体 `origin`、进行额外可见性查询或写入目击记录。该源码检查是边界保护，不等于完整静态证明。[人工测试 01](manual-test-01.md) 给出提示解读和需要人工确认的项目。

## 运行验证仍待完成

编译和检查不能验证 LUMEN 是否加载了脚本、当前地图是否发出预期事件或 HUD 输出是否正常。首次运行需记录实际版本与启用组合，并检查：关闭时无输出；启用时计数正确；死亡重生不产生重复任务；换图结束时清理正确。

构建命令不部署或启动游戏。需要安装时使用独立的 [部署与回退工具](deployment.md)，显式指定目录，并核对预览和本地回执。游戏实测前记录启用脚本；不得把观察模式与真人化行为完成混为一谈。
