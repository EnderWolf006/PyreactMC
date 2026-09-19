# -*- coding: utf-8 -*-
"""动画容器 Composite。"""

from ..animation import (
    Animation, Easing, _AnimatedTimeline, merge_styles, styles_equal,
    without_style_fields,
    _non_negative_float,
)
from ..component import Component
from ..constants import Display
from ..hooks import use_animation_frame, use_ref, use_state
from ..primitives import Panel
from ..style import Style


@Component
def Animated(style=None, children=None, enter=None, exit=None, duration=0.3,
             transition=None, transitionEasing=Easing.linear, visible=True,
             onTransitionComplete=None):
    """为 children 提供进入、退出与 state 驱动的过渡动画。

    参数：
    :param style: 外层 Panel 的静态 Style。
    :param children: 单个组件或组件列表/元组。
    :param enter: 可选 Animation，首次显示及重新显示时播放。
    :param exit: 可选 Animation；visible 从 True 变 False 时播放，完成后卸载
        children。
    :param duration: transition 的时长，秒。默认 0.3。
    :param transition: 可选 Style。其值随直接或间接 state 变化时，
        从当前帧平滑过渡到新值（仅可插值字段）。
    :param transitionEasing: transition 使用的 easing 函数。默认 Easing.linear。
    :param onTransitionComplete: 可选函数。state 驱动的 transition 自然结束时调用。
    :param visible: presence 开关。False 会播放 exit 后卸载 children；重新变为
        True 会挂载 children 并播放 enter。

    Animated 是基于 Panel 的 Composite，不直接操作原生 Control。退出动画必须
    通过 visible=False 触发；若父组件直接删除 Animated，其 Fiber 已卸载，无法再
    播放 exit。
    """
    if style is not None and not isinstance(style, Style):
        raise TypeError("Animated style must be Style or None")
    if enter is not None and not isinstance(enter, Animation):
        raise TypeError("Animated enter must be Animation or None")
    if exit is not None and not isinstance(exit, Animation):
        raise TypeError("Animated exit must be Animation or None")
    if transition is not None and not isinstance(transition, Style):
        raise TypeError("Animated transition must be Style or None")
    if not callable(transitionEasing):
        raise TypeError("Animated transitionEasing must be callable")
    if onTransitionComplete is not None and not callable(onTransitionComplete):
        raise TypeError("Animated onTransitionComplete must be callable or None")
    transition_duration = _animated_duration(duration)

    # 时间线跨 render 保存可变帧状态；state 只用来通知 Fiber 提交最新样式。
    timeline = use_ref(_AnimatedTimeline).current
    _frame_version, set_frame_version = use_state(0)

    def invalidate():
        set_frame_version(lambda value: value + 1)

    _update_animated_timeline(
        timeline, bool(visible), enter, exit, transition_duration, transition,
        transitionEasing, onTransitionComplete)

    def on_frame(now):
        if timeline.tick(now):
            invalidate()

    use_animation_frame(on_frame, timeline.active)

    animated_style = timeline.current
    final_style = animated_style if style is None else style.merge(animated_style)
    if timeline.dismissed:
        # 保留 Animated 自身 Fiber，使 visible=True 时仍可重新播放 enter。
        final_style = final_style.merge(Style(display=Display.none))
        rendered_children = None
    else:
        rendered_children = children
    return Panel(style=final_style, children=rendered_children)


def _update_animated_timeline(timeline, visible, enter, exit_animation,
                              duration, transition, transition_easing,
                              on_transition_complete=None):
    target = transition if transition is not None else Style()
    if not timeline.initialized:
        timeline.initialized = True
        timeline.visible = visible
        timeline.transition_target = target.copy()
        if not visible:
            timeline.dismissed = True
            timeline.current = target.copy()
            timeline.settled = target.copy()
            return
        timeline.dismissed = False
        _start_enter(timeline, enter, target)
        return

    if visible != timeline.visible:
        timeline.visible = visible
        timeline.transition_target = target.copy()
        if visible:
            timeline.dismissed = False
            _start_enter(timeline, enter, target)
        else:
            _start_exit(timeline, exit_animation)
        return

    if not visible:
        return

    if styles_equal(timeline.transition_target, target):
        return

    # 上一轮 transition 字段由新目标替换，其他已稳定字段必须继续保留。
    previous_transition_fields = timeline.transition_target._set_keys
    stable_style = without_style_fields(
        timeline.settled, previous_transition_fields)
    next_settled = merge_styles(stable_style, target)
    timeline.transition_target = target.copy()
    timeline.settled = next_settled.copy()
    timeline.begin(
        timeline.current, next_settled, duration,
        easing=transition_easing, on_complete=on_transition_complete,
        phase="transition")


def _start_enter(timeline, animation, transition):
    timeline.transition_target = transition.copy()
    if animation is None:
        timeline.active = False
        timeline.current = transition.copy()
        timeline.settled = transition.copy()
        timeline.phase = None
        return
    start = merge_styles(transition, animation.from_)
    # transition 是 state 的最终目标；与 enter.to 重叠时由 transition 覆盖。
    target = merge_styles(animation.to, transition)
    timeline.settled = target.copy()
    timeline.begin(
        start, target, animation.duration, animation.delay, animation.easing,
        animation.onComplete, "enter")


def _start_exit(timeline, animation):
    if animation is None:
        timeline.active = False
        timeline.dismissed = True
        timeline.phase = None
        return
    # 退出必须从当前帧视觉态起步：from_ 只补全 current 未设置的字段，
    # 不能用 from_ 覆盖 current（否则堆叠 transform/opacity 会闪到错误起点）。
    start = merge_styles(animation.from_, timeline.current)
    target = merge_styles(timeline.current, animation.to)

    def complete_exit():
        timeline.dismissed = True
        if animation.onComplete is not None:
            animation.onComplete()

    timeline.begin(
        start, target, animation.duration, animation.delay, animation.easing,
        complete_exit, "exit")


def _animated_duration(value):
    return _non_negative_float(value, "Animated duration")
