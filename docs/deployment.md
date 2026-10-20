# 探针部署与回退

部署工具目前只支持原创观察探针 `hbot_probe.gscc`。源码构建与游戏安装是两个独立步骤，工具只写固定脚本路径，不编辑个人设置或脚本管理器。

## 预览

先从干净的源码提交构建，再选择实际游戏目录：

```console
python -m tools.build
python -m tools.deploy plan --game-root "<game directory>"
```

`plan` 校验清单、大小、摘要、MWIII 字节码头和目标目录标记，报告首次安装、替换或内容相同。预览不创建目录、锁或备份，也不要求游戏退出；进程检查在实际安装前执行。

## 安装

退出游戏和启动器，并在整个操作期间保持关闭：

```console
python -m tools.deploy apply --game-root "<game directory>"
```

实际操作要求 Windows 进程查询成功，并在准备阶段及替换前检查游戏/启动器。工具使用单一目标锁防止自身并发操作，校验产物后保存旧文件字节和本地回执，再以同目录临时文件及原子替换写入。原文件在最后核对前发生变化会阻止替换。

只接受干净且经过编译、反编译检查和重复一致性验证的构建清单。绝对路径、越界、符号链接和 Windows 重解析点均被拒绝。目录标记只用于避免选错安装目录，不能证明游戏文件的真实性。

回执位于 `.local/deployments/<transaction>/receipt.json`，包含本地绝对路径；旧文件备份与回执一同保留。此目录受 Git 忽略，不得上传。重复安装相同字节不会新建备份；请保留首次安装返回的回执路径。

## 回退

```console
python -m tools.deploy rollback --game-root "<game directory>" --receipt "<receipt.json>"
```

首次安装的回退会移除自己的脚本；覆盖安装的回退恢复旧文件字节。回退要求回执属于显式选择的游戏目录，并核对当前文件及备份摘要。如果其他工具在部署后修改了脚本，会保留现状并拒绝覆盖。已回退的回执不会移除后来安装的新文件。

回执先记录 `prepared`，完成写入后记录 `installed`。如果写文件或更新回执中断，可通过回退比较当前文件与原始/安装摘要恢复状态。无法匹配任一摘要时保留文件，交由人工检查。

进程被强制结束可能留下 `.hbot-deploy.lock`。确认没有部署进程、核对回执和脚本后，人工移除该单个锁文件再恢复；工具不会自动猜测锁是否过期。备份恢复的是文件内容，不承诺还原权限、时间戳等元数据。进程检查不能阻止用户在检查后另行启动游戏。

## 游戏实测

安装成功只证明磁盘文件已部署。普通 observer 包默认关闭；是否允许加载由 LUMEN 和本地脚本管理设置决定。普通包启用前须将 `hbot_probe_enabled 1` 在地图初始化前设置，并按实验协议验证输出与生命周期。人工包的明确开启方式见下节。

本工具不设置运行变量，不启动游戏、不安装驱动。加载与行为状态持续记录为 `not_run`，直到实际进入地图验证。

## 人工测试包

没有已确认的变量输入入口时，可显式构建并部署人工包：

```console
python -m tools.build --profile manual-test
python -m tools.deploy plan --game-root "<game directory>" --manifest dist/manual-test/manifest.json
python -m tools.deploy apply --game-root "<game directory>" --manifest dist/manual-test/manifest.json
```

预览和回执会标记 `build_profile=manual-test`、`diagnostics_default_enabled=true`；人工包在缺少同名显式运行变量时自动开启观察、自测和焦点诊断。其余部署约束不变。原来不含配置字段的清单按 observer 兼容；配置与开关标志不匹配则拒绝。回退使用这次安装的回执，恢复先前默认关闭的观察脚本。不要把人工测试包长期当成普通包使用。
