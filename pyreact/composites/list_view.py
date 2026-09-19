# -*- coding: utf-8 -*-
# pylint: disable=unexpected-keyword-arg,E1123
"""列表类 Composite。"""

from ..component import Component
from ..constants import AlignItems, FlexDirection
from ..element import Element, normalize_children
from ..primitives import Label, Panel, ScrollView
from ..style import Style


@Component
def ListView(style=None, contentContainerStyle=None, data=None,
             renderItem=None, keyExtractor=None, listHeaderComponent=None,
             listFooterComponent=None, emptyComponent=None, numColumns=1,
             columnWrapperStyle=None, **kwargs):
    """列表 Composite，基于 ScrollView + Panel 组合。

    参数：
    :param style: Style，应用到外层 ScrollView。通常设置 width/height/flex。
    :param contentContainerStyle: Style，应用到滚动内容 Panel。默认 width=100%、
        flexDirection=column、alignItems=stretch。
    :param data: 列表数据。None 会当作空列表。
    :param renderItem: 函数 ``renderItem(item, index)``，返回 Element。
        未提供时使用 ``Label(content=str(item))``。
    :param keyExtractor: 函数 ``keyExtractor(item, index)``，返回每项 key。
        未提供时优先读取 dict item 的 ``id`` 字段，否则使用 index 字符串。
    :param listHeaderComponent: 列表头部 Element。
    :param listFooterComponent: 列表底部 Element。
    :param emptyComponent: data 为空时显示的 Element。
    :param numColumns: 列数。大于 1 时会把 item 包进行 Panel。
    :param columnWrapperStyle: 多列模式下行 Panel 的 Style。默认 row 布局。
    :param **kwargs: 透传给 ScrollView 的 props，例如 showScrollbar。
    """
    children = []
    if contentContainerStyle is None:
        contentContainerStyle = Style(
            width="100%",
            flexDirection=FlexDirection.column,
            alignItems=AlignItems.stretch,
        )
    if listHeaderComponent is not None:
        children.append(listHeaderComponent)
    data_list = data or []
    if data_list:
        row = []
        row_index = 0
        for index, item in enumerate(data_list):
            if renderItem is None:
                element = Label(content=item if isinstance(item, basestring) else str(item))
            else:
                element = renderItem(item, index)

            # renderItem 与普通 children 一样可以返回空值或嵌套列表。
            normalized = normalize_children(element)
            if not normalized:
                continue
            if keyExtractor is not None:
                key = keyExtractor(item, index)
            elif isinstance(item, dict) and item.get("id") is not None:
                key = item.get("id")
            else:
                key = str(index)
            if len(normalized) == 1:
                source = normalized[0]
                # Element belongs to the caller and may be reused elsewhere.
                element = Element(source.comp_type, source.props, source.style,
                                  source.children, key, source.ref)
            else:
                element = _ListItem(key=key, children=normalized)
            if numColumns is not None and int(numColumns) > 1:
                row.append(element)
                if len(row) >= int(numColumns):
                    children.append(_list_row(
                        row, row_index, columnWrapperStyle))
                    row = []
                    row_index += 1
            else:
                children.append(element)
        if row:
            children.append(_list_row(row, row_index, columnWrapperStyle))
    elif emptyComponent is not None:
        children.append(emptyComponent)
    if listFooterComponent is not None:
        children.append(listFooterComponent)
    return ScrollView(
        style=style,
        children=Panel(
            style=contentContainerStyle,
            children=children,
        ),
        **kwargs
    )


def _list_row(row_children, row_index, column_wrapper_style):
    if column_wrapper_style is None:
        column_wrapper_style = Style(
            width="100%",
            flexDirection=FlexDirection.row,
            alignItems=AlignItems.flex_start,
        )
    return Panel(
        key="row_" + str(row_index),
        style=column_wrapper_style,
        children=row_children,
    )


@Component
def _ListItem(children=None):
    """Keep a multi-element item keyed without adding a native layout box."""
    return children
