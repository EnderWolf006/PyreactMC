# -*- coding: utf-8 -*-
"""pyreact：类 React Native 的中国版 Minecraft Mod UI 开发框架。

公开 API 通过 ``from pyreact import *`` 导入。
"""
from .component import Component
from .element import Element, create_element
from .hooks import (
    use_state,
    use_ref,
    use_effect,
    use_memo,
    use_callback,
    use_event,
    use_custom_event,
)
from .host import (
    PyreactScreenNode as ScreenNode,
    SafeAreaInsets,
    create_root,
    runtime_init,
    get_safe_area_size,
    get_safe_area_insets,
    notify_screen_size_changed,
)
from .navigator import (
    NavigationEntry,
    NavigationError,
    NavigationErrorCode,
    navigator,
)
from .primitives import (
    Panel,
    Label,
    Image,
    sprite_sheet_frames,
    Item,
    PaperDoll,
    Input,
    Slider,
    Button,
    ScrollView,
)
from .composites import (
    Animated,
    Dropdown,
    FilledButton,
    ListView,
    Modal,
    SafeArea,
    Toggle,
)
from .animation import Animation, Easing
from .style import Style, Translate, Scale
from .constants import (
    Color,
    Colors,
    FontSize,
    FlexDirection,
    AlignItems,
    AlignSelf,
    AlignContent,
    JustifyContent,
    ButtonState,
    TextAlignment,
    ImageAdaptionType,
    PaperDollRenderType,
    FlexWrap,
    Position,
    Display,
)

__all__ = [
    # 组件
    "Component",
    # 元素
    "Element",
    "create_element",
    # hooks
    "use_state",
    "use_ref",
    "use_effect",
    "use_memo",
    "use_callback",
    "use_event",
    "use_custom_event",
    # 宿主
    "ScreenNode",
    "SafeAreaInsets",
    "create_root",
    "runtime_init",
    "get_safe_area_size",
    "get_safe_area_insets",
    "notify_screen_size_changed",
    # 全局原生栈 navigator
    "NavigationEntry",
    "NavigationError",
    "NavigationErrorCode",
    "navigator",
    # Primitive
    "Panel",
    "Label",
    "Image",
    "sprite_sheet_frames",
    "Item",
    "PaperDoll",
    "Input",
    "Slider",
    "Button",
    "ScrollView",
    # Composite
    "Animated",
    "Dropdown",
    "FilledButton",
    "ListView",
    "Modal",
    "SafeArea",
    "Toggle",
    # 样式与枚举
    "Style",
    "Translate",
    "Scale",
    "Animation",
    "Easing",
    "Color",
    "Colors",
    "FontSize",
    "FlexDirection",
    "AlignItems",
    "AlignSelf",
    "AlignContent",
    "JustifyContent",
    "ButtonState",
    "TextAlignment",
    "ImageAdaptionType",
    "PaperDollRenderType",
    "FlexWrap",
    "Position",
    "Display",
]
