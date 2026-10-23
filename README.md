# Chovy —— 轻量离线桌面图像处理软件

一款面向日常使用的**完全本地离线**桌面修图工具，定位为系统自带画图的轻量替代：
本地读取与保存图片，打开即用，操作直观。

- 技术栈：Python 3.12 + PySide6（Qt 界面）+ Pillow / numpy（图像处理）
- 所有图像读写、处理、批处理均在本地完成，**不联网、不上传任何数据**

---

## 一、功能一览

| 模块 | 说明 |
| --- | --- |
| 本地浏览与导入 | 打开单张 / 打开文件夹 / 拖拽到窗口；支持 JPG、PNG、GIF、BMP、WebP；左侧缩略图网格；最近记录 |
| 基础调整 | 自由/比例裁剪（1:1、16:9、4:3、3:4、证件照 5:7）、任意角度旋转、90° 步进、水平/垂直翻转、等比/自由缩放；亮度/对比度/饱和度/色温/曝光度滑块实时预览；一键自动白平衡/自动对比度/锐化 |
| 滤镜与水印 | 10 种滤镜（黑白/复古胶片/冷色调/暖色调/高斯模糊/锐化/马赛克/浮雕/怀旧/高对比），0–100% 强度实时预览；文字水印（内容/字体/字号/颜色/透明度、可拖拽）；图片水印（导入 Logo、调大小与透明度） |
| 绘制与标注 | 画笔、橡皮擦、矩形、圆形、直线、箭头；可调粗细/颜色/透明度；文字标注（可拖拽定位后应用） |
| 批量处理 | 批量缩放、格式转换（JPG/PNG/WebP 互转）、批量水印；自定义输出文件夹与命名前缀/后缀；进度条；失败单独提示；**后台线程运行，不阻塞主界面** |
| 辅助 | 按住空格对比原图；撤销/重做（最多 20 步）；导出 JPG/PNG/WebP 并可调质量，支持覆盖或另存为 |

---

## 二、运行方式

```powershell
# 1) 依赖（已随项目提供 vendor 目录，通常无需再次安装）
#    若需重新安装 PySide6 到短路径：
#    python -m pip install --target vendor PySide6-Essentials

# 2) 启动
python run.py

# 3) 自检（无界面，验证核心逻辑）
python run.py --selftest
```

> 说明：本机为 Windows Store 版 Python，路径较长会导致 `pip install PySide6`
> 因长路径报错，故 PySide6 已安装到项目内 `vendor/` 目录并由 `run.py` 加入
> `sys.path`。其余依赖（Pillow、numpy）已装入系统环境。

---

## 三、快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl+O` | 打开图片 |
| `Ctrl+Shift+O` | 打开文件夹 |
| `Ctrl+S` | 保存（覆盖原图 / 另存） |
| `Ctrl+Shift+S` | 导出 / 另存为（选格式与质量） |
| `Ctrl+Z` / `Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+0` / `Ctrl+=` / `Ctrl+-` / `Ctrl+1` | 适应窗口 / 放大 / 缩小 / 100% |
| `空格`（按住） | 对比原图 |
| `Esc` | 取消当前裁剪 / 绘制 / 水印 |
| 滚轮 | 缩放；左键拖拽平移 |

---

## 四、目录结构

```
chovy/
├─ run.py                 # 启动入口（加入 vendor 路径）
├─ requirements.txt
├─ vendor/                # PySide6（短路径安装）
└─ app/
   ├─ main.py             # 程序入口 / 自检模式
   ├─ mainwindow.py       # 主窗口、预览/提交/撤销重做逻辑
   ├─ canvas.py           # 图像画布（缩放/平移/裁剪/绘制/覆盖层）
   ├─ imageops.py         # Pillow+numpy 图像处理核心
   ├─ history.py          # 撤销/重做
   ├─ batch.py            # 批量处理（后台 QThread）
   ├─ panels.py           # 右侧面板（调整/滤镜/水印/绘制/批处理）
   ├─ sidebar.py          # 缩略图/最近浏览栏
   ├─ dialogs.py          # 导出对话框
   ├─ recent.py           # 最近记录与设置持久化
   └─ selftest.py         # 无界面自检
```

---

## 五、已知限制

- GIF 仅取首帧用于编辑（静态化）；BMP 可读取，导出时建议转 JPG/PNG/WebP。
- 文字标注 / 水印在「应用」前可拖拽定位；应用后即栅格化到图像（可撤销重做）。
- 撤销/重做针对破坏性操作（裁剪、旋转、滤镜应用、绘制、水印等）；亮度等滑块为实时参数，可用「重置全部参数」或拖动滑块回到 0 来还原。
- 批量处理中的格式转换在 JPG/PNG/WebP 之间互转。

---

## 六、打包为独立 EXE（可选）

使用 PyInstaller 可生成不依赖 Python 的独立可执行文件：

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name Chovy `
  --paths vendor --add-data "vendor/PySide6;PySide6" `
  --add-data "vendor/shiboken6;shiboken6" run.py
```
