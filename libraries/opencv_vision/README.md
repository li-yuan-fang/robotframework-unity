# OpenCVVision

通过 OpenCV 多尺度模板匹配，在已有 Appium 会话的画面中寻找按钮或图标，返回包含位置、尺寸和分数的 `ImageElement`。

截图使用 `get_screenshot_as_png()` 获取 PNG 字节，经 `numpy.frombuffer` 和 `cv2.imdecode` 直接进入匹配。默认不创建截图文件或临时图片，不需要 Appium images 插件。每次查找只取一帧。

## 安装

在仓库根目录，使用运行 Robot 的同一个 Python 环境执行：

```powershell
python -m pip install -e "./libraries/opencv_vision[robot]"
```

仅使用 Python 内存接口时，可不安装 `[robot]` 扩展。

依赖为 NumPy 和 `opencv-python-headless`。同一个环境不要同时安装 headless 和 GUI 两种 OpenCV 包。开发验证使用本目录下的 `.venv`，未修改系统 Python。

## Robot Framework

先通过 AppiumLibrary 的 `Open Application` 建立会话，再调用：

```robotframework
*** Settings ***
Library    AppiumLibrary
Library    OpenCVVision

*** Test Cases ***
Find Close Button
    ${element}=    CV Find Image Element    ${CURDIR}/images/close.png
    Log To Console    左上角：${element.location}，宽高：${element.size}
    Log To Console    中心点：${element.center}，分数：${element.score}，比例：${element.scale}
```

使用源码入口时，也可以把 `Library    OpenCVVision` 改为本库 `OpenCVVision.py` 的绝对路径，或相对当前资源文件的路径；运行环境仍需安装依赖。

限定搜索区域、调整缩放范围：

```robotframework
${region}=    Create List    800    500    700    350
${element}=    CV Find Image Element    ${CURDIR}/images/close.png
...    roi=${region}
...    scale_min=0.5    scale_max=2.0    scale_step=0.05
...    threshold=0.8
```

ROI 是原始截图中的 `[x, y, width, height]`，必须完整位于图像内。返回坐标已加回 ROI 偏移。

如 AppiumLibrary 使用别名导入，传入 `appium_library=别名`。库复用当前会话，截图前临时切到 `NATIVE_APP`，截图后恢复原上下文。

## 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `template` | 必填 | PNG/JPEG 模板路径或编码后的图片 `bytes` |
| `threshold` | `0.80` | 最低接受分数，范围 `(0, 1]`，不是概率 |
| `scale_min` / `scale_max` | `0.50` / `2.00` | 等比缩放的下界和上界 |
| `scale_step` | `0.05` | 缩放步长；默认 31 个比例，最多允许 101 个 |
| `roi` | 整张图 | 原始截图坐标中的搜索区域 |
| `score_margin` | `0.05` | 不同位置的候选都达标但分差小于该值时报告歧义；0 表示关闭此保护 |
| `debug` | `none` | 可选 `none`、`on_failure`、`always` |
| `debug_dir` | 启用诊断时为 `${OUTPUT DIR}/opencv_vision` | 诊断文件父目录；默认不访问此目录 |
| `appium_library` | `AppiumLibrary` | 已导入的 AppiumLibrary 名称或别名 |
| `coordinate_mode` | `screenshot` | 显式确认截图覆盖完整窗口后，可以设置 `full_window` 请求窗口坐标换算 |

模板按灰度匹配，必须不透明且具有可区分的图像特征。首版不支持旋转、透视、非等比拉伸及透明蒙版。像素尺寸相同的比例会合并，因此 `scale` 是实际采用的请求比例，`rect` 的宽高是准确的匹配尺寸。

## 元素与坐标

`ImageElement` 是只读的截图定位快照，支持：

- `rect`：`x`、`y`、`width`、`height`。
- `location`：左上角 `x`、`y`。
- `size`：`width`、`height`。
- `center`：中心点 `x`、`y`，可为浮点数。
- `score`、`scale`、`scan_id`、`image_size`、`template_size`。
- `coordinate_mapping`、`window_size`、`window_rect`、`window_center`、`window_scale`。
- `debug_paths`、`diagnostic_error`；`to_dict()` 返回可 JSON 序列化的完整元数据。

`rect` 和 `center` 始终使用截图像素坐标。默认 `window_rect` 与 `window_center` 为空，即使窗口和截图尺寸相同也不擅自假设覆盖范围相同。

调用者确认截图和窗口同原点、同方向且覆盖完整窗口时，传入 `coordinate_mode=full_window`。库检查缩放一致性后返回单独的窗口坐标，原始截图坐标保留。窗口宽高缩放比例相差超过 0.5% 时拒绝换算。

元素不持有截图或设备会话，不提供 `click()`。调用者可使用现有关键字点击经确认的窗口中心点；页面变化后应重新查找。

## 失败语义

- `IMAGE_NOT_FOUND`：没有候选达到阈值。
- `AMBIGUOUS_IMAGE_MATCH`：多个不同位置的候选分数过近。
- `INVALID_ARGUMENT`：非法参数、比例过多或 ROI 越界。
- `IMAGE_READ_ERROR` / `UNSUPPORTED_TEMPLATE` / `DEGENERATE_TEMPLATE`：图片无法读取、模板透明或缺少图像特征。
- `NO_VALID_SCALE`：所有请求尺寸都不适合当前搜索区域。
- `APPIUM_SESSION_ERROR` / `SCREEN_CHANGED` / `CONTEXT_RESTORE_ERROR`：会话、截图几何变化或上下文恢复失败。
- `COORDINATE_MAPPING_ERROR`：请求的窗口坐标换算不能成立。

Python 异常均继承 `VisionError`，通过 `code` 与 `details` 获取错误码和候选摘要。Robot 可以通过 `TRY/EXCEPT` 或 `Run Keyword And Expect Error` 匹配错误码。输入或设备错误不会降级成未找到。

## 可选诊断

显式启用后，直接导出本次已使用的内存数据，不再次截图：

```robotframework
${element}=    CV Find Image Element    ${CURDIR}/images/close.png
...    debug=always    debug_dir=${OUTPUT DIR}/vision-debug
```

每次生成一个独立目录，包含原始 `source.png`、模板原始文件、`annotated.png` 和 `metadata.json`。模板若为 JPEG，则原样保留为 `.jpg`。标注图记录 ROI 和候选框，元数据记录有效/跳过的比例、候选分数和依赖版本。原图字节不重压缩，任何导出文件都不参与匹配。

`on_failure` 只在查找失败时导出；导出失败保留原匹配结果或原异常，并通过 `diagnostic_error` 报告。默认 `none` 连匹配失败也不保存图片。

## Python 内存接口

```python
from OpenCVVision import find_image_in_memory

# source_bytes / template_bytes 由调用者提供，均为编码后的 PNG/JPEG 字节。
element = find_image_in_memory(source_bytes, template_bytes, threshold=0.8)
print(element.rect, element.center, element.score)
```

此接口不需要 Robot 或 Appium。图片全部传入字节且 `debug=none` 时，匹配不执行文件系统读写。显式导出诊断时必须自行提供 `debug_dir`。

## 验证

在仓库根目录运行：

```powershell
python -B -m unittest discover -s libraries/opencv_vision/tests -p "test_*.py" -v
```

测试使用真实 OpenCV，覆盖多尺度、相似干扰、重复目标、ROI、无文件传递、非法输入、JPEG、中文路径、诊断及上下文恢复。测试还通过真正的 Robot runner 执行 `tests/robot_smoke.robot`，其 Appium 会话为替身，不连接设备或网络。

已验证环境：Python 3.14.7、OpenCV 5.0.0、NumPy 2.5.4、Robot Framework 7.5、AppiumLibrary 3.2.1、Appium Python Client 6.0.9。当前会话访问封装了 AppiumLibrary 的内部方法 `_current_application()`，升级库后需重新验证。最低 Python 3.9 为包声明范围，尚未逐版本验证。

真实 Appium 服务与实机按钮的匹配、截图覆盖范围和点击坐标仍需在目标设备上验证。默认参数不能保证适用于所有图片，必要时收窄 ROI、缩放范围或调整模板。
