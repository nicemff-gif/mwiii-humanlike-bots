# 锁定工具链与探针构建

## 环境

Windows x64、Git、Python 3.12。编译器为外部 ACTS 3.3.0，版本、官方 URL、压缩包、关键二进制摘要和随机种子记录在 `toolchain.lock.json`。编译器会随机选择部分等价编码及校验信息，因此固定种子后再验证完整字节一致性。更新工具链必须单独提交并重新验证。

```console
python -m tools.toolchain
python -m tools.build
```

首次安装会下载官方发布包、验证 SHA-256 并保存至忽略的 `.tools/`。若已有同版本工具，可使用 `python -m tools.build --acts <acts.exe>`，仍须通过锁定摘要校验。

构建把 `src/hbot/` 模块和共享场景生成的原生自测打包到单一 GSC 对象，显式固定文件命名空间为 `hbot_probe`。执行两次独立编译并比较完整产物，再反编译检查 VM、命名空间、入口、默认关闭开关、模式边界和观察模式约束。产物写入 `dist/`，包括原创字节码、检查文本、编译输出和 `manifest.json`。

清单包含源码提交、工作区是否有改动、每个 GSC 源文件／场景／生成器的摘要、整体输入摘要、工具链与产物摘要。`native_memory_contracts`、`game_load` 和 `behavior` 保持 `not_run`，直到单独记录游戏内结果。重复编译一致只证明本次环境下的字节码一致。

## 观察探针

唯一安装路径为 `jupiter/Assets/Scripts/mp/hbot_probe.gscc`。内部资源身份为 `scripts/mp/hbot_probe.gsc`，命名空间 `hbot_probe`。探针默认关闭，仅在地图初始化前设置 `hbot_probe_enabled 1` 后启动。

只在 TDM 白名单中工作，通过游戏内文字输出总人机数、存活人机数、真人数量和记忆总量，不输出玩家名称或标识，不控制移动、瞄准、武器或伤害。`game_ended` 通知结束任务；同一地图的重复初始化由标记拦截。记忆观察另需 `hbot_memory_enabled 1`，原生自测可由 `hbot_memory_selftest 1` 单独启用；记忆观察启动前也自动运行原生自测，失败即停止。详见 [TDM 记忆验证](tdm-memory.md)。

## 运行验证仍待完成

编译和检查不能验证 LUMEN 是否加载了脚本、当前地图是否发出预期事件或 HUD 输出是否正常。首次运行需记录实际版本与启用组合，并检查：关闭时无输出；启用时计数正确；死亡重生不产生重复任务；换图结束时清理正确。

构建命令不部署或启动游戏。需要安装时使用独立的 [部署与回退工具](deployment.md)，显式指定目录，并核对预览和本地回执。游戏实测前记录启用脚本；不得把观察模式与真人化行为完成混为一谈。
