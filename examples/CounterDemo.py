# -*- coding: utf-8 -*-
"""计数器示例：演示 use_state + 事件回调 + 样式与布局。"""
from ..pyreact import *


@Component
def CounterDemo():
    count, set_count = use_state(0)

    def increment():
        set_count(count + 1)

    return SafeArea(
        style=Style(
            width="100%",
            height="100%",
            alignItems=AlignItems.center,
            justifyContent=JustifyContent.center,
        ),
        children=[
            Label(
                style=Style(marginBottom=8),
                fontSize=FontSize.large,
                shadow=True,
                content="这是一个计数器示例"
            ),
            Button(
                style=Style(padding=8),
                onClick=increment,
                children=Label(shadow=True, content="Count: " + str(count))
            ),
        ]
    )
