# Spring Spirit

一个具备环境感知能力的 Windows 桌面精灵。

Spring Spirit 不只是循环播放动画：它通过 Windows 原生前台事件感知当前活动应用，并由状态协调器在持续状态、单次动作、拖动反馈和系统动画之间进行优先级调度，让角色对桌面工作流产生自然响应。

## 核心特性

- **环境感知**：基于 `SetWinEventHook` 监听前台进程，事件驱动、防抖处理并带低频校准
- **状态编排**：统一协调应用联动、手动状态、启动出场、随机彩蛋、拖动与退出动画
- **声明式动画**：状态角色、触发器、菜单分组和返回策略均由 JSON 清单驱动
- **高保真渲染**：原生 RGBA 帧、逐帧 Alpha 命中区域、2× 素材与 DPI 感知缩放
- **可扩展规则**：前台应用映射支持校验、热加载和最后有效配置回退
- **Windows 集成**：多显示器约束、设置持久化、当前用户开机自启动和会话结束处理
- **隐私克制**：仅识别进程文件名，不读取窗口标题、网页内容或文档名称

## 技术架构

`PySide6 · Win32 API · QTimer · QSettings · PyInstaller · pytest`

动画控制、交互状态和系统事件相互解耦。增加普通动作或持续状态时，只需提供帧序列并更新动画清单，无需在窗口层维护状态分支。

## 运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

右键菜单可切换状态、调整缩放、管理开机自启动及前台应用联动。应用规则位于：

```text
%APPDATA%\SpringPet\foreground_rules.json
```

## 测试与构建

```powershell
pytest
pyinstaller --noconfirm --clean spring_pet.spec
```

构建结果位于 `dist/Spring/`，可脱离 Python 环境独立运行。

## 素材原则

生产动画使用完整透明画布的 PNG 帧序列。项目不会逐帧裁剪、居中、重新抠图或转换为 GIF，从而保留动作轨迹、角色锚点和半透明边缘。
