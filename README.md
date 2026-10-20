# MWIII Humanlike Bots

面向 MWIII 本地自定义对局的人机行为研发项目。目标是实现合理感知、有限记忆、连贯决策和有差异的玩家风格。

项目采用独立源码仓库、短分支、Pull Request、自动检查和分阶段游戏实测。游戏引擎与 LUMEN 加载环境由使用者自行提供。

## 当前状态

**M2：TDM 有限感知与记忆的观察原型。** 已具备锁定工具链、安全部署回退、TDM 白名单和原创 GSC 记忆模块。当前只记录感知与记忆，不控制人机。尚未交付真人化人机；参考模型、GSC 编译、游戏内自测、加载和行为实测分别记录。

首轮限定常规小队 TDM：内部模式标识 `war`、团队对局、连接实体数 1–12。模式识别和引擎接口仍待本地游戏核实；未知模式直接停止观察。随后再适配占领、据点争夺和爆破。

## 项目边界

- 复用游戏的机器人实体、导航、碰撞、动画和武器能力。
- 自主编写行为源码，所有行为控制都经过明确的所有权与退出规则。
- 普通多人小地图作为首个验证场景，复杂模式和战区在后续扩展。
- 公开仓库只收录原创源码、工具、文档和去标识的测试记录。
- 游戏程序、LUMEN 文件、第三方补丁、反编译全文、个人配置和凭据保留在使用者本地。

## 开发检查

开发工具使用 Python 3.12 标准库。

```console
python tools/check_repository.py
python -m unittest discover -s tests -v
```

在 Windows 上构建探针：

```console
python -m tools.toolchain
python -m tools.build
```

输出位于 `dist/`，构建不部署或启动游戏。[工具链与探针说明](docs/build.md) 列出开关和待实测项目。

需要部署时，先用 `python -m tools.deploy plan --game-root "<game directory>"` 预览，再按 [部署与回退说明](docs/deployment.md) 操作。安装保留本地备份与回执，游戏内验证单独记录。

## 文档

- [需求与完成标准](docs/requirements.md)
- [架构决策](docs/adr/0001-own-behavior-reuse-engine.md)
- [开发流程](CONTRIBUTING.md)
- [里程碑](docs/roadmap.md)
- [实验协议](docs/testing.md)
- [人工测试 01：操作步骤与反馈表](docs/manual-test-01.md)
- [TDM 感知记忆与游戏内验证](docs/tdm-memory.md)
- [研究来源与原安装仓库关系](docs/research/provenance.md)

本项目与游戏及第三方加载器的发布者没有隶属关系。原创代码采用 [MIT License](LICENSE)；第三方工具和游戏资源适用各自条款。
