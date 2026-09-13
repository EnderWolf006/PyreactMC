# -*- coding: utf-8 -*-
# pylint: disable=unexpected-keyword-arg,E1123
"""全屏模态层 Composite。"""

from .. import native
from ..component import Component
from ..constants import Colors, Position
from ..element import normalize_children
from ..hooks import use_effect, use_ref, use_state
from ..primitives import Button, Image, Panel
from ..style import Style


_MODAL_FALLBACK_SCREEN_SIZE = (320.0, 210.0)


@Component
def Modal(visible=True, style=None, onClick=None, children=None,
          _mountPosition=None):
    """覆盖完整屏幕并吞噬底层点击的模态层。

    参数：
    :param visible: bool，是否渲染模态层，默认 True。
    :param style: 模态根 Panel 的 Style。可设置 opacity、zIndex 等；全屏尺寸和
        屏幕原点定位由 Modal 保证。
    :param onClick: 可选背景点击回调。透明背景 Button 即使没有回调也会吞噬
        点击，防止事件穿透到模态层下方。
    :param children: 显示在透明背景 Button 上方的组件。

    Modal 没有独立 native portal。它会测量当前挂载点的全局位置并反向平移到
    屏幕原点；屏幕尺寸通过 ModSDK ``GetScreenSize`` 获取。
    """
    if style is not None and not isinstance(style, Style):
        raise TypeError("Modal style must be Style or None")
    if onClick is not None and not callable(onClick):
        raise TypeError("Modal onClick must be callable or None")

    anchor_ref = use_ref()
    measured_origin, set_measured_origin = use_state(None)
    mount_origin = _normalize_modal_origin(_mountPosition)

    def measure_origin():
        if not visible or mount_origin is not None:
            return
        control = anchor_ref.current
        if control is None:
            return
        try:
            position = control.GetGlobalPosition()
            next_origin = (float(position[0]), float(position[1]))
        except Exception:
            return
        if measured_origin != next_origin:
            set_measured_origin(next_origin)

    use_effect(measure_origin)

    if not visible:
        return None

    origin = mount_origin if mount_origin is not None else measured_origin
    ready = origin is not None
    if origin is None:
        origin = (0.0, 0.0)
    screen_width, screen_height = _get_modal_screen_size()
    modal_style = Style(zIndex=1000).merge(style).merge(Style(
        position=Position.absolute,
        top=-origin[1],
        left=-origin[0],
        width=screen_width,
        height=screen_height,
        visible=ready,
    ))
    anchor = Panel(
        ref=anchor_ref,
        style=Style(
            position=Position.absolute,
            top=0,
            left=0,
            width=0,
            height=0,
        ),
    )
    modal_children = [
        Button(
            style=Style(
                position=Position.absolute,
                top=0,
                left=0,
                width="100%",
                height="100%",
                zIndex=0,
            ),
            buttonBuilder=_transparent_modal_button,
            onClick=onClick,
        ),
    ]
    modal_children.extend(normalize_children(children))
    return [
        anchor,
        Panel(style=modal_style, children=modal_children),
    ]


def _normalize_modal_origin(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _get_modal_screen_size():
    try:
        size = native.get_screen_size()
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            return _MODAL_FALLBACK_SCREEN_SIZE
        width = float(size[0])
        height = float(size[1])
        if width <= 0.0 or height <= 0.0:
            return _MODAL_FALLBACK_SCREEN_SIZE
        return (width, height)
    except Exception:
        return _MODAL_FALLBACK_SCREEN_SIZE


def _transparent_modal_button(state):
    return Image(color=Colors.transparent)
