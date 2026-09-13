# -*- coding: utf-8 -*-
"""SDK 访问中枢。

集中封装对网易 ModSDK UI 接口的访问，让上层模块不直接依赖 SDK 细节。
本模块只使用 ``mod.client.extraClientApi``，不引入任何第三方库。
"""
import mod.client.extraClientApi as clientApi

ScreenNode = clientApi.GetScreenNodeCls()
ViewBinder = clientApi.GetViewBinderCls()
ViewRequest = clientApi.GetViewViewRequestCls()

# 静态资源包中 PyreactBase.json 的命名空间与模板实例路径。
# rootBase 会在 screen 的 /root 处实例化，模板作为其隐藏子控件存在。
ROOT_PATH = "/root"
TEMPLATE_NAMESPACE = "PyreactBase"

# 模板控件在 /root 下的实例名（见 PyreactBase.json）
TEMPLATE_PANEL = ROOT_PATH + "/panel_tmpl"
TEMPLATE_LABEL = ROOT_PATH + "/label_tmpl"
TEMPLATE_IMAGE = ROOT_PATH + "/image_tmpl"
TEMPLATE_BUTTON = ROOT_PATH + "/button_tmpl"
TEMPLATE_ITEM = ROOT_PATH + "/item_tmpl"
TEMPLATE_PAPER_DOLL = ROOT_PATH + "/paper_doll_tmpl"
TEMPLATE_INPUT = ROOT_PATH + "/input_tmpl"
TEMPLATE_SLIDER = ROOT_PATH + "/slider_tmpl"
TEMPLATE_SCROLL = ROOT_PATH + "/scroll_tmpl"

# 白色 1x1 纹理路径（用于纯色 Image 着色）
WHITE_TEXTURE = "textures/ui/white_bg"

# 专用文本量测控件：挂在 /root 下（始终被渲染），用于在不依赖目标控件
# 已渲染的前提下量测文字像素尺寸）。
MEASURE_LABEL_PATH = ROOT_PATH + "/measure_lbl"

# 量测控件默认文本对齐；max_width>0 时用 (max_width, MEASURE_MAX_HEIGHT)
# 覆盖以触发 SDK 自动换行。不传 max_width 时用 SetMaxSize((0.0, 0.0))，
# 文档明确 (0,0) 表示无限制，量测单行真实尺寸。
MEASURE_TEXT_ALIGN_DEFAULT = "left"
MEASURE_MAX_HEIGHT = 99999.0

# 控件名净化：JSON UI 控件名只允许 ASCII 字母数字下划线


def sanitize_name(name):
    """把任意字符串净化为合法的 JSON UI 控件名（仅 ASCII 字母数字下划线）。"""
    if name is None:
        return None
    cleaned = []
    for ch in str(name):
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch == "_":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    result = "".join(cleaned)
    if not result:
        return None
    # 不能以数字开头
    if "0" <= result[0] <= "9":
        result = "_" + result
    return result


def join_path(parent_path, name):
    """拼接父路径与控件名，返回子控件路径。"""
    if parent_path.endswith("/"):
        return parent_path + name
    return parent_path + "/" + name


def get_control(host, path):
    """按路径获取 BaseUIControl，找不到返回 None。"""
    return host.GetBaseUIControl(path)


def set_visible(control, visible, force_update=False):
    """设置控件可见性，并默认把刷新交给提交边界统一处理。"""
    if control is None:
        return
    control.SetVisible(bool(visible), bool(force_update))


def set_layer(control, layer, sync_refresh=False):
    """设置控件层级，并默认把刷新交给提交边界统一处理。"""
    if control is None:
        return
    control.SetLayer(int(layer), bool(sync_refresh), False)


def clone(host, template_path, parent_path, name):
    """克隆模板控件到 parent_path 下，命名为 name。

    延迟本次 clone 的同步刷新和自动更新。reconciler 会在同一提交中继续
    克隆并设置属性，提交结束后由宿主统一调用 ``UpdateScreen(True)``。
    这样一批控件只触发一次 SDK 的布局/数据重算，避免每个 clone 都同步
    刷新一遍界面。

    SDK 文档明确建议同一帧大量 Clone 使用 ``syncRefresh=False``；这里同时
    使用 ``forceUpdate=False``，避免 SDK 在当前帧或下一帧隐式刷新，刷新由
    Pyreact 的提交边界统一控制。
    """
    return host.Clone(template_path, parent_path, name, False, False)


def remove(host, control):
    """移除一个子控件，返回是否成功。"""
    if control is None:
        return False
    return host.RemoveChildControl(control)


def update_screen(host, force_update=True):
    """刷新屏幕，使累积的控件操作生效。"""
    host.UpdateScreen(force_update)


def register_ui(namespace, ui_name, screen_class_path, screen_def):
    """注册可由 ModSDK UI 栈创建的 screen。"""
    return clientApi.RegisterUI(
        namespace, ui_name, screen_class_path, screen_def)


def create_ui(namespace, ui_name, create_params=None):
    """创建常驻 UI；``isHud`` 等参数通过 create_params 传入。"""
    return clientApi.CreateUI(namespace, ui_name, create_params)


def push_screen(namespace, ui_name, create_params=None):
    """把已注册 UI 压入原生 UI 栈。"""
    return clientApi.PushScreen(namespace, ui_name, create_params)


def pop_top_ui():
    """弹出实际栈顶 UI，包括原生游戏 UI 与 PushScreen UI。"""
    return clientApi.PopTopUI()


def get_top_ui():
    """返回实际 UI 栈顶名称。"""
    return clientApi.GetTopUI()


def get_top_screen():
    """返回最近的 PushScreen ScreenNode；空栈时返回 None。"""
    return clientApi.GetTopScreen()


def get_screen_size():
    """返回当前游戏完整屏幕尺寸 ``(width, height)``。"""
    game = clientApi.GetEngineCompFactory().CreateGame(
        clientApi.GetLevelId())
    return game.GetScreenSize()


def get_size(host, path):
    """读取控件像素尺寸 (width, height)。"""
    ctrl = get_control(host, path)
    if ctrl is None:
        return (0.0, 0.0)
    return ctrl.GetSize()


def get_global_position(host, path):
    """读取控件在当前 screen 中的全局坐标 (x, y)。"""
    ctrl = get_control(host, path)
    if ctrl is None:
        return (0.0, 0.0)
    return ctrl.GetGlobalPosition()


def set_size(control, size, resize_children=True):
    """设置控件尺寸。

    ``resize_children`` 控制 JSON UI 内部的百分比子控件是否随父尺寸刷新。
    """
    if control is None:
        return
    control.SetSize(size, bool(resize_children))


def measure_text(host, text, font_scale=None, line_padding=None,
                 text_alignment=None, shadow=None, max_width=None):
    """用专用量测控件测量文字像素尺寸。

    目标控件可能尚未渲染（其父容器未布局、尺寸为 0），直接 GetSize 会得到 0。
    此处把文本写到 /root 下的量测控件（始终被渲染）上，借 syncSize 取得
    真实文字尺寸。font_scale/line_padding/text_alignment/shadow 需与目标一致以
    保证量测准确（line_padding 会影响多行高度，shadow 会影响 1px 边缘）。

    每次量测都先重置 measure 控件的 line_padding/font_size/align/shadow，再按
    传入值应用，避免上一次量测的属性残留到下一次（量测控件是共享单例）。

    :param max_width: 若 > 0，将 measure 控件最大宽度限制为该值，SDK 会在该
        宽度内自动换行，syncSize 返回换行后的多行宽高，用于 Label 自动换行
        布局。若为 None 或 <= 0，量测单行尺寸（不限制宽度）。
    :return: (width, height) 像素尺寸。
    """
    ctrl = get_control(host, MEASURE_LABEL_PATH)
    if ctrl is None:
        return (0.0, 0.0)
    label = ctrl.asLabel()
    if label is None:
        return (0.0, 0.0)
    t = text
    if isinstance(t, unicode):
        t = t.encode("utf-8")

    # Text measurement is synchronous and relatively expensive.  Layout is
    # often recomputed while the same labels keep their text and typography,
    # so cache successful measurements per screen host.  The host lifetime
    # bounds the cache and the cap prevents unbounded growth for dynamic text.
    cache_key = (t, font_scale, line_padding, text_alignment, shadow, max_width)
    measure_cache = getattr(host, "_pyreact_measure_cache", None)
    if measure_cache is None:
        measure_cache = {}
        host._pyreact_measure_cache = measure_cache
    cached = measure_cache.get(cache_key)
    if cached is not None:
        return cached

    # 先重置 measure 控件到干净状态，避免上次量测属性残留。
    # 每个调用独立 try/except，避免单个属性设置异常中断整个量测。
    try:
        label.SetTextLinePadding(0.0)
    except Exception:
        pass
    try:
        label.SetTextFontSize(1.0)
    except Exception:
        pass
    try:
        label.SetTextAlignment(MEASURE_TEXT_ALIGN_DEFAULT)
    except Exception:
        pass
    try:
        label.DisableTextShadow()
    except Exception:
        pass

    # 按原生文字量测所需顺序应用 style：
    # linePadding -> fontSize -> textAlign -> shadow -> text
    if line_padding is not None:
        try:
            label.SetTextLinePadding(float(line_padding))
        except (TypeError, ValueError):
            pass

    scale = font_scale if (font_scale is not None and font_scale > 0.0) else 1.0
    # 先重置到 1.0 再应用目标 scale，强制刷新（避免 SDK 内部缓存跳过同值设置）
    label.SetTextFontSize(1.0)
    label.SetTextFontSize(scale)

    if text_alignment is not None:
        try:
            label.SetTextAlignment(text_alignment)
        except Exception:
            pass

    if shadow is True:
        label.EnableTextShadow()
    elif shadow is False:
        label.DisableTextShadow()

    # max_width: >0 时限制 measure 控件宽度触发 SDK 自动换行，量测多行尺寸；
    # 否则 SetMaxSize((0,0)) 表示无限制（文档语义），量测单行真实宽度。
    if max_width is not None and max_width > 0.0:
        label.SetMaxSize((float(max_width), MEASURE_MAX_HEIGHT))
    else:
        label.SetMaxSize((0.0, 0.0))

    label.SetText(t, True)

    try:
        size = ctrl.GetSize()
    except Exception:
        size = None
    width = float(size[0]) if size and len(size) >= 2 else 0.0
    height = float(size[1]) if size and len(size) >= 2 else 0.0

    # 量测完清空文本与 max_size，保持量测控件干净，避免下次残留
    label.SetText("", True)
    label.SetMaxSize((0.0, 0.0))

    # max_width 截断：宽度不应超过传入限制
    if max_width is not None and max_width > 0.0 and width > max_width:
        width = float(max_width)

    # 防御异常返回值
    if width >= 4000.0 or height >= 4000.0:
        return (0.0, 0.0)
    # 最小宽度兜底（参考官方字体测量 demo）
    if width > 0.0 and (width / scale) < 4.0:
        width = 4.0 * scale
    result = (width, height)
    if width > 0.0 and height > 0.0:
        if len(measure_cache) >= 2048:
            measure_cache.clear()
        measure_cache[cache_key] = result
    return result
