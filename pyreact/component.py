# -*- coding: utf-8 -*-
"""@Component 装饰器。

每个 Pyreact 自定义组件必须用 ``@Component`` 标记。装饰器统一处理所有组件
通用的 ``key`` / ``ref``：调用被装饰的函数时，并不会执行渲染逻辑，而是返回
一个 Element 描述；真正的渲染由 reconciler 调用 ``_render`` 完成。

用法::

    @Component
    def CounterDemo():
        ...
        return Panel(...)
"""

from .element import Element, normalize_children


def Component(func):
    """把普通函数标记为 Pyreact 组件。"""

    def make_element(**kwargs):
        key = kwargs.pop("key", None)
        ref = kwargs.pop("ref", None)
        # style 与 children 作为普通 props 传给组件渲染函数（与 React 一致）；
        # 组件自身的 Element 不直接承载 host 子节点（其输出才承载）。
        children = kwargs.get("children", None)
        if children is not None:
            kwargs["children"] = normalize_children(children)
        return Element(
            comp_type=make_element,
            props=kwargs,
            style=None,
            children=[],
            key=key,
            ref=ref,
        )

    # 标记与渲染入口
    make_element._is_pyreact_component = True
    make_element._render = func
    make_element.__name__ = func.__name__
    make_element.__doc__ = func.__doc__
    return make_element
