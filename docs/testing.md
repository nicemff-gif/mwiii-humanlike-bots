# 对照实验与测试记录

## 四组配置

1. LUMEN 与语言环境，无研究中的两个人机补丁。
2. 仅 BOTS OVERHAUL。
3. 仅 LUMEN BOTMOD。
4. 两个旧补丁同时启用。

新行为版本作为独立实验组，不能默认与旧控制脚本叠加。显式记录启用脚本及其摘要、运行变量、地图、模式、人数、难度和版本。

## 记录格式

每次实验采用独立记录，至少包含：

```json
{
  "source_commit": "<tested commit>",
  "artifact_sha256": "<built artifact>",
  "game_build": "<observed build>",
  "map": "<map>",
  "mode": "<mode>",
  "enabled_scripts": [],
  "runtime_dvars": {},
  "seed": null,
  "compile": "not_run",
  "load": "not_run",
  "behavior": "not_run",
  "notes": ""
}
```

`pass` 必须有实际结果，加载未确认就保留 `not_run`。测试记录发布前移除玩家标识、聊天内容、绝对本机路径和其他个人信息。

## 首轮场景

- 出生、死亡、重生、结束比赛后，任务和控制权正确释放。
- 玩家绕过遮挡，人机丢失实时位置，搜索最后目击处。
- 持枪、换弹、投掷、撤退互不争夺控制权。
- 固定地图与参数重复实验，记录决策延迟分布、失视搜索、掩体行为和任务耗时。
- 长局与较多人数组合单独检查任务增长和性能。

游戏加载环境保持本地；自动检查不启动游戏，不安装驱动，不写个人设置。
