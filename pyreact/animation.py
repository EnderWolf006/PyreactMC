# -*- coding: utf-8 -*-
"""Animated Composite 使用的样式插值与时间线。

本模块不直接操作原生 Control。每一帧生成新的 ``Style``，再由
Pyreact 现有的 reconcile、layout / visual commit 流程提交。
"""
import time
import math

from .style import (
    Style,
    Translate,
    _INTERPOLATABLE_FIELDS,
    interpolate_transform,
)


class _AnimationAxis(object):
    left = "left"
    top = "top"
    translate_x = "translateX"
    translate_y = "translateY"


class Easing(object):
    """常用 easing 预设，所有函数都接收 0~1 的进度 t。"""

    @staticmethod
    def linear(t):
        return t

    @staticmethod
    def ease_in(t):
        return t * t

    @staticmethod
    def ease_out(t):
        return 1.0 - (1.0 - t) * (1.0 - t)

    @staticmethod
    def ease_in_out(t):
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - ((-2.0 * t + 2.0) ** 2.0) / 2.0

    @staticmethod
    def cubic_in(t):
        return t * t * t

    @staticmethod
    def cubic_out(t):
        return 1.0 - ((1.0 - t) ** 3.0)

    @staticmethod
    def cubic_in_out(t):
        if t < 0.5:
            return 4.0 * t * t * t
        return 1.0 - ((-2.0 * t + 2.0) ** 3.0) / 2.0

    @staticmethod
    def cubic_bezier(x1, y1, x2, y2):
        """通过两个控制点创建三次贝塞尔 easing。

        返回的函数将时间线的 x 轴进度映射为曲线的 y 值。``x1`` 和 ``x2``
        必须在 0~1 内以保证曲线是函数；y 值可超出该范围来实现回弹超调。
        """
        x1 = float(x1)
        y1 = float(y1)
        x2 = float(x2)
        y2 = float(y2)
        if not 0.0 <= x1 <= 1.0 or not 0.0 <= x2 <= 1.0:
            raise ValueError(
                "cubic_bezier x control points must be between 0 and 1")

        ax = 1.0 - 3.0 * x2 + 3.0 * x1
        bx = 3.0 * x2 - 6.0 * x1
        cx = 3.0 * x1
        ay = 1.0 - 3.0 * y2 + 3.0 * y1
        by = 3.0 * y2 - 6.0 * y1
        cy = 3.0 * y1

        def sample_x(curve_t):
            return ((ax * curve_t + bx) * curve_t + cx) * curve_t

        def sample_y(curve_t):
            return ((ay * curve_t + by) * curve_t + cy) * curve_t

        def sample_x_derivative(curve_t):
            return (3.0 * ax * curve_t + 2.0 * bx) * curve_t + cx

        def easing(t):
            t = float(t)
            if t <= 0.0:
                return 0.0
            if t >= 1.0:
                return 1.0

            curve_t = t
            for _unused in range(8):
                error = sample_x(curve_t) - t
                if abs(error) < 0.0000001:
                    return sample_y(curve_t)
                derivative = sample_x_derivative(curve_t)
                if abs(derivative) < 0.0000001:
                    break
                curve_t -= error / derivative

            lower = 0.0
            upper = 1.0
            curve_t = t
            for _unused in range(20):
                error = sample_x(curve_t) - t
                if abs(error) < 0.0000001:
                    break
                if error < 0.0:
                    lower = curve_t
                else:
                    upper = curve_t
                curve_t = (lower + upper) * 0.5
            return sample_y(curve_t)

        return easing

    @staticmethod
    def back_in(t):
        c1 = 1.70158
        c3 = c1 + 1.0
        return c3 * t * t * t - c1 * t * t

    @staticmethod
    def back_out(t):
        c1 = 1.70158
        c3 = c1 + 1.0
        p = t - 1.0
        return 1.0 + c3 * p * p * p + c1 * p * p

    @staticmethod
    def back_in_out(t):
        c1 = 1.70158
        c2 = c1 * 1.525
        if t < 0.5:
            p = 2.0 * t
            return (p * p * ((c2 + 1.0) * p - c2)) / 2.0
        p = 2.0 * t - 2.0
        return (p * p * ((c2 + 1.0) * p + c2) + 2.0) / 2.0

    @staticmethod
    def bounce_out(t):
        n1 = 7.5625
        d1 = 2.75
        if t < 1.0 / d1:
            return n1 * t * t
        if t < 2.0 / d1:
            p = t - 1.5 / d1
            return n1 * p * p + 0.75
        if t < 2.5 / d1:
            p = t - 2.25 / d1
            return n1 * p * p + 0.9375
        p = t - 2.625 / d1
        return n1 * p * p + 0.984375

    @staticmethod
    def bounce_in(t):
        return 1.0 - Easing.bounce_out(1.0 - t)

    @staticmethod
    def bounce_in_out(t):
        if t < 0.5:
            return (1.0 - Easing.bounce_out(1.0 - 2.0 * t)) / 2.0
        return (1.0 + Easing.bounce_out(2.0 * t - 1.0)) / 2.0


class Animation(object):
    """一次 enter/exit 动画配置。

    :param duration: 动画时长，秒。
    :param delay: 开始前延迟，秒。
    :param easing: ``easing(t)``，t 范围 0~1；默认线性。
    :param from_: 起始 Style（仅可插值字段会参与动画）。
    :param to: 结束 Style。
    :param onComplete: 动画自然完成后的回调。
    """

    __slots__ = (
        "duration", "delay", "easing", "from_", "to",
        "onComplete",
    )

    def __init__(self, duration=0.3, delay=0.0, easing=None, from_=None,
                 to=None, onComplete=None):
        self.duration = _non_negative_float(duration, "duration")
        self.delay = _non_negative_float(delay, "delay")
        self.easing = easing if easing is not None else Easing.linear
        if not callable(self.easing):
            raise TypeError("Animation easing must be callable")
        self.from_ = _coerce_style(from_, "from_")
        self.to = _coerce_style(to, "to")
        if onComplete is not None and not callable(onComplete):
            raise TypeError("Animation onComplete must be callable or None")
        self.onComplete = onComplete

    @classmethod
    def fade_in(cls, duration=0.25, delay=0.0, easing=Easing.ease_out,
                onComplete=None):
        """透明度从 0 到 1 的进入预设。"""
        return cls(
            duration, delay, easing,
            Style(opacity=0.0), Style(opacity=1.0),
            onComplete)

    @classmethod
    def fade_out(cls, duration=0.2, delay=0.0, easing=Easing.ease_in,
                 onComplete=None):
        """透明度从 1 到 0 的退出预设。"""
        return cls(
            duration, delay, easing,
            Style(opacity=1.0), Style(opacity=0.0),
            onComplete)

    @classmethod
    def slide_in_left(cls, distance=20.0, duration=0.3, delay=0.0,
                      easing=Easing.ease_out, onComplete=None):
        """从左侧滑入。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_x, -1.0, 0.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_in_right(cls, distance=20.0, duration=0.3, delay=0.0,
                       easing=Easing.ease_out, onComplete=None):
        """从右侧滑入。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_x, 1.0, 0.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_in_up(cls, distance=20.0, duration=0.3, delay=0.0,
                    easing=Easing.ease_out, onComplete=None):
        """从上方滑入。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_y, -1.0, 0.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_in_down(cls, distance=20.0, duration=0.3, delay=0.0,
                      easing=Easing.ease_out, onComplete=None):
        """从下方滑入。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_y, 1.0, 0.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_out_left(cls, distance=20.0, duration=0.25, delay=0.0,
                       easing=Easing.ease_in, onComplete=None):
        """向左侧滑出。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_x, 0.0, -1.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_out_right(cls, distance=20.0, duration=0.25, delay=0.0,
                        easing=Easing.ease_in, onComplete=None):
        """向右侧滑出。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_x, 0.0, 1.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_out_up(cls, distance=20.0, duration=0.25, delay=0.0,
                     easing=Easing.ease_in, onComplete=None):
        """向上方滑出。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_y, 0.0, -1.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def slide_out_down(cls, distance=20.0, duration=0.25, delay=0.0,
                       easing=Easing.ease_in, onComplete=None):
        """向下方滑出。distance 使用设计像素（transform.translate）。"""
        return cls._slide(
            _AnimationAxis.translate_y, 0.0, 1.0, distance, duration, delay,
            easing, onComplete)

    @classmethod
    def _slide(cls, axis, start_factor, end_factor, distance, duration,
               delay, easing, on_complete):
        safe_distance = _non_negative_float(distance, "distance")
        start = safe_distance * start_factor
        end = safe_distance * end_factor
        if axis == _AnimationAxis.translate_x:
            from_style = Style(transform=[Translate(start, 0.0)])
            to_style = Style(transform=[Translate(end, 0.0)])
        elif axis == _AnimationAxis.translate_y:
            from_style = Style(transform=[Translate(0.0, start)])
            to_style = Style(transform=[Translate(0.0, end)])
        elif axis == _AnimationAxis.left:
            from_style = Style(left=start)
            to_style = Style(left=end)
        else:
            from_style = Style(top=start)
            to_style = Style(top=end)
        return cls(
            duration, delay, easing, from_style, to_style, on_complete)


class _AnimatedTimeline(object):
    """Animated 组件 Fiber 生命周期内持有的可变时间线。"""

    __slots__ = (
        "initialized", "visible", "dismissed", "phase",
        "current", "settled", "transition_target",
        "start_style", "target_style", "started_at",
        "duration", "delay", "easing", "on_complete", "active",
    )

    def __init__(self):
        self.initialized = False
        self.visible = True
        self.dismissed = False
        self.phase = None
        self.current = Style()
        self.settled = Style()
        self.transition_target = Style()
        self.start_style = Style()
        self.target_style = Style()
        self.started_at = 0.0
        self.duration = 0.0
        self.delay = 0.0
        self.easing = Easing.linear
        self.on_complete = None
        self.active = False

    def begin(self, start_style, target_style, duration, delay=0.0,
              easing=None, on_complete=None, phase=None):
        self.start_style = _coerce_style(start_style, "start_style").copy()
        self.target_style = _coerce_style(target_style, "target_style").copy()
        self.current = self.start_style.copy()
        self.duration = _non_negative_float(duration, "duration")
        self.delay = _non_negative_float(delay, "delay")
        self.easing = easing if easing is not None else Easing.linear
        self.on_complete = on_complete
        self.phase = phase
        self.started_at = time.time()
        self.active = True

    def tick(self, now=None):
        """推进一帧，返回样式是否发生变化。"""
        if not self.active:
            return False
        if now is None:
            now = time.time()
        elapsed = float(now) - self.started_at
        if elapsed < self.delay:
            return False
        if self.duration <= 0.0:
            progress = 1.0
        else:
            progress = (elapsed - self.delay) / self.duration
            progress = max(0.0, min(1.0, progress))
        eased = float(self.easing(progress))
        next_style = interpolate_style(
            self.start_style, self.target_style, eased, progress >= 1.0)
        changed = not self.current.equals(next_style)
        self.current = next_style
        if progress >= 1.0:
            self.active = False
            callback = self.on_complete
            self.on_complete = None
            self.phase = None
            if callback is not None:
                callback()
            return True
        return changed


def interpolate_style(from_style, to_style, progress, complete=False):
    """在两个 Style 之间插值（仅可插值字段）。"""
    _require_style(from_style, "from_style")
    _require_style(to_style, "to_style")
    # progress 可能是 easing 后的值。back_out / bounce 等会在真实时间结束前
    # 返回大于 1.0 的值；只有调用方明确传入 complete 才能收敛到目标样式。
    if complete:
        return to_style.copy()
    values = {}
    keys = from_style._set_keys | to_style._set_keys
    for key in keys:
        has_from = key in from_style._set_keys
        has_to = key in to_style._set_keys
        if not has_from:
            values[key] = getattr(to_style, key)
            continue
        if not has_to:
            values[key] = getattr(from_style, key)
            continue
        start = getattr(from_style, key)
        end = getattr(to_style, key)
        if key not in _INTERPOLATABLE_FIELDS:
            # 离散字段：进度未完成前保持 start，完成时由 complete 分支返回 to
            values[key] = start
            continue
        values[key] = _interpolate_value(key, start, end, progress)
    return Style(**values)


def merge_styles(first, second):
    """合并两个可选 Style，second 覆盖 first。"""
    result = _coerce_style(first, "first").copy()
    if second is not None:
        result = result.merge(_coerce_style(second, "second"))
    return result


def without_style_fields(style, fields):
    """复制 Style，但移除 fields 中的显式字段。"""
    source = _coerce_style(style, "style")
    return source.without_fields(fields)


def styles_equal(first, second):
    return _coerce_style(first, "first").equals(
        _coerce_style(second, "second"))


def _interpolate_value(key, start, end, progress):
    if key == "transform":
        return interpolate_transform(start, end, progress)
    if (isinstance(start, (int, long, float)) and not isinstance(start, bool)
            and isinstance(end, (int, long, float))
            and not isinstance(end, bool)):
        return float(start) + (float(end) - float(start)) * progress
    start_dimension = _parse_dimension(start)
    end_dimension = _parse_dimension(end)
    if (start_dimension is not None and end_dimension is not None and
            start_dimension[1] == end_dimension[1]):
        value = (start_dimension[0] +
                 (end_dimension[0] - start_dimension[0]) * progress)
        if start_dimension[1] == "%":
            return "%.6f%%" % value
        if start_dimension[1] == "px":
            return "%.6fpx" % value
        return value
    return start


def _parse_dimension(value):
    if not isinstance(value, basestring):
        return None
    text = value.strip()
    unit = ""
    number = text
    if text.endswith("%"):
        unit = "%"
        number = text[:-1]
    elif text.endswith("px"):
        unit = "px"
        number = text[:-2]
    try:
        return (float(number), unit)
    except (TypeError, ValueError):
        return None


def _coerce_style(value, name):
    if value is None:
        return Style()
    _require_style(value, name)
    return value


def _require_style(value, name):
    if not isinstance(value, Style):
        raise TypeError("%s must be Style" % name)


def _non_negative_float(value, name):
    if isinstance(value, bool):
        raise TypeError("%s must be a number" % name)
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise TypeError("%s must be a number" % name)
    if math.isnan(result) or math.isinf(result) or result < 0.0:
        raise ValueError("%s must be finite and >= 0" % name)
    return result
