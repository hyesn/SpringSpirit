# Spring 独立桌宠项目交接方案 
## 一、开发计划 
### 技术方案 
- 平台：Windows 
- 语言：Python 3.11 
- GUI：PySide6 
- 动画：`QTimer + RGBA PNG 帧` 
- 配置：JSON 动画清单 + `QSettings` 
- 打包：PyInstaller `onedir` 
- 测试：pytest 
正式程序不使用 GIF 播放。GIF 只作为预览，因为 PNG 帧： 
- 保留完整半透明边缘。 
- 不受 GIF 256 色限制。 
- 可以精确控制每帧速度。 
- 更容易切换状态和缩放。 
- 可正确保留跳跃高度轨迹。 
### V0.1 核心功能 
- 无边框透明窗口。 
- 始终置顶且不显示任务栏图标。 
- 默认显示在主屏幕右下角。 
- 循环播放 `idle`。 
- 左键拖动。 
- 右键退出。 
- 仅角色非透明区域响应鼠标。 
### V0.2 九状态版本 
右键菜单接入： 
| 状态 | 中文菜单 | 行为 | 
|---|---|---| 
| `idle` | 待机 | 持续循环 | 
| `running-right` | 向右跑 | 持续循环 | 
| `running-left` | 向左跑 | 持续循环 | 
| `waving` | 挥手 | 播放一次后回待机 | 
| `jumping` | 跳跃 | 播放一次后回待机 | 
| `failed` | 闹别扭 | 播放一次后回待机 | 
| `waiting` | 喝奶茶 | 持续循环 | 
| `running` | 工作中 | 持续循环 | 
| `review` | 照镜子 | 持续循环 | 
左右跑首版只播放动作，不自动移动窗口。 
### V0.3 使用体验 
- 滚轮缩放，范围 50%–250%。 
- 默认缩放 125%。 
- 保存上次位置、尺寸和循环状态。 
- 启动时恢复配置。 
- 如果保存位置不在当前显示器范围内，自动移回可见区域。 
- 支持多显示器和 Windows DPI 缩放。 
### 推荐结构 
```text 
F:\Code\Spring 
├── main.py 
├── requirements.txt 
├── spring_pet.spec 
├── README.md 
├── src\spring_pet 
│ ├── app.py 
│ ├── pet_window.py 
│ ├── animation_controller.py 
│ ├── asset_loader.py 
│ └── settings.py 
├── assets 
│ ├── animation_manifest.json 
│ └── animations 
│ ├── idle 
│ ├── running-right 
│ ├── running-left 
│ ├── waving 
│ ├── jumping 
│ ├── failed 
│ ├── waiting 
│ ├── running 
│ └── review 
├── docs 
│ ├── ASSET_GUIDE.md 
│ ├── previews 
│ └── assets-reference 
└── tests 
``` 
### 动画速度 
在 `animation_manifest.json` 配置，不修改图片： 
```json 
{ 
"default_state": "idle", 
"canvas": [192, 208], 
"default_scale": 1.25, 
"states": { 
"idle": { 
"label": "待机", 
"frames": 6, 
"durations_ms": [350, 140, 140, 180, 180, 400], 
"behavior": "loop" 
} 
} 
} 
``` 
其余建议时长： 
- 左右跑：`[150,150,150,150,150,150,150,280]` 
- 挥手：`[180,180,180,350]` 
- 跳跃：`[180,180,180,180,350]` 
- 失败：`[180,180,180,180,180,180,180,300]` 
- 喝奶茶：`[190,190,190,190,190,330]` 
- 工作：`[150,150,150,150,150,280]` 
- 照镜子：`[190,190,190,190,190,350]` 


## 二、交给 Spring 项目 Codex Agent 的素材指南 
--- 
# Spring Desktop Pet Asset Guide 
## 1. Production assets 
The application must use PNG frame sequences from: 
```text 
assets/animations 
``` 
Do not use GIF files as the production animation source. GIF files under `docs/previews` are visual references only. 
Each production frame is: 
```text 
Format: PNG 
Mode: RGBA 
Canvas: 192×208 
Background: transparent 
Naming: two-digit sequence, e.g. 00.png, 01.png 
``` 
## 2. Available states 
```text 
idle 6 frames 
running-right 8 frames 
running-left 8 frames 
waving 4 frames 
jumping 5 frames 
failed 8 frames 
waiting 6 frames 
running 6 frames 
review 6 frames 
``` 
Product-specific meanings: 
```text 
waiting = drinking milk tea while waiting 
running = working with a laptop 
review = admiring herself in a hand mirror 
``` 
These are intentional custom semantics and must not be “corrected” to the original Codex meanings. 
## 3. Critical invariants 
Do not automatically crop, trim or recenter individual frames. 
The transparent canvas encodes animation position: 
- `jumping` uses different vertical positions to express the jump. 
- Cropping and centering each jumping frame would destroy the jump trajectory. 
- Other states use stable anchors to prevent size and position popping. 
Do not regenerate or independently edit `running-left`. 
`running-left` is the approved framewise horizontal mirror of `running-right`, with the same temporal order. 
Do not apply chroma-key removal again. These PNG frames already have transparent backgrounds and cleaned edges. 
Do not convert production frames to GIF before display. GIF palette conversion reduces color and alpha quality. 
## 4. Runtime loading 
Load frames in lexical order: 
```text 
00.png 
01.png 
02.png 
... 
``` 
Validate at startup: 
- Directory exists. 
- Frame count matches the manifest. 
- Every image is `192×208`. 
- Every image has an alpha channel. 
- The first frame can be loaded before creating the window. 
Use one reusable `QTimer` and update the `QLabel` pixmap for each frame. 
Do not create a timer per state. 
## 5. State behavior 
Looping states: 
```text 
idle 
running-right 
running-left 
waiting 
running 
review 
``` 
One-shot states: 
```text 
waving 
jumping 
failed 
``` 
One-shot states return to `idle` after their final frame. 
Animation speed must come from `animation_manifest.json`. Do not duplicate timing constants throughout Python files. 
## 6. Rendering 
Scale the complete `192×208` frame uniformly. 
Do not scale the visible character bounding box independently. 
Use smooth transformation for display scaling, but preserve the original frame files. 
The window mask should follow the current frame alpha channel so transparent regions do not block desktop clicks. 
Recalculate the mask after: 
- frame changes; 
- scale changes; 
- state changes. 
## 7. Interaction 
Required interactions: 
- Left mouse drag moves the pet. 
- Right click opens the state menu. 
- Mouse wheel changes scale. 
- Exit menu item closes the application. 
Persist using `QSettings`: 
```text 
window position 
scale 
last looping state 
``` 
Clamp restored positions to an available screen. 
## 8. Packaging 
Use PyInstaller `onedir`. 
All assets must be collected through `spring_pet.spec`. 
Runtime code must resolve assets through a central `resource_path()` helper and must work both: 
- from the source checkout; 
- from a PyInstaller frozen build. 
Do not rely on the current working directory. 
## 9. Asset acceptance checks 
Before release, verify: 
- No visible green fringe. 
- No white or black rectangular background. 
- Jumping visibly moves low → high → low. 
- Running-left visually mirrors running-right. 
- Milk tea, laptop and hand mirror remain intact. 
- State changes do not resize or shift the window unexpectedly. 
- Transparent areas do not block normal desktop interaction. 
- Animation speed matches the manifest. 
## 10. Source references 
```text 
docs/assets-reference/canonical-base.png 
docs/assets-reference/contact-sheet.png 
docs/assets-reference/repair-report.json 
docs/assets-reference/validation.json 
``` 
These files support QA and identity comparison but are not loaded by the application at runtime. 
--- 
## 验收标准 
- 源码运行时透明窗口、拖动、右键菜单和九状态正常。 
- 透明区域不遮挡桌面点击。 
- 跳跃轨迹、左右镜像和道具完整。 
- 程序重启后恢复位置与尺寸。 
- PyInstaller `onedir` 包可脱离 Conda 环境双击运行。 
- 运行目录只需要打包后的应用，不要求用户额外复制素材。 
