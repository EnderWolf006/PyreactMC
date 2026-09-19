# -*- coding: utf-8 -*-
"""Primitive 组件。

- Primitive：单原生控件映射
  （Panel/Label/Image/Item/PaperDoll/Input/ScrollView/Button）。
  每个实例是一个可调用对象，
  调用后返回 Element。子类实现 ``apply_props`` 把原生属性应用到控件。
"""
from functools import partial
import math

from . import native
from .constants import (
    AlignItems,
    ButtonState,
    Color,
    JustifyContent,
    PaperDollRenderType,
    font_size_to_scale,
)
from .element import Element, normalize_children
from .style import Style


def _prop_changed(prev_props, next_props, name):
    if prev_props is None:
        return True
    return prev_props.get(name) != next_props.get(name)


def _has_auto_size(style):
    return (style is None or style.get("width") is None or
            style.get("height") is None)


def _apply_color_alpha(control, fiber, color):
    inherited = fiber.primitive_state.get("_inherited_opacity")
    if control is not None and inherited is not None and color is not None:
        final_alpha = inherited * color.a
        if fiber.primitive_state.get("_native_color_alpha") == final_alpha:
            return
        control.SetAlpha(final_alpha)
        fiber.primitive_state["_native_color_alpha"] = final_alpha
        applied = fiber.primitive_state.get("_layout_applied")
        if applied is not None:
            fiber.primitive_state["_layout_applied"] = applied[:4] + (final_alpha,)


_IMAGE_FRAME_FIELDS = frozenset(("src", "uv", "uvSize"))


def sprite_sheet_frames(frame_size, columns, rows, count=None,
                        offset=(0, 0), spacing=(0, 0)):
    """按行优先顺序构建 Image.frames 使用的图集帧。

    :param frame_size: 单帧 ``(width, height)``，单位为贴图像素。
    :param columns: 图集列数。
    :param rows: 图集行数。
    :param count: 可选帧数，默认使用整个网格。
    :param offset: 可选首帧 ``(x, y)`` 偏移，默认 ``(0, 0)``。
    :param spacing: 可选帧之间的 ``(x, y)`` 间距，默认 ``(0, 0)``。
    :return: 可直接传给 ``Image(frames=...)`` 的帧描述列表。
    """
    frame_width, frame_height = _validate_image_frame_pair(
        frame_size, "frame_size", positive=True)
    offset_x, offset_y = _validate_image_frame_pair(
        offset, "offset", non_negative=True)
    spacing_x, spacing_y = _validate_image_frame_pair(
        spacing, "spacing", non_negative=True)
    columns = _validate_image_frame_integer(columns, "columns", minimum=1)
    rows = _validate_image_frame_integer(rows, "rows", minimum=1)
    capacity = columns * rows
    if count is None:
        count = capacity
    else:
        count = _validate_image_frame_integer(count, "count", minimum=0)
        if count > capacity:
            raise ValueError("count exceeds sprite sheet grid capacity")

    frames = []
    for index in range(count):
        column = index % columns
        row = index // columns
        frames.append({
            "uv": (
                offset_x + column * (frame_width + spacing_x),
                offset_y + row * (frame_height + spacing_y),
            ),
            "uvSize": (frame_width, frame_height),
        })
    return frames


def _validate_image_frame_pair(value, name, positive=False,
                               non_negative=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise TypeError("%s must be a pair" % name)
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, long, float)):
            raise TypeError("%s values must be numbers" % name)
        if positive and item <= 0:
            raise ValueError("%s values must be greater than 0" % name)
        if non_negative and item < 0:
            raise ValueError("%s values must not be negative" % name)
    return (value[0], value[1])


def _validate_image_frame_integer(value, name, minimum):
    if isinstance(value, bool) or not isinstance(value, (int, long)):
        raise TypeError("%s must be an integer" % name)
    if value < minimum:
        raise ValueError("%s must be at least %d" % (name, minimum))
    return value


def _normalize_image_frames(value):
    """把 Image.frames 归一化为只含原生贴图字段的帧描述。"""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError("Image.frames must be a list or tuple")
    normalized = []
    for frame in value:
        if isinstance(frame, basestring):
            frame = {"src": frame}
        elif isinstance(frame, dict):
            unknown = set(frame.keys()) - _IMAGE_FRAME_FIELDS
            if unknown:
                raise ValueError(
                    "Image frame contains unsupported props: %s" %
                    ", ".join(sorted(unknown)))
            frame = dict(frame)
        else:
            raise TypeError(
                "Image frame must be a texture path or dict, got %r" %
                (frame,))
        if not frame:
            raise ValueError("Image frame must contain src, uv or uvSize")
        src = frame.get("src")
        if src is not None and not isinstance(src, basestring):
            raise TypeError("Image frame src must be a string")
        for field in ("uv", "uvSize"):
            pair = frame.get(field)
            if pair is not None and (
                    not isinstance(pair, (list, tuple)) or len(pair) != 2):
                raise TypeError("Image frame %s must be a pair" % field)
        normalized.append(frame)
    return tuple(normalized)


class Primitive(object):
    """原生控件基类。

    通用参数：
    :param key: Element 复用键，影响 diff 时的节点对齐。
    :param ref: 原生控件引用回调或带 ``current`` 字段的对象。
    :param style: Style 实例，承载布局、显示、透明度、zIndex 等通用属性。
    :param children: 子 Element、Element 列表/元组、文本或数字。
    :param **kwargs: 原生控件专属 props，由具体 Primitive 解释。
    """

    # 克隆来源模板路径（由 native.py 定义）
    template_path = None
    # fill children 默认继承 Primitive 的最终 alpha。自行管理子控件透明度的
    # Primitive 可覆盖为 False，避免通用布局覆盖其内部状态。
    fill_children_inherit_alpha = True

    def __call__(self, **kwargs):
        key = kwargs.pop("key", None)
        ref = kwargs.pop("ref", None)
        children = kwargs.pop("children", None)
        style = kwargs.pop("style", None)
        return Element(
            comp_type=self,
            props=kwargs,
            style=style,
            children=(normalize_children(children)
                      if children is not None else None),
            key=key,
            ref=ref,
        )

    def children_path(self, native_path, host=None):
        """子控件挂载的父路径，默认即自身路径。"""
        return native_path

    def fill_children(self, native_path):
        """需要铺满本控件的模板子控件路径列表（布局后由 layout 同步尺寸）。

        这些子控件用 size:100%/100% 表示铺满，但 SetSize 父控件时 SDK 默认不会
        重算子控件的相对尺寸，故由布局显式同步。默认无。
        """
        return []

    def apply_props(self, host, fiber, control, prev_props, next_props):
        """应用原生属性。子类覆盖。"""

    def props_affect_layout(self, prev_props, next_props, style):
        """props 变化是否可能改变自适应尺寸。"""
        return _has_auto_size(style)

    def apply_layout(self, host, node):
        """布局应用后的额外同步。子类按需覆盖。"""

    def apply_visual_scale(self, host, fiber, control, scale_x, scale_y):
        """视觉缩放写入后的额外同步。子类按需覆盖。"""

    def adjust_visual_size(self, width, height, scale_x, scale_y):
        """返回带 native 绘制补偿的视觉尺寸。"""
        return (width, height)

    def apply_children(self, host, node, apply_func):
        """自定义子节点布局应用。返回 True 表示已处理。"""
        return False

    def unmount(self, host, fiber):
        """卸载清理。子类可覆盖。"""


class PanelPrimitive(Primitive):
    """容器 Primitive，映射普通 panel 控件。

    参数：
    :param style: Style。常用 width、height、flex、padding、margin、
        flexDirection、alignItems、justifyContent、opacity、display。
    :param children: 子组件，挂载到 Panel 自身。

    Panel 当前没有原生专属 props。
    """
    template_path = native.TEMPLATE_PANEL

    def props_affect_layout(self, prev_props, next_props, style):
        return prev_props.get("_safeArea") != next_props.get("_safeArea")

    def apply_props(self, host, fiber, control, prev_props, next_props):
        # Panel 无原生专属属性（布局/视觉由 layout 与 renderer 处理）
        pass


class LabelPrimitive(Primitive):
    """文本 Primitive，映射 label 控件。

    参数：
    :param style: Style。控制布局、位置、透明度和可见性。
    :param content: 文本内容。unicode 会按 utf-8 编码后传给原生控件。
    :param color: Color 对象或可转换为 Color 的 int/list/tuple。
    :param fontSize: FontSize 枚举值或数值。传给原生前会乘以 0.1。
    :param textAlign: TextAlignment 枚举值。
    :param linePadding: float，多行文本的行间距（像素）。仅对换行后的多行
        文本生效，单行时无影响。对应 ModSDK ``SetTextLinePadding``。
    :param shadow: bool，是否启用文字阴影。
    :param children: 不建议传入；Label 主要通过 content 显示文本。

    原生属性应用顺序：
    linePadding -> fontSize -> textAlign -> shadow -> color -> text。
    该顺序保证 SDK 在 text 自适应尺寸前已收到全部影响排版/行高的属性。

    处于 ``Scale`` 子树时，字号会随累计纵向比例更新；为避免 native 浮点
    frame 裁掉字形边缘，缩放后的实际绘制尺寸会在右下额外扩 0.94px。
    """
    template_path = native.TEMPLATE_LABEL
    _VISUAL_SIZE_EPSILON = 0.94

    def props_affect_layout(self, prev_props, next_props, style):
        if not _has_auto_size(style):
            return False
        for name in ("content", "fontSize", "linePadding", "textAlign", "shadow"):
            if _prop_changed(prev_props, next_props, name):
                return True
        return False

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        label = control.asLabel()
        if label is None:
            return
        # 行间距：必须在 SetText 之前设置，SDK 才会在 syncSize/换行时计入行高
        line_padding = next_props.get("linePadding")
        line_padding_changed = _prop_changed(prev_props, next_props, "linePadding")
        if line_padding_changed:
            try:
                label.SetTextLinePadding(float(line_padding) if line_padding is not None else 0.0)
            except (TypeError, ValueError):
                pass
        # 字号
        font_size_changed = _prop_changed(prev_props, next_props, "fontSize")
        if font_size_changed:
            visual_scale = fiber.primitive_state.get(
                "_visual_scale", (1.0, 1.0))
            self.apply_visual_scale(
                host, fiber, control, visual_scale[0], visual_scale[1])
        # 文本对齐
        text_alignment = next_props.get("textAlign")
        text_alignment_changed = _prop_changed(prev_props, next_props, "textAlign")
        if text_alignment_changed:
            label.SetTextAlignment(text_alignment if text_alignment is not None else "left")
        # 阴影
        shadow = next_props.get("shadow")
        shadow_changed = _prop_changed(prev_props, next_props, "shadow")
        if shadow is True and shadow_changed:
            label.EnableTextShadow()
        elif shadow_changed:
            # 模板默认即为 false；显式关闭
            label.DisableTextShadow()
        # 颜色
        color = next_props.get("color")
        color_obj = _to_color_obj(color) or Color(1.0, 1.0, 1.0)
        if _prop_changed(prev_props, next_props, "color"):
            label.SetTextColor(color_obj.to_rgb_tuple())
            _apply_color_alpha(control, fiber, color_obj)
        # 文本内容最后设置；尺寸由 Pyreact 布局引擎的独立量测控件负责。
        content = next_props.get("content")
        typography_changed = (line_padding_changed or font_size_changed or
                              text_alignment_changed or shadow_changed)
        if typography_changed or _prop_changed(prev_props, next_props, "content"):
            # SDK 的 SetText 期望 utf-8 str；若拿到 unicode 则编码回 str
            text = "" if content is None else content
            if isinstance(text, unicode):
                text = text.encode("utf-8")
            elif not isinstance(text, str):
                text = str(text)
            # 布局引擎会通过独立量测控件计算文本尺寸；避免每个 Label
            # 在提交期间同步调整原生文本框尺寸。
            label.SetText(text, False)

    def apply_visual_scale(self, host, fiber, control, scale_x, scale_y):
        """按累计纵向 scale 更新原生字号，保持字形等比。"""
        if control is None:
            return
        label = control.asLabel()
        if label is None:
            return
        font_size = fiber.props.get("fontSize") if fiber.props else None
        base_scale = font_size_to_scale(font_size)
        if base_scale is None:
            base_scale = 1.0
        # 字号只能接受单个比例。非等比缩放时跟随纵轴，保持字形自身比例。
        target_scale = base_scale * abs(float(scale_y))
        previous = fiber.primitive_state.get("_native_font_scale")
        if previous == target_scale:
            return
        label.SetTextFontSize(target_scale)
        fiber.primitive_state["_native_font_scale"] = target_scale

    def adjust_visual_size(self, width, height, scale_x, scale_y):
        """扩张缩放后的 native frame，避免浮点舍入裁掉字形边缘。"""
        if (width <= 0.0 or height <= 0.0 or
                (scale_x == 1.0 and scale_y == 1.0)):
            return (width, height)
        return (
            width + self._VISUAL_SIZE_EPSILON,
            height + self._VISUAL_SIZE_EPSILON,
        )


class ImagePrimitive(Primitive):
    """图片 Primitive，映射 image 控件。

    参数：
    :param style: Style。控制布局、位置、透明度和可见性。
    :param src: 贴图路径。
    :param color: Color 对象或可转换为 Color 的 int/list/tuple。
    :param uv: 二元组，设置贴图 UV 起点。
    :param uvSize: 二元组，设置贴图 UV 尺寸。
    :param rotatePivot: 二元组，设置旋转锚点。
    :param rotate: 数值角度。内部按上次角度计算增量调用 Rotate。
    :param grayscale: bool，是否灰度显示。
    :param clipRatio: float，设置贴图裁剪比例。
    :param imageAdaption: ImageAdaptionType 枚举值。
    :param nineSliceData: 四元组，仅九宫格适配时使用，顺序为左、右、上、下。
    :param frames: 序列帧列表/元组。每帧是贴图路径，或包含 src、uv、uvSize
        的 dict。帧字段直接写入原生 Image，不触发组件重渲染和布局。
    :param frameDuration: 每帧持续秒数，默认 0.1，必须大于 0。
    :param playing: bool，是否播放，默认 True。False 时停在当前帧。
    :param loop: bool，是否循环，默认 True。
    :param initialFrame: 初始帧索引，默认 0。
    :param onAnimationEnd: 非循环动画播放结束时调用的无参回调。
    :param children: 子组件，挂载到 Image 自身。
    """
    template_path = native.TEMPLATE_IMAGE

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        image = control.asImage()
        if image is None:
            return
        frames = _normalize_image_frames(next_props.get("frames"))
        restore_static = bool(
            prev_props is not None and prev_props.get("frames") and not frames)
        src = next_props.get("src")
        if restore_static or _prop_changed(prev_props, next_props, "src"):
            image.SetSprite(src if src is not None else native.WHITE_TEXTURE)
        color = next_props.get("color")
        color_obj = _to_color_obj(color) or Color(1.0, 1.0, 1.0)
        if _prop_changed(prev_props, next_props, "color"):
            image.SetSpriteColor(color_obj.to_rgb_tuple())
            _apply_color_alpha(control, fiber, color_obj)
        uv = next_props.get("uv")
        if uv is not None and (
                restore_static or _prop_changed(prev_props, next_props, "uv")):
            image.SetSpriteUV((float(uv[0]), float(uv[1])))
        uv_size = next_props.get("uvSize")
        if uv_size is not None and (
                restore_static or
                _prop_changed(prev_props, next_props, "uvSize")):
            image.SetSpriteUVSize((float(uv_size[0]), float(uv_size[1])))
        # 旋转锚点
        rotate_pivot = next_props.get("rotatePivot")
        if rotate_pivot is not None and _prop_changed(prev_props, next_props, "rotatePivot"):
            image.SetRotatePivot((float(rotate_pivot[0]), float(rotate_pivot[1])))
        # 旋转角度：Rotate 是相对增量，用 fiber state 记录上次角度，设增量
        rotate_angle = next_props.get("rotate")
        if _prop_changed(prev_props, next_props, "rotate"):
            target = float(rotate_angle) if rotate_angle is not None else 0.0
            last = fiber.primitive_state.get("rotate", 0.0)
            image.Rotate(target - last)
            fiber.primitive_state["rotate"] = target
        # 灰度
        grayscale = next_props.get("grayscale")
        if _prop_changed(prev_props, next_props, "grayscale"):
            image.SetSpriteGray(bool(grayscale))
        # 裁剪比例（进度条等），clipDirection 由模板/JSON 决定
        clip_ratio = next_props.get("clipRatio")
        if _prop_changed(prev_props, next_props, "clipRatio"):
            image.SetSpriteClipRatio(float(clip_ratio) if clip_ratio is not None else 0.0)
        # 图片适配方式（九宫格等）。nineSliceData 仅九宫模式需要：左、右、上、下
        adaption_type = next_props.get("imageAdaption")
        if adaption_type is not None and (
                _prop_changed(prev_props, next_props, "imageAdaption") or
                _prop_changed(prev_props, next_props, "nineSliceData")):
            nine_slice_data = next_props.get("nineSliceData")
            if nine_slice_data is not None:
                image.SetImageAdaptionType(
                    adaption_type,
                    (float(nine_slice_data[0]), float(nine_slice_data[1]),
                     float(nine_slice_data[2]), float(nine_slice_data[3])),
                )
            else:
                image.SetImageAdaptionType(adaption_type)

        self._sync_frame_animation(host, fiber, image, frames, next_props)

    def _sync_frame_animation(self, host, fiber, image, frames, next_props):
        state = fiber.primitive_state.get("_image_frame_animation")
        if not frames:
            if state is not None:
                self._set_frame_animation_active(host, state, False)
                fiber.primitive_state.pop("_image_frame_animation", None)
            return

        try:
            frame_duration = float(next_props.get("frameDuration", 0.1))
        except (TypeError, ValueError):
            raise TypeError("Image.frameDuration must be a number")
        if (math.isnan(frame_duration) or math.isinf(frame_duration) or
                frame_duration <= 0.0):
            raise ValueError("Image.frameDuration must be finite and greater than 0")

        initial_frame = next_props.get("initialFrame", 0)
        if (isinstance(initial_frame, bool) or
                not isinstance(initial_frame, (int, long))):
            raise TypeError("Image.initialFrame must be an integer")
        if initial_frame < 0 or initial_frame >= len(frames):
            raise ValueError("Image.initialFrame is outside frames")

        on_end = next_props.get("onAnimationEnd")
        if on_end is not None and not callable(on_end):
            raise TypeError("Image.onAnimationEnd must be callable")
        playing = bool(next_props.get("playing", True))
        loop = bool(next_props.get("loop", True))

        if state is None:
            slot = {
                "fiber": fiber,
                "active": False,
            }
            state = {
                "slot": slot,
                "frames": frames,
                "frame_duration": frame_duration,
                "initial_frame": initial_frame,
                "index": initial_frame,
                "elapsed": 0.0,
                "last_time": None,
                "playing": playing,
                "loop": loop,
                "completed": False,
                "on_end": on_end,
            }
            slot["callback"] = partial(
                self._tick_frame_animation, host, fiber)
            fiber.primitive_state["_image_frame_animation"] = state
        else:
            frames_changed = state["frames"] != frames
            initial_changed = state["initial_frame"] != initial_frame
            duration_changed = state["frame_duration"] != frame_duration
            was_playing = state["playing"]
            was_looping = state["loop"]
            state["frames"] = frames
            state["frame_duration"] = frame_duration
            state["initial_frame"] = initial_frame
            state["playing"] = playing
            state["loop"] = loop
            state["on_end"] = on_end
            if frames_changed or initial_changed:
                state["index"] = initial_frame
                state["elapsed"] = 0.0
                state["last_time"] = None
                state["completed"] = False
            elif duration_changed:
                state["elapsed"] = 0.0
                state["last_time"] = None
            if playing != was_playing:
                state["last_time"] = None
            if playing and not was_playing and state["completed"]:
                state["index"] = initial_frame
                state["elapsed"] = 0.0
                state["last_time"] = None
                state["completed"] = False
            elif loop and not was_looping and state["completed"]:
                state["last_time"] = None
                state["completed"] = False

        self._apply_frame(image, state["frames"][state["index"]])
        active = state["playing"] and not state["completed"]
        self._set_frame_animation_active(host, state, active)

    @staticmethod
    def _apply_frame(image, frame):
        src = frame.get("src")
        if src is not None:
            image.SetSprite(src)
        uv = frame.get("uv")
        if uv is not None:
            image.SetSpriteUV((float(uv[0]), float(uv[1])))
        uv_size = frame.get("uvSize")
        if uv_size is not None:
            image.SetSpriteUVSize((float(uv_size[0]), float(uv_size[1])))

    @staticmethod
    def _set_frame_animation_active(host, state, active):
        slot = state["slot"]
        slot["active"] = bool(active)
        if active and slot.get("_registration_id") is None:
            host.pyreact_register_animation_frame(slot)
        elif not active and slot.get("_registration_id") is not None:
            host.pyreact_unregister_animation_frame(slot)

    def _tick_frame_animation(self, host, fiber, now):
        state = fiber.primitive_state.get("_image_frame_animation")
        if state is None or not state["playing"] or state["completed"]:
            return
        now = float(now)
        if state["last_time"] is None:
            state["last_time"] = now
            return
        delta = max(0.0, now - state["last_time"])
        state["last_time"] = now
        elapsed = state["elapsed"] + delta
        steps = int(elapsed / state["frame_duration"])
        if steps <= 0:
            state["elapsed"] = elapsed
            return
        state["elapsed"] = elapsed - steps * state["frame_duration"]

        frames = state["frames"]
        previous_index = state["index"]
        completed = False
        if state["loop"]:
            state["index"] = (previous_index + steps) % len(frames)
        else:
            steps_until_end = len(frames) - previous_index
            if steps >= steps_until_end:
                state["index"] = len(frames) - 1
                completed = True
            else:
                state["index"] = previous_index + steps

        if state["index"] != previous_index:
            control = native.get_control(host, fiber.native_path)
            image = control.asImage() if control is not None else None
            if image is not None:
                self._apply_frame(image, frames[state["index"]])
                host._commit_native_dirty = True

        if completed:
            state["completed"] = True
            self._set_frame_animation_active(host, state, False)
            callback = state.get("on_end")
            if callback is not None:
                callback()

    def unmount(self, host, fiber):
        state = fiber.primitive_state.pop("_image_frame_animation", None)
        if state is not None:
            self._set_frame_animation_active(host, state, False)


class ItemPrimitive(Primitive):
    """物品展示 Primitive，映射原生 ItemRenderer 控件。

    参数：
    :param style: Style。通常设置 width、height。
    :param identifier: 物品 identifier，例如 ``minecraft:stone_sword``。
    :param aux: 物品附加值，默认 0。
    :param enchant: bool，是否显示附魔效果。
    :param userData: 物品 userData，空 dict 会视为 None。
    :param itemDict: ModSDK 物品字典。优先读取 newItemName/newAuxValue，
        并支持 itemName/auxValue、userData、enchantData、modEnchantData。
    """
    template_path = native.TEMPLATE_ITEM

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        item = control.asItemRenderer()
        if item is None:
            return
        item_props = self._resolve_item_props(next_props)
        if prev_props is not None:
            previous_item_props = self._resolve_item_props(prev_props)
            if previous_item_props == item_props:
                return
        item_name = self._safe_text(item_props.get("identifier"))
        if not item_name:
            return
        aux = item_props.get("aux")
        if aux is None:
            aux = 0
        enchant = item_props.get("enchant")
        if enchant is None:
            enchant = False
        user_data = item_props.get("userData")
        if isinstance(user_data, dict) and not user_data:
            user_data = None
        item.SetUiItem(item_name, int(aux), self._to_bool(enchant), user_data)

    def _resolve_item_props(self, props):
        resolved = {
            "identifier": None,
            "aux": None,
            "enchant": None,
            "userData": None,
        }
        if not isinstance(props, dict):
            return resolved

        item_dict = props.get("itemDict")
        if isinstance(item_dict, dict):
            resolved.update(self._build_item_props_from_dict(item_dict))

        if props.get("identifier") is not None:
            resolved["identifier"] = props.get("identifier")

        if props.get("aux") is not None:
            resolved["aux"] = props.get("aux")

        if props.get("enchant") is not None:
            resolved["enchant"] = props.get("enchant")

        if props.get("userData") is not None:
            resolved["userData"] = props.get("userData")

        return resolved

    def _build_item_props_from_dict(self, item_dict):
        resolved = {
            "identifier": None,
            "aux": None,
            "enchant": None,
            "userData": None,
        }
        if not isinstance(item_dict, dict):
            return resolved

        if item_dict.get("newItemName") is not None:
            resolved["identifier"] = item_dict.get("newItemName")
        elif item_dict.get("itemName") is not None:
            resolved["identifier"] = item_dict.get("itemName")

        if item_dict.get("newAuxValue") is not None:
            resolved["aux"] = item_dict.get("newAuxValue")
        elif item_dict.get("auxValue") is not None:
            resolved["aux"] = item_dict.get("auxValue")

        if item_dict.get("userData") is not None:
            resolved["userData"] = item_dict.get("userData")

        enchant_data = item_dict.get("enchantData")
        mod_enchant_data = item_dict.get("modEnchantData")
        resolved["enchant"] = bool(enchant_data or mod_enchant_data)

        return resolved

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, long, float)):
            return value != 0
        if isinstance(value, basestring):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _safe_text(self, value):
        if value is None:
            return ""
        if isinstance(value, unicode):
            return value.encode("utf-8")
        return str(value)


class PaperDollPrimitive(Primitive):
    """网易纸娃娃 Primitive，映射 ``netease_paper_doll_renderer``。

    参数：
    :param style: Style。通常设置稳定的 width、height，并可使用 opacity、
        visible、zIndex 等通用属性。
    :param renderType: PaperDollRenderType，默认 entity。
    :param entityId: 实体运行时 ID；与 entityIdentifier 同传时优先使用。
    :param entityIdentifier: 实体 identifier，例如 ``minecraft:cow``。
    :param skeletonModelName: 骨骼模型名称。
    :param animation: 骨骼动画名称，ModSDK 默认 ``idle``。
    :param animationLooped: bool，骨骼动画是否循环，ModSDK 默认 True。
    :param blockGeometryModelName: CombineBlockPaletteToGeometry 返回的网格体
        模型名称。
    :param scale: float，模型缩放比例，ModSDK 默认 1.0。
    :param renderDepth: int，渲染深度，用于处理 UI 遮挡剔除。
    :param initRotX: float，初始 X 轴旋转角度。
    :param initRotY: float，初始 Y 轴旋转角度。
    :param initRotZ: float，初始 Z 轴旋转角度。
    :param molangDict: dict，MoLang 变量名到 float 的映射。
    :param rotationAxis: 三元组，手势旋转所环绕的轴。
    :param lightDirection: 三元组，骨骼模型的光照方向；仅 skeleton 模式支持。
    :param children: 不建议传入；纸娃娃主要用于渲染模型。

    ``ref.current`` 是 BaseUIControl。如需异步取得模型 ID，可先调用
    ``ref.current.asNeteasePaperDoll()``，再调用 ``GetModelId()``。官方文档
    要求不要在 RenderEntity/RenderSkeletonModel 后立即读取模型 ID。
    """
    template_path = native.TEMPLATE_PAPER_DOLL

    _COMMON_PARAM_MAP = (
        ("scale", "scale"),
        ("initRotX", "init_rot_x"),
        ("initRotY", "init_rot_y"),
        ("initRotZ", "init_rot_z"),
        ("molangDict", "molang_dict"),
        ("rotationAxis", "rotation_axis"),
    )
    _ENTITY_PARAM_MAP = (
        ("entityId", "entity_id"),
        ("entityIdentifier", "entity_identifier"),
        ("renderDepth", "render_depth"),
    )
    _SKELETON_PARAM_MAP = (
        ("skeletonModelName", "skeleton_model_name"),
        ("animation", "animation"),
        ("animationLooped", "animation_looped"),
        ("renderDepth", "render_depth"),
        ("lightDirection", "light_direction"),
    )
    _BLOCK_GEOMETRY_PARAM_MAP = (
        ("blockGeometryModelName", "block_geometry_model_name"),
    )

    def props_affect_layout(self, prev_props, next_props, style):
        return False

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        paper_doll = control.asNeteasePaperDoll()
        if paper_doll is None:
            return

        render_type = (next_props.get("renderType") or
                       PaperDollRenderType.entity)
        params = self._build_params(render_type, next_props)
        if not self._has_render_source(render_type, params):
            return

        if prev_props is not None:
            previous_type = (prev_props.get("renderType") or
                             PaperDollRenderType.entity)
            if (previous_type == render_type and
                    self._build_params(previous_type, prev_props) == params):
                return

        if render_type == PaperDollRenderType.entity:
            paper_doll.RenderEntity(params)
        elif render_type == PaperDollRenderType.skeleton:
            paper_doll.RenderSkeletonModel(params)
        elif render_type == PaperDollRenderType.block_geometry:
            paper_doll.RenderBlockGeometryModel(params)

    def _build_params(self, render_type, props):
        params = {}
        param_map = self._COMMON_PARAM_MAP
        if render_type == PaperDollRenderType.entity:
            param_map += self._ENTITY_PARAM_MAP
        elif render_type == PaperDollRenderType.skeleton:
            param_map += self._SKELETON_PARAM_MAP
        elif render_type == PaperDollRenderType.block_geometry:
            param_map += self._BLOCK_GEOMETRY_PARAM_MAP
        for prop_name, native_name in param_map:
            value = props.get(prop_name)
            if value is None:
                continue
            if prop_name in ("rotationAxis", "lightDirection"):
                value = self._to_vec3(value)
                if value is None:
                    continue
            params[native_name] = value
        return params

    def _has_render_source(self, render_type, params):
        if render_type == PaperDollRenderType.entity:
            return bool(params.get("entity_id") or
                        params.get("entity_identifier"))
        if render_type == PaperDollRenderType.skeleton:
            return bool(params.get("skeleton_model_name"))
        if render_type == PaperDollRenderType.block_geometry:
            return bool(params.get("block_geometry_model_name"))
        return False

    def _to_vec3(self, value):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            return (float(value[0]), float(value[1]), float(value[2]))
        except (TypeError, ValueError):
            return None


class InputPrimitive(Primitive):
    """文本输入 Primitive，映射 ``common.text_edit_box``。

    参数：
    :param style: Style。控制输入框尺寸、位置、透明度和可见性。
    :param value: str 或 unicode。受控输入值；传入后原生文本会与该值同步。
    :param onChange: callable。文本改变时回调，接收一个文本参数。
    :param children: 子组件，挂载到输入框自身。

    不传 ``value`` 时为非受控输入，文本由原生控件维护，并在组件重渲染后保留。
    """
    template_path = native.TEMPLATE_INPUT

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        edit_box = control.asTextEditBox()
        if edit_box is None:
            return

        host.pyreact_register_input(
            fiber.native_path,
            next_props.get("onChange"),
        )

        if prev_props is not None and not _prop_changed(
                prev_props, next_props, "value"):
            return

        current = self._get_text(edit_box)
        value = next_props.get("value")
        if value is not None:
            desired = self._to_text(value)
            host.pyreact_set_input_controlled_value(fiber.native_path, desired)
            if current != desired:
                try:
                    edit_box.SetEditText(desired)
                except Exception:
                    pass
            host.pyreact_set_input_value(fiber.native_path, desired)
        else:
            host.pyreact_unset_input_controlled_value(fiber.native_path)
            # 保留非受控输入在组件重渲染或控件重新创建后的内容。
            cached = host.pyreact_get_input_value(fiber.native_path)
            if cached is None:
                if current is not None:
                    host.pyreact_set_input_value(fiber.native_path, current)
            elif current != cached:
                try:
                    edit_box.SetEditText(cached)
                except Exception:
                    pass

    def unmount(self, host, fiber):
        host.pyreact_unregister_input(fiber.native_path)

    def _get_text(self, edit_box):
        try:
            value = edit_box.GetEditText()
        except Exception:
            return None
        if value is None:
            return None
        return self._to_text(value)

    def _to_text(self, value):
        if isinstance(value, unicode):
            return value.encode("utf-8")
        if isinstance(value, str):
            return value
        return str(value)


class SliderPrimitive(Primitive):
    """滑块 Primitive，映射 ``common.slider``。

    参数：
    :param style: Style。控制滑块尺寸、位置、透明度和可见性。
    :param value: int 或 float。受控滑块值；传入后原生值会与该值同步。
    :param steps: int。原生滑块格数，默认 1（0.0 到 1.0 的连续值）；
        大于 1 时为固定格滑块，值范围为 0 到 steps - 1。
    :param onChange: callable。值改变时回调，接收一个 float 参数。
    :param children: 不建议传入；Slider 主要通过原生滑块交互。

    不传 ``value`` 时为非受控滑块，值由原生控件维护，并在组件重渲染后保留。
    """
    template_path = native.TEMPLATE_SLIDER

    def props_affect_layout(self, prev_props, next_props, style):
        return False

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        slider = control.asSlider()
        if slider is None:
            return

        host.pyreact_register_slider(
            fiber.native_path,
            next_props.get("onChange"),
        )

        value_changed = _prop_changed(prev_props, next_props, "value")
        steps_changed = _prop_changed(prev_props, next_props, "steps")
        if prev_props is not None and not value_changed and not steps_changed:
            return

        steps = self._to_steps(next_props.get("steps"))
        current = self._get_value(slider)
        value = next_props.get("value")
        if value is not None:
            desired = self._to_value(value)
            if desired is None:
                host.pyreact_unset_slider_controlled_value(fiber.native_path)
                return
            host.pyreact_set_slider_controlled_value(
                fiber.native_path,
                desired,
            )
        else:
            host.pyreact_unset_slider_controlled_value(fiber.native_path)
            cached = host.pyreact_get_slider_value(fiber.native_path)
            desired = current if cached is None else cached

        self._set_property_bag(control, steps, desired)
        if desired is not None and current != desired:
            try:
                slider.SetSliderValue(desired)
            except Exception:
                pass
        if desired is not None:
            host.pyreact_set_slider_value(fiber.native_path, desired)

    def unmount(self, host, fiber):
        host.pyreact_unregister_slider(fiber.native_path)

    def _get_value(self, slider):
        try:
            return float(slider.GetSliderValue())
        except (TypeError, ValueError):
            return None
        except Exception:
            return None

    def _to_value(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_steps(self, value):
        try:
            steps = int(value) if value is not None else 1
        except (TypeError, ValueError):
            steps = 1
        return max(1, steps)

    def _set_property_bag(self, control, steps, value):
        bag = {
            "#slider_steps": steps,
            "#slider_value": 0.0 if value is None else value,
        }
        try:
            control.SetPropertyBag(bag)
        except Exception:
            pass


class ScrollViewPrimitive(Primitive):
    """滚动容器 Primitive，映射 common.scrolling_panel。

    参数：
    :param style: Style。必须提供稳定尺寸，例如 width/height 或 flex。
    :param showScrollbar: bool，是否显示滚动条，默认 True。
    :param children: 子组件。子组件会挂载到 scrolling_content 路径下。

    说明：
    ScrollView 是 Primitive，不再内置 contentContainerStyle。
    需要内容容器样式时，在 children 中显式放入 Panel，或使用 ListView。
    """
    template_path = native.TEMPLATE_SCROLL

    @staticmethod
    def _get_scroll_view(control):
        """从 ScrollView 模板 ref 解析实际 ScrollViewUIControl。"""
        if control is None:
            return None

        candidates = [control]
        for path in ("/scroll_mouse/scroll_view", "/scroll_touch/scroll_view"):
            try:
                child = control.GetChildByPath(path)
            except Exception:
                child = None
            if child is not None:
                candidates.append(child)

        for candidate in candidates:
            try:
                scroll_view = candidate.asScrollView()
            except Exception:
                scroll_view = None
            if scroll_view is not None:
                return scroll_view
        return None

    @staticmethod
    def scroll_to(control, position):
        """设置 ScrollView 的像素滚动位置。

        ``control`` 通常来自 ``ScrollView`` 的 ``ref``。模板根控件本身
        不是 ScrollView 时，会自动查找 touch/mouse 分支中的实际控件。
        """
        scroll_view = ScrollViewPrimitive._get_scroll_view(control)
        if scroll_view is None:
            return False
        try:
            scroll_view.SetScrollViewPos(position)
            return True
        except Exception:
            return False

    @staticmethod
    def scroll_to_percent(control, percent):
        """设置 ScrollView 的百分比滚动位置，范围为 0 到 100。"""
        scroll_view = ScrollViewPrimitive._get_scroll_view(control)
        if scroll_view is None:
            return False
        try:
            scroll_view.SetScrollViewPercentValue(percent)
            return True
        except Exception:
            return False

    @staticmethod
    def get_scroll_position(control):
        """读取 ScrollView 当前顶部内容的像素位置，失败时返回 None。"""
        scroll_view = ScrollViewPrimitive._get_scroll_view(control)
        if scroll_view is None:
            return None
        try:
            return scroll_view.GetScrollViewPos()
        except Exception:
            return None

    @staticmethod
    def scroll_to_top(control):
        """将 ScrollView 滚动到内容顶部。"""
        return ScrollViewPrimitive.scroll_to_percent(control, 0)

    def props_affect_layout(self, prev_props, next_props, style):
        return False

    def apply_props(self, host, fiber, control, prev_props, next_props):
        show_scrollbar = next_props.get("showScrollbar", True)
        if prev_props is not None and not _prop_changed(
                prev_props, next_props, "showScrollbar"):
            return
        track_path = self._scrollbar_track_path(fiber.native_path, host)
        track = native.get_control(host, track_path)
        if track is not None:
            native.set_visible(track, show_scrollbar)

    def children_path(self, native_path, host=None):
        return self._content_path(native_path, host)

    def fill_children(self, native_path):
        touch_view = native.join_path(native.join_path(native_path, "scroll_touch"), "scroll_view")
        mouse_view = native.join_path(native.join_path(native_path, "scroll_mouse"), "scroll_view")
        return [
            native.join_path(native_path, "scroll_touch"),
            native.join_path(native_path, "scroll_mouse"),
            touch_view,
            touch_view + "/panel",
            touch_view + "/panel/bar_and_track",
            touch_view + "/panel/background_and_viewport",
            touch_view + "/panel/background_and_viewport/scrolling_view_port",
            mouse_view,
            mouse_view + "/stack_panel",
            mouse_view + "/stack_panel/bar_and_track",
            mouse_view + "/stack_panel/background_and_viewport",
            mouse_view + "/stack_panel/background_and_viewport/scrolling_view_port",
        ]

    def apply_layout(self, host, node):
        native_path = node.fiber.native_path
        show_scrollbar = node.fiber.props.get("showScrollbar", True) if node.fiber.props else True
        scroll_view_path = self._real_scroll_view_path(native_path, host)
        layout_signature = (node.frame_w, node.frame_h, show_scrollbar,
                            scroll_view_path)
        state = node.fiber.primitive_state
        if state.get("_scroll_layout_signature") != layout_signature:
            self._sync_scroll_branches(host, native_path, node.frame_w, node.frame_h)
            scroll_view = native.get_control(host, scroll_view_path)
            if scroll_view is not None:
                native.set_size(scroll_view, (node.frame_w, node.frame_h))
                scroll_view.SetPosition((0.0, 0.0))
                native.set_visible(scroll_view, True)
            self._sync_viewport(host, scroll_view_path, node.frame_w, node.frame_h)
            self._sync_all_scroll_internals(host, native_path, node.frame_w, node.frame_h, show_scrollbar)
            state["_scroll_layout_signature"] = layout_signature

        content_path = self._content_path(native_path, host)
        content = native.get_control(host, content_path)
        if content is None:
            return
        content_w, content_h = self._scroll_content_size(node)
        content_signature = (content_w, content_h)
        if state.get("_scroll_content_signature") != content_signature:
            native.set_size(content, content_signature, False)
            state["_scroll_content_signature"] = content_signature

    def apply_children(self, host, node, apply_func):
        content_path = self._content_path(node.fiber.native_path, host)
        content = native.get_control(host, content_path)
        content_w, content_h = self._scroll_content_size(node)
        if content is not None:
            content_signature = (content_w, content_h, node.inherited_opacity)
            state = node.fiber.primitive_state
            if state.get("_scroll_children_signature") != content_signature:
                native.set_visible(content, True)
                content.SetAlpha(node.inherited_opacity)
                native.set_size(content, (content_w, content_h), False)
                state["_scroll_children_signature"] = content_signature
        for child in node.children:
            apply_func(
                child,
                host,
                node.frame_x,
                node.frame_y,
                node.visual_scale_x,
                node.visual_scale_y,
            )
        return True

    def _scroll_content_size(self, node):
        content_w = node.frame_w
        content_h = node.frame_h
        if getattr(node, "content_w", 0.0) > content_w:
            content_w = node.content_w
        if getattr(node, "content_h", 0.0) > content_h:
            content_h = node.content_h
        return (max(0.0, content_w), max(0.0, content_h))

    def _child_bounds(self, child, origin_x, origin_y):
        right = (child.frame_x - origin_x) + child.frame_w
        bottom = (child.frame_y - origin_y) + child.frame_h
        if getattr(child, "content_w", 0.0) > child.frame_w:
            right = (child.frame_x - origin_x) + child.content_w
        if getattr(child, "content_h", 0.0) > child.frame_h:
            bottom = (child.frame_y - origin_y) + child.content_h
        for grand in child.children:
            gr, gb = self._child_bounds(grand, origin_x, origin_y)
            if gr > right:
                right = gr
            if gb > bottom:
                bottom = gb
        return (right, bottom)

    def _sync_scroll_branches(self, host, native_path, width, height):
        paths = [
            native.join_path(native_path, "scroll_touch"),
            native.join_path(native_path, "scroll_mouse"),
        ]
        for path in paths:
            ctrl = native.get_control(host, path)
            if ctrl is not None:
                native.set_visible(ctrl, True)
                native.set_size(ctrl, (width, height))
                ctrl.SetPosition((0.0, 0.0))

    def _sync_viewport(self, host, scroll_view_path, width, height):
        if not scroll_view_path:
            return
        if "/scroll_touch/" in scroll_view_path:
            paths = [
                scroll_view_path + "/panel",
                scroll_view_path + "/panel/background_and_viewport",
                scroll_view_path + "/panel/background_and_viewport/scrolling_view_port",
            ]
        else:
            paths = [
                scroll_view_path + "/stack_panel",
                scroll_view_path + "/stack_panel/background_and_viewport",
                scroll_view_path + "/stack_panel/background_and_viewport/scrolling_view_port",
            ]
        for path in paths:
            ctrl = native.get_control(host, path)
            if ctrl is not None:
                native.set_visible(ctrl, True)
                native.set_size(ctrl, (width, height))
                ctrl.SetPosition((0.0, 0.0))

    def _sync_all_scroll_internals(self, host, native_path, width, height, show_scrollbar):
        touch_view = native.join_path(native.join_path(native_path, "scroll_touch"), "scroll_view")
        mouse_view = native.join_path(native.join_path(native_path, "scroll_mouse"), "scroll_view")
        self._sync_scroll_view_branch(host, touch_view, True, width, height, show_scrollbar)
        self._sync_scroll_view_branch(host, mouse_view, False, width, height, show_scrollbar)

    def _sync_scroll_view_branch(self, host, scroll_view_path, is_touch, width, height, show_scrollbar):
        scroll_view = native.get_control(host, scroll_view_path)
        if scroll_view is not None:
            native.set_visible(scroll_view, True)
            native.set_size(scroll_view, (width, height))
            scroll_view.SetPosition((0.0, 0.0))

        if is_touch:
            body_path = scroll_view_path + "/panel"
            track_path = body_path + "/bar_and_track"
        else:
            body_path = scroll_view_path + "/stack_panel"
            track_path = body_path + "/bar_and_track"

        body = native.get_control(host, body_path)
        if body is not None:
            native.set_visible(body, True)
            native.set_size(body, (width, height))
            body.SetPosition((0.0, 0.0))

        bg_path = body_path + "/background_and_viewport"
        viewport_path = bg_path + "/scrolling_view_port"
        for path in (bg_path, viewport_path):
            ctrl = native.get_control(host, path)
            if ctrl is not None:
                native.set_visible(ctrl, True)
                native.set_size(ctrl, (width, height))
                ctrl.SetPosition((0.0, 0.0))

        track = native.get_control(host, track_path)
        if track is not None:
            native.set_visible(track, show_scrollbar)
            native.set_size(track, (2.0, height))
            track.SetPosition((max(0.0, width - 2.0), 0.0))

    def _real_scroll_view_path(self, native_path, host=None):
        cache_key = native_path
        cache = getattr(self, "_scroll_path_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._scroll_path_cache = cache
        if cache.get(cache_key):
            return cache[cache_key]

        touch_path = native.join_path(native.join_path(native_path, "scroll_touch"), "scroll_view")
        mouse_path = native.join_path(native.join_path(native_path, "scroll_mouse"), "scroll_view")

        if host is not None:
            mouse = native.get_control(host, mouse_path)
            if mouse is not None:
                cache[cache_key] = mouse_path
                return mouse_path

            touch = native.get_control(host, touch_path)
            if touch is not None:
                cache[cache_key] = touch_path
                return touch_path

        return ""

    def _content_path(self, native_path, host=None):
        scroll_view_path = self._real_scroll_view_path(native_path, host)
        candidates = [
            scroll_view_path + "/panel/background_and_viewport/scrolling_view_port/scrolling_content",
            scroll_view_path + "/stack_panel/background_and_viewport/scrolling_view_port/scrolling_content",
        ]
        if host is not None:
            for path in candidates:
                if native.get_control(host, path) is not None:
                    return path
        if "/scroll_touch/" in scroll_view_path:
            return candidates[0]
        if "/scroll_mouse/" in scroll_view_path:
            return candidates[1]
        return native_path

    def _scrollbar_track_path(self, native_path, host=None):
        scroll_view_path = self._real_scroll_view_path(native_path, host)
        if "/scroll_touch/" in scroll_view_path:
            return scroll_view_path + "/panel/bar_and_track"
        if "/scroll_mouse/" in scroll_view_path:
            return scroll_view_path + "/stack_panel/bar_and_track"
        return ""

    def _has_children(self, control):
        if control is None or not hasattr(control, "GetChildren"):
            return False
        try:
            children = control.GetChildren()
        except Exception:
            children = None
        return bool(children)

    def unmount(self, host, fiber):
        cache = getattr(self, "_scroll_path_cache", None)
        if cache is not None:
            cache.pop(fiber.native_path, None)


class ButtonPrimitive(Primitive):
    """按钮 Primitive。

    参数：
    :param style: Style。控制按钮布局、尺寸、padding、透明度和可见性。
        内容默认在水平和垂直方向居中；显式传入 alignItems 或
        justifyContent 可覆盖对应默认值。
    :param onClick: 点击回调。当前绑定原生 touch up 事件。
    :param buttonBuilder: 函数 ``buttonBuilder(state)``，state 为
        ``ButtonState.default``、``ButtonState.hover`` 或
        ``ButtonState.pressed``。返回单个 Image 时会复用模板状态控件设置背景。
    :param children: 按钮内容，挂载到 Button 自身。
    :param **kwargs: 预留给后续 Button 原生 props。

    利用原生 button 控件对名为 default/hover/pressed 的直接子控件的自动显隐
    来实现三态切换，框架不再手动切背景。模板中这三个子控件预设为铺满的按钮
    贴图（textures/ui/button_border_[state]）。

    buttonBuilder(state) 返回一个 Element：
    - 若是单个 Image -> 复用根状态控件：设其 sprite/color（src）即可
    - 否则 -> 把根状态控件 alpha 设为 0（仅作占位/自动切换载体），并把实际
      组件克隆挂到该根状态控件下渲染
    """
    template_path = native.TEMPLATE_BUTTON
    # default/hover/pressed 各自带 Color.alpha，由 apply_layout 独立同步。
    fill_children_inherit_alpha = False

    _DEFAULT_STYLE = Style(
        alignItems=AlignItems.center,
        justifyContent=JustifyContent.center,
    )

    def __call__(self, **kwargs):
        style = kwargs.get("style")
        kwargs["style"] = self._DEFAULT_STYLE.merge(style)
        return Primitive.__call__(self, **kwargs)

    def props_affect_layout(self, prev_props, next_props, style):
        return False

    # 原生自动切换的三态子控件名
    STATE_NAMES = (ButtonState.default, ButtonState.hover, ButtonState.pressed)

    def apply_props(self, host, fiber, control, prev_props, next_props):
        if control is None:
            return
        button = control.asButton()
        if button is None:
            return
        button_builder = next_props.get("buttonBuilder")
        on_click = next_props.get("onClick")

        if button_builder is not None:
            for state in self.STATE_NAMES:
                state_path = native.join_path(fiber.native_path, state)
                state_ctrl = native.get_control(host, state_path)
                if state_ctrl is None:
                    continue
                img_el = None
                try:
                    img_el = button_builder(state)
                except Exception:
                    img_el = None

                if self._is_single_image(img_el):
                    # 复用根状态控件：设贴图与颜色
                    image = state_ctrl.asImage()
                    color = _to_color_obj(img_el.props.get("color"))
                    src = img_el.props.get("src")
                    effective_src = src
                    if effective_src is None and color is not None:
                        effective_src = native.WHITE_TEXTURE
                    color_tuple = color.to_rgb_tuple() if color is not None else (1.0, 1.0, 1.0)
                    state_alpha = color.a if color is not None else 1.0
                    state_data = ("image", state_alpha, effective_src, color_tuple)
                    state_key = "state_" + state
                    if fiber.primitive_state.get(state_key) == state_data:
                        continue
                    if image is not None:
                        # 仅指定颜色时用白色纹理，确保着色为纯色
                        if src is not None:
                            image.SetSprite(src)
                        elif color is not None:
                            image.SetSprite(native.WHITE_TEXTURE)
                        image.SetSpriteColor(color_tuple)
                    inherited = fiber.primitive_state.get(
                        "_inherited_opacity", 1.0)
                    state_ctrl.SetAlpha(inherited * state_alpha)
                    # 清理上一次可能挂的复杂子控件
                    self._clear_state_children(host, fiber, state)
                    fiber.primitive_state[state_key] = state_data
                    fiber.primitive_state[
                        "_state_layout_alpha_" + state] = inherited * state_alpha
                else:
                    # 根状态控件仅作占位，透明；实际组件挂其下
                    state_key = "state_" + state
                    state_data = ("complex", 0.0)
                    if fiber.primitive_state.get(state_key) != state_data:
                        state_ctrl.SetAlpha(0.0)
                        fiber.primitive_state.pop("_state_layout_alpha_" + state, None)
                    # TODO: 复杂态子组件挂载（v2）。v1 仅支持单 Image 复用，
                    # 以覆盖绝大多数纯色/贴图按钮场景。
                    fiber.primitive_state[state_key] = state_data

        elif prev_props is not None and prev_props.get("buttonBuilder") is not None:
            textures = ("button_borderless_light", "button_borderless_lighthover",
                        "button_borderless_lightpressed")
            for state, texture in zip(self.STATE_NAMES, textures):
                state_ctrl = native.get_control(host, native.join_path(fiber.native_path, state))
                if state_ctrl is not None:
                    image = state_ctrl.asImage()
                    if image is not None:
                        image.SetSprite("textures/ui/" + texture)
                        image.SetSpriteColor((1.0, 1.0, 1.0))
                    alpha = fiber.primitive_state.get("_inherited_opacity", 1.0)
                    state_ctrl.SetAlpha(alpha)
                    fiber.primitive_state["_state_layout_alpha_" + state] = alpha
                fiber.primitive_state.pop("state_" + state, None)

        # 注册点击回调（仅 touch up = click；三态视觉由原生自动切换）
        if prev_props is None:
            button.AddTouchEventParams({"isSwallow": True})
            button.SetButtonTouchUpCallback(host._pyreact_dispatch_touch_up)
        host.pyreact_register_button(fiber.native_path, None, None, on_click)

    def fill_children(self, native_path):
        # default/hover/pressed 都是 size:100%/100%，需随按钮尺寸同步
        return [native.join_path(native_path, s) for s in self.STATE_NAMES]

    def apply_layout(self, host, node):
        for state in self.STATE_NAMES:
            state_path = native.join_path(node.fiber.native_path, state)
            state_ctrl = native.get_control(host, state_path)
            if state_ctrl is None:
                continue
            state_data = node.fiber.primitive_state.get("state_" + state)
            state_alpha = 1.0
            if state_data is not None and len(state_data) > 1 and state_data[1] is not None:
                state_alpha = state_data[1]
            final_alpha = node.inherited_opacity * state_alpha
            alpha_key = "_state_layout_alpha_" + state
            if node.fiber.primitive_state.get(alpha_key) == final_alpha:
                continue
            state_ctrl.SetAlpha(final_alpha)
            node.fiber.primitive_state[alpha_key] = final_alpha

    def unmount(self, host, fiber):
        host.pyreact_unregister_button(fiber.native_path)

    def _is_single_image(self, element):
        """builder 返回的是否为单个 Image 元素。"""
        if not isinstance(element, Element):
            return False
        return isinstance(element.comp_type, ImagePrimitive)

    def _clear_state_children(self, host, fiber, state):
        """移除某状态根控件下的非原生子控件（复杂态残留）。"""
        state_path = native.join_path(fiber.native_path, state)
        state_ctrl = native.get_control(host, state_path)
        if state_ctrl is None:
            return
        # 获取直接子控件并移除（保留原生占位本身）
        children = state_ctrl.GetChildren() if hasattr(state_ctrl, "GetChildren") else None
        if children:
            for child in children:
                host.RemoveChildControl(child)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _to_color_obj(value):
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    if isinstance(value, (int, long)):
        return Color(value)
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return Color(value[0], value[1], value[2])
        if len(value) == 4:
            return Color(value[0], value[1], value[2], value[3])
    return None


# ---------------------------------------------------------------------------
# 用户态 Primitive 单例
# ---------------------------------------------------------------------------

Panel = PanelPrimitive()
Label = LabelPrimitive()
Image = ImagePrimitive()
Item = ItemPrimitive()
PaperDoll = PaperDollPrimitive()
Input = InputPrimitive()
Slider = SliderPrimitive()
ScrollView = ScrollViewPrimitive()
Button = ButtonPrimitive()
