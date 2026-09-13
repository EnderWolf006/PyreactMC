# -*- coding: utf-8 -*-
"""用 Button 模拟的原版风格开关 Composite。"""

from functools import partial

from ..component import Component
from ..constants import ButtonState
from ..hooks import use_state
from ..primitives import Button, Image
from ..style import Style


_UNSET = object()
_TOGGLE_OFF = "textures/ui/toggle_off"
_TOGGLE_OFF_HOVER = "textures/ui/toggle_off_hover"
_TOGGLE_ON = "textures/ui/toggle_on"
_TOGGLE_ON_HOVER = "textures/ui/toggle_on_hover"
_TOGGLE_DISABLED_OPACITY = 0.5


@Component
def Toggle(style=None, value=_UNSET, defaultValue=False, onChange=None,
           disabled=False):
    """原版风格开关 Composite，内部使用 Button 模拟交互。

    参数：
    :param style: Button 的 Style，默认 width=30、height=16。
    :param value: bool，受控值。传入后显示状态完全由 value 决定。
    :param defaultValue: bool，非受控初始值，默认 False。
    :param onChange: 可选回调，点击后以 ``onChange(next_value)`` 调用。
    :param disabled: bool，禁用后不响应点击，并使用原版 0.5 透明度。

    默认、悬停和禁用视觉对应 ``ui_template_toggles.json`` 中
    ``switch_toggle`` 使用的四张原版贴图；不创建原生 Toggle Control。
    """
    if style is not None and not isinstance(style, Style):
        raise TypeError("Toggle style must be Style or None")
    if onChange is not None and not callable(onChange):
        raise TypeError("Toggle onChange must be callable or None")

    internal_value, set_internal_value = use_state(bool(defaultValue))
    controlled = value is not _UNSET
    checked = bool(value) if controlled else internal_value

    toggle_style = Style(width=30, height=16).merge(style)
    if disabled:
        own_opacity = toggle_style.get("opacity", 1.0)
        toggle_style = toggle_style.merge(Style(
            opacity=own_opacity * _TOGGLE_DISABLED_OPACITY,
        ))

    def builder(state):
        hovered = (not disabled and
                   state in (ButtonState.hover, ButtonState.pressed))
        if checked:
            src = _TOGGLE_ON_HOVER if hovered else _TOGGLE_ON
        else:
            src = _TOGGLE_OFF_HOVER if hovered else _TOGGLE_OFF
        return Image(
            style=Style(width="100%", height="100%"),
            src=src,
        )

    handler = None
    if not disabled:
        handler = partial(
            _change_toggle,
            set_internal_value,
            controlled,
            checked,
            onChange,
        )
    return Button(
        style=toggle_style,
        buttonBuilder=builder,
        onClick=handler,
    )


def _change_toggle(set_internal_value, controlled, checked, on_change):
    next_value = not checked
    if not controlled:
        set_internal_value(next_value)
    if on_change is not None:
        on_change(next_value)
