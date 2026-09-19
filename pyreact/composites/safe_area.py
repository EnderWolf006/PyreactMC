# -*- coding: utf-8 -*-
"""异形屏安全区容器 Composite。"""

from .. import host
from ..component import Component
from ..hooks import use_effect, use_state
from ..primitives import Panel
from ..style import Style


_ZERO_INSETS = host.SafeAreaInsets(0.0, 0.0, 0.0, 0.0)


@Component
def SafeArea(style=None, children=None):
    """类似 React Native SafeAreaView 的安全区容器。

    参数：
    :param style: 应用到内部 Panel 的 Style。原有 padding 会与当前容器实际覆盖的
        安全区 inset 相加；其他布局和视觉字段保持不变。
    :param children: 单个组件，或组件列表/元组。

    探针尚未完成首次布局时暂以零 inset 渲染；测量完成及窗口变化后只重渲染
    订阅的 SafeArea。容器已位于安全矩形内或嵌套在另一个 SafeArea 中时不会重复添加
    padding。inset 使用 Pyreact/JsonUI 设计坐标，不是设备物理像素。
    """
    if style is not None and not isinstance(style, Style):
        raise TypeError("SafeArea style must be Style or None")

    initial_insets = host.get_safe_area_insets()
    if initial_insets is None:
        initial_insets = _ZERO_INSETS
    insets, set_insets = use_state(initial_insets)

    def subscribe():
        return host._subscribe_safe_area(set_insets)

    use_effect(subscribe, ())
    safe_size = host.get_safe_area_size()
    safe_area = None
    if safe_size is not None:
        safe_area = (
            float(safe_size[0]),
            float(safe_size[1]),
            insets.top,
            insets.right,
            insets.bottom,
            insets.left,
        )
    return Panel(style=style, _safeArea=safe_area, children=children)
