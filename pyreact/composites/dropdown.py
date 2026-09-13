# -*- coding: utf-8 -*-
# pylint: disable=unexpected-keyword-arg,E1123
"""下拉选择 Composite。"""

from functools import partial

from ..component import Component
from ..constants import (
    AlignItems, ButtonState, Color, Colors, FlexDirection, Position,
)
from ..hooks import use_ref, use_state
from ..primitives import Button, Image, Label, Panel
from ..style import Style
from .list_view import ListView
from .modal import Modal


_UNSET = object()
_DROPDOWN_HEIGHT = 30
_DROPDOWN_OPTION_HEIGHT = 17
_DROPDOWN_MENU_PADDING = 4
_DROPDOWN_CHEVRON = "textures/ui/dropdown_chevron"
_DROPDOWN_BACKGROUND = "textures/ui/dropdown_background"
_DROPDOWN_SELECTED_COLOR = Color(0.29, 0.29, 0.29)
_DROPDOWN_HOVER_COLOR = Color(0.12, 0.48, 0.0)
_DROPDOWN_RADIO_OFF = "textures/ui/radio_off"
_DROPDOWN_RADIO_ON = "textures/ui/radio_on"
_DROPDOWN_FALLBACK_WIDTH = 120.0


@Component
def Dropdown(style=None, menuStyle=None, optionStyle=None, labelStyle=None,
             optionLabelStyle=None, options=None, value=_UNSET,
             defaultValue=_UNSET, onChange=None, placeholder="",
             disabled=False, maxVisibleOptions=5, showScrollbar=True):
    """下拉选择 Composite，视觉与原生 server_form dropdown 保持一致。

    参数：
    :param style: 外层 Panel 的 Style，默认 width=100%、height=30。
    :param menuStyle: 展开菜单 Panel 的 Style，可覆盖默认位置和尺寸。
    :param optionStyle: 每个选项 Button 的 Style，默认 height=17。
    :param labelStyle: 收起态已选文本 Label 的 Style。
    :param optionLabelStyle: 菜单选项文本 Label 的 Style。
    :param options: 选项列表。每项可以是标量、``(label, value)``，或含
        ``label`` / ``value`` 的 dict。
    :param value: 受控值。传入后选中态完全由 value 决定。
    :param defaultValue: 非受控初始值；省略时默认选中第一项。
    :param onChange: 可选回调，选中后以 ``onChange(value)`` 调用。
    :param placeholder: 当前值未匹配选项时显示的文本。
    :param disabled: bool，禁用后不可展开或选择。
    :param maxVisibleOptions: 菜单最多同时显示的选项数，默认 5。
    :param showScrollbar: bool，选项超出可见数量时是否显示滚动条。

    展开时创建覆盖全屏的透明模态点击层，点击菜单外部会自动收起。菜单顶部
    与触发按钮顶部对齐，因此选项会直接覆盖触发按钮。
    """
    _validate_dropdown_style(style, "Dropdown style")
    _validate_dropdown_style(menuStyle, "Dropdown menuStyle")
    _validate_dropdown_style(optionStyle, "Dropdown optionStyle")
    _validate_dropdown_style(labelStyle, "Dropdown labelStyle")
    _validate_dropdown_style(optionLabelStyle, "Dropdown optionLabelStyle")
    if onChange is not None and not callable(onChange):
        raise TypeError("Dropdown onChange must be callable or None")
    visible_count = _dropdown_visible_count(maxVisibleOptions)
    normalized_options = _normalize_dropdown_options(options)

    if defaultValue is _UNSET:
        initial_value = (normalized_options[0]["value"]
                         if normalized_options else None)
    else:
        initial_value = defaultValue
    internal_value, set_internal_value = use_state(initial_value)
    open_, set_open = use_state(False)
    toggle_ref = use_ref()
    modal_metrics = use_ref(_default_dropdown_modal_metrics())

    # 是否传入 value 决定受控模式；受控模式下内部值不能抢先改变显示。
    controlled = value is not _UNSET
    selected_value = value if controlled else internal_value
    selected_label = _dropdown_selected_label(
        normalized_options, selected_value, placeholder)

    root_style = Style(
        width="100%",
        height=_DROPDOWN_HEIGHT,
        position=Position.relative,
    ).merge(style)
    toggle_style = Style(width="100%", height="100%")
    toggle_content_style = Style(
        width="100%",
        height="100%",
        flexDirection=FlexDirection.row,
        alignItems=AlignItems.center,
        paddingLeft=8,
        paddingRight=8,
    )
    toggle_label_style = Style(
        flex=1,
        marginRight=4,
    ).merge(labelStyle)

    toggle_handler = None
    if not disabled and normalized_options:
        toggle_handler = partial(
            _toggle_dropdown,
            set_open,
            modal_metrics,
            toggle_ref,
            open_,
        )
    children = [
        Button(
            ref=toggle_ref,
            style=toggle_style,
            onClick=toggle_handler,
            children=Panel(
                style=toggle_content_style,
                children=[
                    Label(
                        style=toggle_label_style,
                        content=selected_label,
                        color=Colors.white,
                    ),
                    Image(
                        style=Style(width=8, height=8),
                        src=_DROPDOWN_CHEVRON,
                    ),
                ],
            ),
        ),
    ]

    if open_ and not disabled and normalized_options:
        item_count = min(len(normalized_options), visible_count)
        menu_height = (item_count * _DROPDOWN_OPTION_HEIGHT +
                       _DROPDOWN_MENU_PADDING)
        metrics = modal_metrics.current

        # Modal 已位于屏幕原点，菜单直接使用触发器的全局坐标。
        menu_style = Style(
            position=Position.absolute,
            top=metrics["triggerY"],
            left=metrics["triggerX"],
            width=metrics["triggerWidth"],
            height=menu_height,
            zIndex=2,
        ).merge(menuStyle)
        list_style = Style(
            position=Position.absolute,
            top=2,
            left=2,
            right=2,
            bottom=2,
            zIndex=2,
        )
        content_style = Style(
            width="100%",
            flexDirection=FlexDirection.column,
            alignItems=AlignItems.stretch,
        )

        def render_option(item, index):
            return _dropdown_option(
                item,
                item["value"] == selected_value,
                controlled,
                set_internal_value,
                set_open,
                onChange,
                optionStyle,
                optionLabelStyle,
            )

        menu = Panel(
            style=menu_style,
            children=[
                Image(
                    style=Style(
                        position=Position.absolute,
                        top=0,
                        left=0,
                        width="100%",
                        height="100%",
                        zIndex=1,
                    ),
                    src=_DROPDOWN_BACKGROUND,
                ),
                ListView(
                    style=list_style,
                    contentContainerStyle=content_style,
                    data=normalized_options,
                    renderItem=render_option,
                    showScrollbar=(showScrollbar and
                                   len(normalized_options) > visible_count),
                ),
            ],
        )
        children.append(Modal(
            style=Style(zIndex=42),
            onClick=partial(_set_dropdown_open, set_open, False),
            children=menu,
            _mountPosition=(metrics["triggerX"], metrics["triggerY"]),
        ))
    return Panel(style=root_style, children=children)


def _validate_dropdown_style(style, name):
    if style is not None and not isinstance(style, Style):
        raise TypeError(name + " must be Style or None")


def _dropdown_visible_count(value):
    if (isinstance(value, bool) or
            not isinstance(value, (int, long))):
        raise TypeError("Dropdown maxVisibleOptions must be an integer")
    if value < 1:
        raise ValueError("Dropdown maxVisibleOptions must be at least 1")
    return int(value)


def _normalize_dropdown_options(options):
    if options is None:
        return []
    if not isinstance(options, (list, tuple)):
        raise TypeError("Dropdown options must be a list or tuple")
    normalized = []
    for index, option in enumerate(options):
        if isinstance(option, dict):
            value = option.get("value", option.get("label"))
            label = option.get("label", value)
            key = option.get("key", index)
        elif isinstance(option, (list, tuple)):
            if len(option) != 2:
                raise ValueError(
                    "Dropdown tuple options must contain label and value")
            label, value = option
            key = index
        else:
            label = option
            value = option
            key = index
        normalized.append({
            "id": "dropdown_option_" + str(key),
            "label": _dropdown_text(label),
            "value": value,
        })
    return normalized


def _dropdown_selected_label(options, value, placeholder):
    for option in options:
        if option["value"] == value:
            return option["label"]
    return _dropdown_text(placeholder)


def _dropdown_text(value):
    if value is None:
        return ""
    if isinstance(value, (str, unicode)):
        return value
    return str(value)


def _set_dropdown_open(set_open, value):
    set_open(bool(value))


def _toggle_dropdown(set_open, modal_metrics, toggle_ref, open_):
    if open_:
        set_open(False)
        return
    # 展开前测量，避免窗口尺寸或父布局变化后复用过期坐标。
    modal_metrics.current = _measure_dropdown_modal(toggle_ref.current)
    set_open(True)


def _default_dropdown_modal_metrics():
    return {
        "triggerX": 0.0,
        "triggerY": 0.0,
        "triggerWidth": _DROPDOWN_FALLBACK_WIDTH,
    }


def _measure_dropdown_modal(control):
    metrics = _default_dropdown_modal_metrics()
    if control is not None:
        # 原生 Control 在首次 commit 前可能暂时不可测量，保留回退值即可。
        try:
            position = control.GetGlobalPosition()
            metrics["triggerX"] = float(position[0])
            metrics["triggerY"] = float(position[1])
        except Exception:
            pass
        try:
            size = control.GetSize()
            if float(size[0]) > 0.0:
                metrics["triggerWidth"] = float(size[0])
        except Exception:
            pass

    return metrics


def _select_dropdown_option(set_internal_value, set_open, controlled,
                            on_change, value):
    if not controlled:
        set_internal_value(value)
    set_open(False)
    if on_change is not None:
        on_change(value)


def _dropdown_option(item, selected, controlled, set_internal_value,
                     set_open, on_change, option_style, option_label_style):
    def builder(state):
        if state in (ButtonState.hover, ButtonState.pressed):
            return Image(color=_DROPDOWN_HOVER_COLOR)
        if selected:
            return Image(color=_DROPDOWN_SELECTED_COLOR)
        return Image(color=Colors.transparent)

    row_style = Style(
        width="100%",
        height=_DROPDOWN_OPTION_HEIGHT,
    ).merge(option_style)
    content_style = Style(
        width="100%",
        height="100%",
        flexDirection=FlexDirection.row,
        alignItems=AlignItems.center,
    )
    text_style = Style(
        flex=1,
        marginLeft=6,
    ).merge(option_label_style)
    handler = partial(
        _select_dropdown_option,
        set_internal_value,
        set_open,
        controlled,
        on_change,
        item["value"],
    )
    return Button(
        style=row_style,
        buttonBuilder=builder,
        onClick=handler,
        children=Panel(
            style=content_style,
            children=[
                Image(
                    style=Style(width=10, height=10),
                    src=(_DROPDOWN_RADIO_ON if selected
                         else _DROPDOWN_RADIO_OFF),
                ),
                Label(
                    style=text_style,
                    content=item["label"],
                    color=Colors.white,
                ),
            ],
        ),
    )
