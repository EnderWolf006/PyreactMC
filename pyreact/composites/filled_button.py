# -*- coding: utf-8 -*-
"""按钮类 Composite。"""

from ..component import Component
from ..constants import ButtonState, Colors
from ..primitives import Button, Image
from ..style import Style


def _resolve_button_states(default_value, hover, pressed):
    if default_value is None:
        default_value = Colors.transparent
    if hover is None:
        hover = default_value.lighten(0.2)
    if pressed is None:
        pressed = default_value.darken(0.2)
    return {
        ButtonState.default: default_value,
        ButtonState.hover: hover,
        ButtonState.pressed: pressed,
    }


@Component
def FilledButton(default=Colors.transparent, hover=None, pressed=None,
                 **kwargs):
    """纯色背景按钮 Composite，基于 Button + Image 组合。

    参数：
    :param default: 默认态 Color。默认 Colors.transparent。
    :param hover: 悬停态 Color。未传时使用 ``default.lighten(0.2)``。
    :param pressed: 按下态 Color。未传时使用 ``default.darken(0.2)``。
    :param **kwargs: 原样透传给 Button，例如 key、ref、style、children、onClick。
    """
    color_map = _resolve_button_states(default, hover, pressed)

    # Button 会按原生交互状态重新调用 builder，这里只负责映射背景颜色。
    def builder(state):
        return Image(
            style=Style(width="100%", height="100%"),
            color=color_map.get(state, color_map[ButtonState.default]),
        )

    kwargs["buttonBuilder"] = builder
    return Button(**kwargs)
