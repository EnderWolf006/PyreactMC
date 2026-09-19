# -*- coding: utf-8 -*-
"""Element：虚拟 DOM 节点。

一个 Element 是对“渲染成什么”的不可变描述：
- ``comp_type`` 为 ``@Component`` 装饰的函数时，reconciler 会调用其 ``_render``
- ``comp_type`` 为 ``Primitive`` 实例时，reconciler 会创建/更新原生控件
"""


def is_component(value):
    """判断 ``value`` 是否为 ``@Component`` 装饰后的组件。"""
    return callable(value) and getattr(value, "_is_pyreact_component", False)


class Element(object):
    """虚拟 DOM 节点。

    :param comp_type: 组件函数或 Primitive 实例
    :param props: 原生/框架属性（color、content、onClick、buttonBuilder 等），不含 key/ref/children/style
    :param style: Style 实例或 None
    :param children: 已归一化的 Element 列表
    :param key: 复用键
    :param ref: Ref 对象或 None
    """

    __slots__ = ("comp_type", "props", "style", "children", "key", "ref")

    def __init__(self, comp_type, props=None, style=None, children=None,
                 key=None, ref=None):
        self.comp_type = comp_type
        self.props = props if props is not None else {}
        self.style = style
        self.children = children if children is not None else []
        self.key = key
        self.ref = ref

    @property
    def is_primitive(self):
        from .primitives import Primitive
        return isinstance(self.comp_type, Primitive)

    @property
    def is_component(self):
        return is_component(self.comp_type)

    def __repr__(self):
        name = getattr(self.comp_type, "__name__", repr(self.comp_type))
        return "Element(%s, key=%r)" % (name, self.key)


def normalize_children(children):
    """把任意 children 形态归一为 Element 列表。

    支持：None、单个 Element、list/tuple（递归展平）、str/int/float（包成 Label）。
    过滤掉 None。
    """
    if children is None:
        return []
    if isinstance(children, Element):
        return [children]
    if isinstance(children, (list, tuple)):
        # Primitive/Component render 中最常见的是已经归一化的 Element list。
        # Element 是不可变描述，直接复用可避免每次渲染都复制整份 children。
        if isinstance(children, list):
            normalized = True
            for item in children:
                if not isinstance(item, Element):
                    normalized = False
                    break
            if normalized:
                return children
        result = []
        for item in children:
            if item is None:
                continue
            if isinstance(item, (list, tuple)):
                result.extend(normalize_children(item))
            elif isinstance(item, Element):
                result.append(item)
            else:
                result.append(_wrap_text(item))
        return result
    # 标量
    return [_wrap_text(children)]


def _wrap_text(value):
    """把字符串/数字包成 Label 元素（RN 风格的文本子节点）。"""
    from .primitives import Label
    return Label(content=value if isinstance(value, basestring) else str(value))


def create_element(comp_type, props=None, style=None, children=None,
                   key=None, ref=None):
    """显式构造 Element 的工厂函数。"""
    return Element(
        comp_type,
        props=props,
        style=style,
        children=(normalize_children(children)
                  if children is not None else None),
        key=key,
        ref=ref,
    )


def resolve_element(value):
    """把「Element 或未调用的 ``@Component``」归一为 ``Element``。

    - 已经是 ``Element`` 时原样返回，调用方拿到的始终是 Element；
    - ``@Component`` 装饰的组件会以空 props 调用一次，取它返回的 ``Element``；
    - 其他值返回 ``None``，由调用方决定报错方式。

    组件返回的不是 ``Element`` 时抛出 ``TypeError``。
    """
    if isinstance(value, Element):
        return value
    if is_component(value):
        element = value()
        if not isinstance(element, Element):
            raise TypeError(
                "component %s must return a Pyreact Element, got %r"
                % (getattr(value, "__name__", "<component>"), element)
            )
        return element
    return None
