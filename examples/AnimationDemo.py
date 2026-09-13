# -*- coding: utf-8 -*-
# pylint: disable=unexpected-keyword-arg,E1123
"""全屏 Animated 场景实验室，设计基准为 320 x 210。"""
import math
from functools import partial

import mod.client.extraClientApi as clientApi

from ..pyreact import *
from ..pyreact.hooks import use_animation_frame


class DemoColors(object):
    backdrop = Color(0x091016FF)
    header = Color(0x101B23FF)
    sidebar = Color(0x0D171EFF)
    surface = Color(0x16232CFF)
    surface_raised = Color(0x1D303BFF)
    stage = Color(0x0B141AFF)
    divider = Color(0x36505CFF)
    text = Color(0xEDF6F7FF)
    muted = Color(0x8BA2AAFF)
    dim = Color(0x526B75FF)
    teal = Color(0x32D2BCFF)
    teal_dark = Color(0x176F68FF)
    gold = Color(0xF2C14EFF)
    coral = Color(0xEB6D68FF)
    blue = Color(0x5BA6DBFF)
    green = Color(0x59D18CFF)


class DemoScene(object):
    shop = 0
    loadout = 1
    alerts = 2
    dialog = 3
    stress = 4


class EasingPreset(object):
    linear = 0
    ease = 1
    back = 2
    bounce = 3


class SpeedPreset(object):
    fast = 0
    normal = 1
    slow = 2


class LoadoutSlot(object):
    scout = 0
    assault = 1
    support = 2


@Component
def ActionButton(label="", selected=False, accent=None, onClick=None,
                 style=None):
    color = DemoColors.surface_raised
    if selected:
        color = accent or DemoColors.teal_dark
    return FilledButton(
        style=style,
        default=color,
        hover=color.lighten(0.12),
        pressed=color.darken(0.18),
        onClick=onClick,
        children=Label(
            style=Style(width="100%"),
            content=label,
            color=DemoColors.text,
            fontSize=FontSize.small,
            textAlign=TextAlignment.center,
        ),
    )


@Component
def NavButton(label="", code="", selected=False, onClick=None):
    color = DemoColors.teal_dark if selected else DemoColors.sidebar
    return FilledButton(
        style=Style(width="100%", height=24, marginBottom=3),
        default=color,
        hover=color.lighten(0.12),
        pressed=color.darken(0.18),
        onClick=onClick,
        children=Panel(
            style=Style(
                width="100%",
                height="100%",
                paddingHorizontal=5,
                flexDirection=FlexDirection.row,
                alignItems=AlignItems.center,
            ),
            children=[
                Label(
                    style=Style(width=14),
                    content=code,
                    color=DemoColors.teal if selected else DemoColors.dim,
                    fontSize=FontSize.small,
                ),
                Label(
                    style=Style(flex=1),
                    content=label,
                    color=DemoColors.text if selected else DemoColors.muted,
                    fontSize=FontSize.small,
                    textAlign=TextAlignment.left,
                ),
            ],
        ),
    )


@Component
def PulseDot(color=DemoColors.teal, size=4):
    """呼吸脉冲圆点：transform Scale 只作用于本叶子 Image，走 visual-fast
    路径逐帧缩放，零布局开销。"""
    tick, set_tick = use_state(0.0)

    def on_frame(now):
        set_tick(now)

    use_animation_frame(on_frame, True)
    pulse = 1.0 + 0.35 * math.sin(tick * 5.0)
    return Image(
        style=Style(width=size, height=size, marginLeft=3,
                    transform=[Scale(pulse)]),
        color=color,
    )


@Component
def StageHeader(title="", eyebrow="", status=""):
    return Panel(
        style=Style(
            width="100%",
            height=20,
            flexDirection=FlexDirection.row,
            alignItems=AlignItems.center,
        ),
        children=[
            Image(style=Style(width=2, height=11, marginRight=4),
                  color=DemoColors.teal),
            Panel(
                style=Style(flex=1),
                children=[
                    Label(content=title, color=DemoColors.text,
                          fontSize=FontSize.normal),
                    Label(content=eyebrow, color=DemoColors.dim,
                          fontSize=FontSize.small),
                ],
            ),
            Label(
                style=Style(width=58),
                content=status,
                color=DemoColors.teal,
                fontSize=FontSize.small,
                textAlign=TextAlignment.right,
            ),
            PulseDot(),
        ],
    )


_SHOP_CATEGORIES = ("ALL", "GEAR", "FOOD", "LOOT")

# 字段：(id, 名称, 分类, 单价, 物品 identifier, 附魔, 描述, 强调色)
_SHOP_GOODS = (
    ("dsword", "DIAMOND SWORD", 1, 260, "minecraft:diamond_sword", True,
     "Sharp blade with a lasting edge", DemoColors.blue),
    ("bow", "POWER BOW", 1, 180, "minecraft:bow", True,
     "Charged shots pierce targets", DemoColors.teal),
    ("pick", "IRON PICKAXE", 1, 120, "minecraft:iron_pickaxe", False,
     "Breaks stone twice as fast", DemoColors.muted),
    ("shield", "TOWER SHIELD", 1, 90, "minecraft:shield", False,
     "Blocks frontal attacks", DemoColors.gold),
    ("gapple", "GOLDEN APPLE", 2, 150, "minecraft:golden_apple", False,
     "Grants a regeneration burst", DemoColors.gold),
    ("beef", "COOKED BEEF", 2, 30, "minecraft:cooked_beef", False,
     "Restores 8 hunger points", DemoColors.coral),
    ("bread", "FRESH BREAD", 2, 20, "minecraft:bread", False,
     "Cheap and filling ration", DemoColors.gold),
    ("emerald", "EMERALD", 3, 60, "minecraft:emerald", False,
     "Villager trading currency", DemoColors.green),
    ("diamond", "DIAMOND", 3, 110, "minecraft:diamond", False,
     "Premium crafting gem", DemoColors.blue),
    ("pearl", "ENDER PEARL", 3, 140, "minecraft:ender_pearl", True,
     "Teleports you on impact", DemoColors.teal),
    ("tnt", "TNT BUNDLE", 3, 80, "minecraft:tnt", False,
     "Handle with extreme care", DemoColors.coral),
    ("blaze", "BLAZE ROD", 3, 95, "minecraft:blaze_rod", False,
     "Brewing stand fuel core", DemoColors.gold),
    ("xbow", "CROSSBOW", 1, 200, "minecraft:crossbow", False,
     "Keeps a bolt pre-loaded", DemoColors.coral),
    ("rod", "FISHING ROD", 1, 70, "minecraft:fishing_rod", False,
     "Reels in a river catch", DemoColors.blue),
    ("cake", "SWEET CAKE", 2, 120, "minecraft:cake", False,
     "Party dessert, seven slices", DemoColors.coral),
    ("pie", "PUMPKIN PIE", 2, 45, "minecraft:pumpkin_pie", False,
     "Autumn harvest treat", DemoColors.gold),
    ("gold", "GOLD INGOT", 3, 90, "minecraft:gold_ingot", False,
     "Universal barter metal", DemoColors.gold),
    ("redstone", "REDSTONE DUST", 3, 40, "minecraft:redstone", False,
     "Powers hidden machinery", DemoColors.coral),
)

_SHOP_WALLET_MAX = 1500

_TOAST_HOLD = 1.6
_TOAST_EXIT = 0.3
_TOAST_ROW_STEP = 17


@Component
def ShopScene(easing=None, duration=0.42):
    cat, set_cat = use_state(0)
    selected, set_selected = use_state(_SHOP_GOODS[0][0])
    shown, set_shown = use_state(_SHOP_GOODS[0][0])
    qty, set_qty = use_state(1)
    coins, set_coins = use_state(_SHOP_WALLET_MAX)
    owned, set_owned = use_state({})
    # toast 状态隔离在 ShopToastHub 里，避免其生命周期反复重渲染整个场景。
    toast_api = use_ref(dict).current
    # 详情出场动画期间 selected 可能再次变化，onComplete 从 ref 取最新目标。
    detail_target = use_ref(dict).current
    detail_target["id"] = selected
    good = _shop_find(selected)
    goods = _shop_filter(cat)
    total = good[3] * qty

    def pick(item_id):
        set_selected(item_id)
        set_qty(1)

    def switch_cat(index):
        set_cat(index)
        filtered = _shop_filter(index)
        if filtered and not any(g[0] == selected for g in filtered):
            set_selected(filtered[0][0])
            set_qty(1)

    def push_toast(message, color):
        push = toast_api.get("push")
        if push is not None:
            push(message, color)

    def buy():
        if total > coins:
            push_toast("INSUFFICIENT COINS", DemoColors.coral)
            return
        set_coins(coins - total)
        counts = dict(owned)
        counts[selected] = counts.get(selected, 0) + qty
        set_owned(counts)
        push_toast("+%s %s" % (qty, good[1]), DemoColors.green)
        set_qty(1)

    def restock():
        set_coins(_SHOP_WALLET_MAX)
        set_owned({})
        set_qty(1)

    return Panel(
        style=Style(width="100%", height="100%"),
        children=[
            StageHeader(
                title="TRADING POST",
                eyebrow="ITEM RENDERER STOREFRONT",
                status="%s COINS" % coins,
            ),
            Panel(
                style=Style(
                    width="100%",
                    flex=1,
                    marginTop=3,
                    flexDirection=FlexDirection.row,
                    gap=4,
                ),
                children=[
                    Panel(
                        style=Style(flex=1, height="100%"),
                        children=[
                            _shop_tabs(cat, switch_cat),
                            Image(
                                style=Style(
                                    width="100%", flex=1,
                                    marginTop=3, padding=3),
                                color=DemoColors.stage,
                                children=ListView(
                                    style=Style(width="100%", height="100%"),
                                    data=list(goods),
                                    numColumns=3,
                                    keyExtractor=lambda item, index:
                                        "cell_%s_%s" % (cat, item[0]),
                                    columnWrapperStyle=Style(
                                        width="100%",
                                        flexDirection=FlexDirection.row,
                                        gap=2,
                                        marginBottom=2,
                                    ),
                                    renderItem=lambda item, index:
                                        _shop_cell(
                                            item, index,
                                            item[0] == selected,
                                            pick, owned, duration, easing),
                                ),
                            ),
                        ],
                    ),
                    Panel(
                        style=Style(width="38%", height="100%"),
                        children=[
                            Animated(
                                visible=shown == selected,
                                style=Style(width="100%", flex=1),
                                enter=Animation(
                                    duration=duration * 0.5,
                                    easing=Easing.cubic_out,
                                    from_=Style(
                                        transform=[Translate(14, 0)],
                                        opacity=0.0,
                                    ),
                                    to=Style(
                                        transform=[Translate(0, 0)],
                                        opacity=1.0,
                                    ),
                                ),
                                exit=Animation(
                                    duration=duration * 0.35,
                                    easing=Easing.ease_in,
                                    from_=Style(
                                        transform=[Translate(0, 0)],
                                        opacity=1.0,
                                    ),
                                    to=Style(
                                        transform=[Translate(-14, 0)],
                                        opacity=0.0,
                                    ),
                                    onComplete=lambda: set_shown(
                                        detail_target["id"]),
                                ),
                                children=_shop_detail(_shop_find(shown)),
                            ),
                            Panel(
                                style=Style(
                                    width="100%",
                                    height=10,
                                    flexDirection=FlexDirection.row,
                                    alignItems=AlignItems.center,
                                ),
                                children=[
                                    Label(
                                        style=Style(flex=1),
                                        content="OWNED x%s" % owned.get(
                                            selected, 0),
                                        color=DemoColors.dim,
                                        fontSize=FontSize.small,
                                    ),
                                    Label(
                                        content="UNIT %s" % good[3],
                                        color=DemoColors.gold,
                                        fontSize=FontSize.small,
                                    ),
                                ],
                            ),
                            _shop_qty_row(qty, set_qty),
                            Panel(
                                style=Style(
                                    width="100%",
                                    height=18,
                                    marginTop=3,
                                    flexDirection=FlexDirection.row,
                                    gap=3,
                                ),
                                children=[
                                    ActionButton(
                                        label="BUY  %s" % total,
                                        selected=True,
                                        onClick=buy,
                                        style=Style(flex=1, height="100%"),
                                    ),
                                    ActionButton(
                                        label="RESET",
                                        onClick=restock,
                                        style=Style(
                                            width="30%", height="100%"),
                                    ),
                                ],
                            ),
                            _shop_wallet(coins, duration, easing),
                        ],
                    ),
                ],
            ),
            ShopToastHub(api=toast_api),
        ],
    )


def _shop_filter(cat):
    if cat == 0:
        return _SHOP_GOODS
    return tuple(g for g in _SHOP_GOODS if g[2] == cat)


def _shop_find(item_id):
    for good in _SHOP_GOODS:
        if good[0] == item_id:
            return good
    return _SHOP_GOODS[0]


def _shop_tabs(cat, switch_cat):
    tabs = []
    for index, label in enumerate(_SHOP_CATEGORIES):
        tabs.append(ActionButton(
            label=label,
            selected=cat == index,
            onClick=lambda index=index: switch_cat(index),
            style=Style(flex=1, height="100%"),
        ))
    return Panel(
        style=Style(
            width="100%",
            height=15,
            flexDirection=FlexDirection.row,
            gap=2,
        ),
        children=tabs,
    )


def _shop_cell(good, index, active, pick, owned, duration, easing):
    item_id, _name, _cat, price, icon, enchant, _desc, _accent = good
    count = owned.get(item_id, 0)
    color = DemoColors.teal_dark if active else DemoColors.surface_raised
    content = [
        # 选中时用 Scale 放大图标：叶子 Item 自身缩放，不占额外布局空间
        Item(style=Style(
                width=16, height=16,
                transform=[Scale(1.25)] if active else None),
             identifier=icon, enchant=enchant),
        Label(content=str(price), color=DemoColors.gold,
              fontSize=FontSize.small),
    ]
    if count:
        content.append(Label(
            style=Style(position=Position.absolute, top=1, right=2),
            content="x%s" % count,
            color=DemoColors.teal,
            fontSize=FontSize.small,
        ))
    return Animated(
        style=Style(width="32%", height=36),
        enter=Animation.fade_in(duration=0.2, delay=0.03 * index),
        duration=duration * 0.5,
        transitionEasing=easing,
        transition=Style(opacity=1.0 if active else 0.72),
        children=FilledButton(
            style=Style(width="100%", height="100%"),
            default=color,
            hover=color.lighten(0.12),
            pressed=color.darken(0.15),
            onClick=partial(pick, item_id),
            children=Panel(
                style=Style(
                    width="100%",
                    height="100%",
                    alignItems=AlignItems.center,
                    justifyContent=JustifyContent.center,
                ),
                children=content,
            ),
        ),
    )


def _shop_detail(good):
    _item_id, name, cat_id, _price, icon, enchant, desc, accent = good
    return Panel(
        style=Style(
            width="100%",
            height="100%",
            alignItems=AlignItems.center,
        ),
        children=[
            Image(
                style=Style(
                    width=34,
                    height=34,
                    marginTop=8,
                    alignItems=AlignItems.center,
                    justifyContent=JustifyContent.center,
                ),
                color=DemoColors.surface,
                children=Item(style=Style(width=26, height=26),
                              identifier=icon, enchant=enchant),
            ),
            Label(style=Style(width="100%", marginTop=3), content=name,
                  color=DemoColors.text, fontSize=FontSize.small,
                  textAlign=TextAlignment.center),
            Label(style=Style(width="100%"),
                  content=_SHOP_CATEGORIES[cat_id],
                  color=accent, fontSize=FontSize.small,
                  textAlign=TextAlignment.center),
            Label(style=Style(width="100%", marginTop=2), content=desc,
                  color=DemoColors.muted, fontSize=FontSize.small,
                  textAlign=TextAlignment.center),
        ],
    )


def _shop_qty_row(qty, set_qty):
    return Panel(
        style=Style(
            width="100%",
            height=16,
            marginTop=2,
            flexDirection=FlexDirection.row,
            gap=2,
        ),
        children=[
            ActionButton(
                label="-",
                onClick=lambda: set_qty(max(1, qty - 1)),
                style=Style(width=16, height="100%"),
            ),
            Image(
                style=Style(
                    flex=1,
                    height="100%",
                    alignItems=AlignItems.center,
                    justifyContent=JustifyContent.center,
                ),
                color=DemoColors.surface,
                children=Label(content="QTY x%s" % qty,
                               color=DemoColors.text,
                               fontSize=FontSize.small),
            ),
            ActionButton(
                label="+",
                onClick=lambda: set_qty(min(9, qty + 1)),
                style=Style(width=16, height="100%"),
            ),
        ],
    )


@Component
def ShopWalletBar(percent=1.0, duration=0.42, easing=None):
    """用 transform Scale 播放进度动画。

    width 属于布局字段，逐帧过渡会导致整树 relayout（30 帧瓶颈来源）；
    Scale 走 visual-fast 路径只 SetSize/SetPosition 本控件，不触发布局。
    """
    if easing is None:
        easing = Easing.ease_in_out
    target = max(0.0, min(1.0, float(percent)))
    shown, set_shown = use_state(target)
    anim = use_ref(dict).current
    if anim.get("target") != target:
        anim["target"] = target
        anim["from"] = shown
        anim["start"] = None

    def on_frame(now):
        if anim["start"] is None:
            anim["start"] = now
        if duration <= 0:
            progress = 1.0
        else:
            progress = min(1.0, (now - anim["start"]) / duration)
        if progress >= 1.0:
            set_shown(anim["target"])
            return
        value = anim["from"] + (anim["target"] - anim["from"]) * easing(
            progress)
        set_shown(max(0.0, min(1.0, value)))

    use_animation_frame(on_frame, shown != anim["target"])
    # 横向 Scale + 左侧原点 = 从左往右的进度填充
    return Image(
        style=Style(width="100%", height="100%",
                    transform=[Scale(shown, 1.0, origin=(0.0, 0.5))]),
        color=DemoColors.gold,
    )


def _shop_wallet(coins, duration, easing):
    return Panel(
        style=Style(
            width="100%",
            height=8,
            marginTop=3,
            flexDirection=FlexDirection.row,
            alignItems=AlignItems.center,
        ),
        children=[
            Label(style=Style(width=36), content="WALLET",
                  color=DemoColors.dim, fontSize=FontSize.small),
            Panel(
                style=Style(flex=1, height=4),
                children=[
                    Image(
                        style=Style(
                            position=Position.absolute,
                            top=0, left=0, right=0, bottom=0,
                        ),
                        color=DemoColors.divider,
                    ),
                    ShopWalletBar(
                        percent=coins / float(_SHOP_WALLET_MAX),
                        duration=duration,
                        easing=easing,
                    ),
                ],
            ),
        ],
    )


@Component
def ShopToastHub(api=None):
    """Toast 状态与逐帧生命周期都隔离在这里，避免重渲染整个商店场景。"""
    toasts, set_toasts = use_state(())
    seq = use_ref(dict).current
    positions = use_ref(dict).current

    def push(message, color):
        seq["n"] = seq.get("n", 0) + 1
        entry = {
            "id": seq["n"],
            "message": message,
            "color": color,
            "born": None,
            "hidden": False,
        }

        def append(items):
            items = tuple(items) + (entry,)
            return items[-4:]

        set_toasts(append)

    if api is not None:
        api["push"] = push

    def on_frame(now):
        changed = False
        kept = []
        for entry in toasts:
            if entry["born"] is None:
                entry = dict(entry, born=now)
                changed = True
            age = now - entry["born"]
            if age >= _TOAST_HOLD + _TOAST_EXIT:
                changed = True
                continue
            if age >= _TOAST_HOLD and not entry["hidden"]:
                entry = dict(entry, hidden=True)
                changed = True
            kept.append(entry)
        if changed:
            set_toasts(tuple(kept))

    use_animation_frame(on_frame, bool(toasts))

    rows = []
    visible_index = 0
    for entry in toasts:
        if not entry["hidden"]:
            stack_y = visible_index * _TOAST_ROW_STEP
            positions[entry["id"]] = stack_y
            visible_index += 1
        else:
            stack_y = positions.get(entry["id"], 0)
        rows.append(Animated(
            key="toast_%s" % entry["id"],
            visible=not entry["hidden"],
            style=Style(
                position=Position.absolute,
                left=0,
                right=0,
                height=15,
            ),
            enter=Animation(
                duration=0.3,
                easing=Easing.cubic_out,
                from_=Style(
                    transform=[Translate(0, stack_y - 14)],
                    opacity=0.0,
                ),
                to=Style(
                    transform=[Translate(0, stack_y)],
                    opacity=1.0,
                ),
            ),
            exit=Animation(
                duration=_TOAST_EXIT,
                easing=Easing.ease_in,
                from_=Style(
                    transform=[Translate(0, stack_y)],
                    opacity=1.0,
                ),
                to=Style(
                    transform=[Translate(0, stack_y - 10)],
                    opacity=0.0,
                ),
            ),
            duration=0.22,
            transitionEasing=Easing.ease_in_out,
            transition=Style(transform=[Translate(0, stack_y)]),
            children=_shop_toast_row(entry["message"], entry["color"]),
        ))
    return Panel(
        style=Style(
            position=Position.absolute,
            top=2,
            left=0,
            right=0,
            zIndex=90,
        ),
        children=rows,
    )


def _shop_toast_row(message, color):
    return Panel(
        style=Style(
            width="100%",
            height="100%",
            flexDirection=FlexDirection.row,
            justifyContent=JustifyContent.center,
        ),
        children=Image(
            style=Style(height="100%", padding=1),
            color=color.darken(0.35),
            children=Image(
                style=Style(
                    height="100%",
                    paddingHorizontal=5,
                    flexDirection=FlexDirection.row,
                    alignItems=AlignItems.center,
                ),
                color=DemoColors.header,
                children=Label(content=message, color=color,
                               fontSize=FontSize.small),
            ),
        ),
    )


@Component
def LoadoutScene(easing=None, duration=0.42):
    selected, set_selected = use_state(LoadoutSlot.assault)
    replay, set_replay = use_state(0)
    slots = (
        (LoadoutSlot.scout, "SCOUT", "MOBILITY", DemoColors.blue),
        (LoadoutSlot.assault, "ASSAULT", "DAMAGE", DemoColors.coral),
        (LoadoutSlot.support, "SUPPORT", "CONTROL", DemoColors.green),
    )
    cards = []
    for index, item in enumerate(slots):
        slot, name, role, color = item
        cards.append(Animated(
            key="loadout_%s_%s" % (replay, slot),
            style=Style(position=Position.relative),
            enter=Animation.slide_in_up(
                distance=26,
                duration=0.32,
                delay=0.07 * index,
                easing=Easing.ease_in_out,
            ),
            duration=duration,
            transitionEasing=easing,
            transition=_loadout_target(slot, selected),
            children=_loadout_card(
                name, role, color, slot == selected,
                partial(set_selected, slot)),
        ))
    return Panel(
        style=Style(width="100%", height="100%"),
        children=[
            StageHeader(
                title="TACTICAL LOADOUT",
                eyebrow="LINKED CARD MORPH",
                status=_loadout_name(selected),
            ),
            Image(
                style=Style(
                    width="100%",
                    flex=1,
                    marginTop=3,
                    padding=6,
                    flexDirection=FlexDirection.row,
                    alignItems=AlignItems.center,
                    justifyContent=JustifyContent.center,
                    gap=4,
                ),
                color=DemoColors.stage,
                children=cards,
            ),
            Panel(
                style=Style(
                    width="100%",
                    height=22,
                    marginTop=4,
                    flexDirection=FlexDirection.row,
                    gap=3,
                ),
                children=[
                    ActionButton(
                        label="SCOUT",
                        selected=selected == LoadoutSlot.scout,
                        accent=DemoColors.blue,
                        onClick=lambda: set_selected(LoadoutSlot.scout),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="ASSAULT",
                        selected=selected == LoadoutSlot.assault,
                        accent=DemoColors.coral,
                        onClick=lambda: set_selected(LoadoutSlot.assault),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="SUPPORT",
                        selected=selected == LoadoutSlot.support,
                        accent=DemoColors.green,
                        onClick=lambda: set_selected(LoadoutSlot.support),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="REDEAL",
                        onClick=lambda: set_replay(replay + 1),
                        style=Style(width="20%", height="100%"),
                    ),
                ],
            ),
        ],
    )


def _loadout_card(name, role, color, selected, on_click):
    return FilledButton(
        style=Style(width="100%", height="100%"),
        default=color.darken(0.45 if selected else 0.62),
        hover=color.darken(0.34),
        pressed=color.darken(0.55),
        onClick=on_click,
        children=Panel(
            style=Style(
                width="100%", height="100%", padding=5),
            children=[
                Image(style=Style(width=3, height=17), color=color),
                Label(style=Style(marginTop=4), content=name,
                      color=DemoColors.text, fontSize=FontSize.normal),
                Label(content=role, color=color, fontSize=FontSize.small),
                Panel(style=Style(flex=1)),
                Label(content="ACTIVE" if selected else "STANDBY",
                      color=DemoColors.text if selected else DemoColors.dim,
                      fontSize=FontSize.small),
            ],
        ),
    )


@Component
def AlertsScene(easing=None, duration=0.42):
    level, set_level = use_state(3)
    replay, set_replay = use_state(0)
    # 隐藏后仍保留上次堆叠 Y，避免 exit 时 stack_index<0 把行闪回顶部。
    last_stack_y = use_ref(dict).current
    alerts = (
        ("NETWORK", "Relay latency normalized", DemoColors.blue),
        ("THERMAL", "Core temperature elevated", DemoColors.gold),
        ("SECURITY", "Unknown signature detected", DemoColors.coral),
        ("POWER", "Auxiliary bus load unstable", DemoColors.teal),
        ("NAVIGATION", "Trajectory drift requires review", DemoColors.green),
        ("SENSOR", "Optical array miscalibration", DemoColors.blue),
        ("COMMS", "Uplink packet loss rising", DemoColors.teal),
        ("HULL", "Microfracture near bay 3", DemoColors.coral),
    )
    rows = []
    first_visible = len(alerts) - level
    for index, item in enumerate(alerts):
        title, message, color = item
        stack_index = index - first_visible
        if stack_index >= 0:
            stack_y = 4 + stack_index * 24
            last_stack_y[index] = stack_y
        else:
            stack_y = last_stack_y.get(index, 4)
        # 堆叠位移用 transform，避免 transition 每帧触发布局；
        # enter/exit 的 Y 与 transition / 上次可见位一致。
        rows.append(Animated(
            key="alert_%s_%s" % (replay, index),
            visible=stack_index >= 0,
            style=Style(
                position=Position.absolute,
                left=4,
                right=3,
                height=22,
            ),
            enter=Animation(
                duration=duration,
                delay=0.05 * max(0, stack_index),
                easing=easing,
                from_=Style(
                    transform=[Translate(36, stack_y)],
                    opacity=0.0,
                ),
                to=Style(
                    transform=[Translate(0, stack_y)],
                    opacity=1.0,
                ),
            ),
            exit=Animation(
                duration=duration * 0.66,
                delay=0.03 * max(0, int(round((stack_y - 4) / 24.0))),
                easing=Easing.ease_in,
                from_=Style(
                    transform=[Translate(0, stack_y)],
                    opacity=1.0,
                ),
                to=Style(
                    transform=[Translate(-34, stack_y)],
                    opacity=0.0,
                ),
            ),
            duration=duration * 0.55,
            transitionEasing=Easing.ease_in_out,
            transition=Style(transform=[Translate(0, stack_y)]),
            children=_alert_row(title, message, color, index),
        ))
    return Panel(
        style=Style(width="100%", height="100%"),
        children=[
            StageHeader(
                title="INCIDENT CENTER",
                eyebrow="STAGGERED PRESENCE",
                status="%s ACTIVE" % level,
            ),
            Image(
                style=Style(
                    width="100%",
                    flex=1,
                    marginTop=3,
                ),
                color=DemoColors.stage,
                children=rows,
            ),
            Panel(
                style=Style(
                    width="100%",
                    height=22,
                    marginTop=4,
                    flexDirection=FlexDirection.row,
                    gap=3,
                ),
                children=[
                    ActionButton(
                        label="ADD ALERT",
                        selected=True,
                        accent=DemoColors.coral,
                        onClick=lambda: set_level(
                            min(len(alerts), level + 1)),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="ACKNOWLEDGE",
                        onClick=lambda: set_level(max(0, level - 1)),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="REPLAY STACK",
                        onClick=lambda: set_replay(replay + 1),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="CLEAR",
                        onClick=lambda: set_level(0),
                        style=Style(width="18%", height="100%"),
                    ),
                ],
            ),
        ],
    )


def _alert_row(title, message, color, index):
    return Image(
        style=Style(
            width="100%",
            height="100%",
            paddingVertical=1,
            paddingLeft=4,
            paddingRight=5,
            flexDirection=FlexDirection.row,
            alignItems=AlignItems.center,
        ),
        color=DemoColors.surface_raised,
        children=[
            Image(style=Style(width=3, height=15, marginRight=5),
                  color=color),
            Panel(
                style=Style(flex=1),
                children=[
                    Label(content=title, color=color,
                          fontSize=FontSize.small),
                    Label(content=message, color=DemoColors.text,
                          fontSize=FontSize.small),
                ],
            ),
            Label(content="0%s" % (index + 1), color=DemoColors.dim,
                  fontSize=FontSize.normal),
        ],
    )


class DialogKind(object):
    claim = 0
    reset = 1


@Component
def DialogScene(easing=None, duration=0.42):
    open_, set_open = use_state(False)
    kind, set_kind = use_state(DialogKind.claim)
    level, set_level = use_state(3)
    xp, set_xp = use_state(40)

    def show(which):
        set_kind(which)
        set_open(True)

    def confirm():
        if kind == DialogKind.claim:
            gained = xp + 35
            if gained >= 100:
                set_level(level + 1)
                set_xp(gained - 100)
            else:
                set_xp(gained)
        else:
            set_level(1)
            set_xp(0)
        set_open(False)

    def cancel():
        set_open(False)

    return Panel(
        style=Style(width="100%", height="100%"),
        children=[
            StageHeader(
                title="PLAYER PROFILE",
                eyebrow="MODAL PRESENCE",
                status="LEVEL %s" % level,
            ),
            Image(
                style=Style(
                    width="100%",
                    flex=1,
                    marginTop=3,
                    alignItems=AlignItems.center,
                    justifyContent=JustifyContent.center,
                ),
                color=DemoColors.stage,
                children=_dialog_stats(level, xp, duration, easing),
            ),
            Panel(
                style=Style(
                    width="100%",
                    height=21,
                    marginTop=4,
                    flexDirection=FlexDirection.row,
                    gap=3,
                ),
                children=[
                    ActionButton(
                        label="CLAIM DAILY REWARD",
                        selected=True,
                        onClick=lambda: show(DialogKind.claim),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="RESET PROGRESS",
                        selected=True,
                        accent=DemoColors.coral.darken(0.45),
                        onClick=lambda: show(DialogKind.reset),
                        style=Style(flex=1, height="100%"),
                    ),
                ],
            ),
            _dialog_overlay(open_, kind, duration, confirm, cancel),
        ],
    )


def _dialog_stats(level, xp, duration, easing):
    return Image(
        style=Style(width=150, height=62, padding=6),
        color=DemoColors.surface,
        children=[
            Label(content="OPERATIVE LV.%s" % level, color=DemoColors.text,
                  fontSize=FontSize.normal),
            Label(content="NEXT LEVEL AT 100 XP", color=DemoColors.dim,
                  fontSize=FontSize.small),
            Panel(style=Style(flex=1)),
            Panel(
                style=Style(width="100%", height=5),
                children=[
                    Image(
                        style=Style(
                            position=Position.absolute,
                            top=0, left=0, right=0, bottom=0,
                        ),
                        color=DemoColors.divider,
                    ),
                    Animated(
                        duration=duration,
                        transitionEasing=easing,
                        transition=Style(width="%d%%" % xp, height="100%"),
                        children=Image(
                            style=Style(width="100%", height="100%"),
                            color=DemoColors.teal,
                        ),
                    ),
                ],
            ),
            Label(style=Style(marginTop=2), content="XP %s / 100" % xp,
                  color=DemoColors.muted, fontSize=FontSize.small),
        ],
    )


def _dialog_overlay(open_, kind, duration, on_confirm, on_cancel):
    return Panel(
        style=Style(
            position=Position.absolute,
            top=0, left=0, right=0, bottom=0,
            zIndex=100,
            alignItems=AlignItems.center,
            justifyContent=JustifyContent.center,
        ),
        children=[
            Animated(
                visible=open_,
                style=Style(
                    position=Position.absolute,
                    top=0, left=0, right=0, bottom=0,
                ),
                enter=Animation.fade_in(duration=duration * 0.45),
                exit=Animation.fade_out(duration=duration * 0.35),
                children=FilledButton(
                    style=Style(width="100%", height="100%"),
                    default=Color(0x040A0ECC),
                    hover=Color(0x040A0ECC),
                    pressed=Color(0x040A0ECC),
                    onClick=on_cancel,
                ),
            ),
            Animated(
                visible=open_,
                style=Style(width=168, height=84),
                enter=Animation(
                    duration=duration * 0.7,
                    easing=Easing.cubic_out,
                    from_=Style(
                        transform=[Translate(0, -22)],
                        opacity=0.0,
                    ),
                    to=Style(
                        transform=[Translate(0, 0)],
                        opacity=1.0,
                    ),
                ),
                exit=Animation(
                    duration=duration * 0.4,
                    easing=Easing.ease_in,
                    from_=Style(
                        transform=[Translate(0, 0)],
                        opacity=1.0,
                    ),
                    to=Style(
                        transform=[Translate(0, -14)],
                        opacity=0.0,
                    ),
                ),
                children=_dialog_card(kind, on_confirm, on_cancel),
            ),
        ],
    )


def _dialog_card(kind, on_confirm, on_cancel):
    claim = kind == DialogKind.claim
    accent = DemoColors.teal if claim else DemoColors.coral
    title = "CLAIM DAILY REWARD" if claim else "RESET PROGRESS"
    message = ("Collect 35 XP from the daily cache?" if claim
               else "Level and XP will be lost. Continue?")
    # 卡片本体用无动作按钮承接点击，避免点击穿透到背后的遮罩关闭弹窗。
    return FilledButton(
        style=Style(width="100%", height="100%"),
        default=DemoColors.surface_raised,
        hover=DemoColors.surface_raised,
        pressed=DemoColors.surface_raised,
        onClick=lambda: None,
        children=Panel(
            style=Style(width="100%", height="100%", padding=6),
            children=[
                Panel(
                    style=Style(
                        width="100%",
                        flexDirection=FlexDirection.row,
                        alignItems=AlignItems.center,
                    ),
                    children=[
                        Image(style=Style(width=3, height=10, marginRight=4),
                              color=accent),
                        Label(content=title, color=DemoColors.text,
                              fontSize=FontSize.normal),
                    ],
                ),
                Label(style=Style(marginTop=3), content=message,
                      color=DemoColors.muted, fontSize=FontSize.small),
                Panel(style=Style(flex=1)),
                Panel(
                    style=Style(
                        width="100%",
                        height=18,
                        flexDirection=FlexDirection.row,
                        gap=3,
                    ),
                    children=[
                        ActionButton(
                            label="CANCEL",
                            selected=True,
                            accent=DemoColors.surface,
                            onClick=on_cancel,
                            style=Style(flex=1, height="100%"),
                        ),
                        ActionButton(
                            label="CONFIRM",
                            selected=True,
                            accent=accent.darken(0.4),
                            onClick=on_confirm,
                            style=Style(flex=1, height="100%"),
                        ),
                    ],
                ),
            ],
        ),
    )


_STRESS_COUNTS = (24, 60, 120)


@Component
def StressScene(easing=None, duration=0.42):
    level, set_level = use_state(1)
    phase, set_phase = use_state(0)
    auto, set_auto = use_state(True)
    clock = use_ref(dict).current
    count = _STRESS_COUNTS[level]
    cycle = duration * 1.5 + 0.25

    def flip():
        clock["last"] = None
        set_phase(1 - phase)

    def on_frame(now):
        last = clock.get("last")
        if last is None:
            clock["last"] = now
            return
        if now - last >= cycle:
            clock["last"] = now
            set_phase(1 - phase)

    use_animation_frame(on_frame, auto)

    return Panel(
        style=Style(width="100%", height="100%"),
        children=[
            StageHeader(
                title="MOTION STRESS RIG",
                eyebrow="CONCURRENT TIMELINES",
                status="%s NODES" % count,
            ),
            Image(
                style=Style(
                    width="100%",
                    flex=1,
                    marginTop=3,
                    padding=4,
                    flexDirection=FlexDirection.row,
                    flexWrap=FlexWrap.wrap,
                    justifyContent=JustifyContent.center,
                    alignContent=AlignContent.center,
                ),
                color=DemoColors.stage,
                children=_stress_tiles(count, level, phase, duration, easing),
            ),
            Panel(
                style=Style(
                    width="100%",
                    height=21,
                    marginTop=4,
                    flexDirection=FlexDirection.row,
                    gap=3,
                ),
                children=[
                    ActionButton(
                        label="24",
                        selected=level == 0,
                        onClick=lambda: set_level(0),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="60",
                        selected=level == 1,
                        onClick=lambda: set_level(1),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="120",
                        selected=level == 2,
                        onClick=lambda: set_level(2),
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="WAVE",
                        onClick=flip,
                        style=Style(flex=1, height="100%"),
                    ),
                    ActionButton(
                        label="AUTO",
                        selected=auto,
                        accent=DemoColors.teal_dark,
                        onClick=lambda: set_auto(not auto),
                        style=Style(flex=1, height="100%"),
                    ),
                ],
            ),
        ],
    )


def _stress_tiles(count, level, phase, duration, easing):
    palette = (DemoColors.teal, DemoColors.blue, DemoColors.gold,
               DemoColors.coral, DemoColors.green)
    direction = 1 if phase else -1
    tiles = []
    for index in range(count):
        dx = (((index * 7) % 11) - 5) * 1.5 * direction
        dy = (((index * 5) % 7) - 3) * 1.3 * direction
        fade = 0.55 + ((index * 3) % 6) * 0.09
        opacity = fade if phase else 1.45 - fade
        tiles.append(Animated(
            key="tile_%s_%s" % (level, index),
            style=Style(width=9, height=9, margin=1),
            enter=Animation.fade_in(
                duration=0.22, delay=min(0.5, 0.005 * index)),
            duration=duration * (0.7 + ((index * 3) % 5) * 0.13),
            transitionEasing=easing,
            transition=Style(transform=[Translate(dx, dy)], opacity=opacity),
            children=Image(
                style=Style(width="100%", height="100%"),
                color=palette[index % 5].darken(0.08 * (index % 4)),
            ),
        ))
    return tiles


@Component
def FpsMeter():
    """右下角实时 FPS 框：每帧读 Game.GetFps()，整数变化时再 setState。"""
    fps, set_fps = use_state(0)
    cache = use_ref(dict).current

    def on_frame(_now):
        game = cache.get("game")
        if game is None:
            game = clientApi.GetEngineCompFactory().CreateGame(
                clientApi.GetLevelId())
            cache["game"] = game
        try:
            value = float(game.GetFps())
        except Exception:
            value = 0.0
        shown = int(round(value))
        if shown != cache.get("shown"):
            cache["shown"] = shown
            set_fps(shown)

    use_animation_frame(on_frame, True)

    color = DemoColors.green
    if fps < 30:
        color = DemoColors.coral
    elif fps < 45:
        color = DemoColors.gold

    return Image(
        style=Style(width="100%", height=34, padding=4),
        color=DemoColors.surface,
        children=[
            Label(content="LIVE FPS", color=DemoColors.dim,
                  fontSize=FontSize.small),
            Label(content="%d" % fps, color=color,
                  fontSize=FontSize.normal),
        ],
    )


@Component
def Inspector(scene=DemoScene.shop, easing_preset=EasingPreset.ease,
              set_easing_preset=None, speed=SpeedPreset.normal,
              set_speed=None):
    return Panel(
        style=Style(width="100%", height="100%", padding=5),
        children=[
            Label(content="MOTION PROFILE", color=DemoColors.text,
                  fontSize=FontSize.normal),
            Label(style=Style(marginTop=1), content=_scene_name(scene),
                  color=DemoColors.teal, fontSize=FontSize.small),
            Label(style=Style(marginTop=8), content="EASING",
                  color=DemoColors.dim, fontSize=FontSize.small),
            _inspector_button("LINEAR", easing_preset == EasingPreset.linear,
                              lambda: set_easing_preset(EasingPreset.linear)),
            _inspector_button("EASE", easing_preset == EasingPreset.ease,
                              lambda: set_easing_preset(EasingPreset.ease)),
            _inspector_button("BACK", easing_preset == EasingPreset.back,
                              lambda: set_easing_preset(EasingPreset.back)),
            _inspector_button("BOUNCE", easing_preset == EasingPreset.bounce,
                              lambda: set_easing_preset(EasingPreset.bounce)),
            Label(style=Style(marginTop=7), content="DURATION",
                  color=DemoColors.dim, fontSize=FontSize.small),
            _inspector_button("FAST  0.18", speed == SpeedPreset.fast,
                              lambda: set_speed(SpeedPreset.fast)),
            _inspector_button("NORMAL 0.42", speed == SpeedPreset.normal,
                              lambda: set_speed(SpeedPreset.normal)),
            _inspector_button("SLOW  0.82", speed == SpeedPreset.slow,
                              lambda: set_speed(SpeedPreset.slow)),
            Panel(style=Style(flex=1)),
            FpsMeter(),
        ],
    )


def _inspector_button(label, selected, callback):
    return ActionButton(
        label=label,
        selected=selected,
        onClick=callback,
        style=Style(width="100%", height=18, marginTop=3),
    )


@Component
def AnimationDemo():
    scene, set_scene = use_state(DemoScene.shop)
    easing_preset, set_easing_preset = use_state(EasingPreset.ease)
    speed, set_speed = use_state(SpeedPreset.normal)
    easing = _resolve_easing(easing_preset)
    duration = _resolve_duration(speed)
    content = _render_scene(scene, easing, duration)

    return Image(
        style=Style(width="100%", height="100%"),
        color=DemoColors.backdrop,
        children=[
            Image(
                style=Style(
                    width="100%",
                    height=23,
                    paddingHorizontal=6,
                    flexDirection=FlexDirection.row,
                    alignItems=AlignItems.center,
                ),
                color=DemoColors.header,
                children=[
                    Label(content="PYREACT MOTION", color=DemoColors.text,
                          fontSize=FontSize.normal),
                    Label(style=Style(marginLeft=5), content="SCENE LAB",
                          color=DemoColors.teal, fontSize=FontSize.small),
                    Panel(style=Style(flex=1)),
                    Image(style=Style(width=4, height=4, marginRight=3),
                          color=DemoColors.green),
                    Label(content="RENDER SYNC", color=DemoColors.muted,
                          fontSize=FontSize.small),
                    ActionButton(
                        label="X",
                        selected=True,
                        accent=DemoColors.coral,
                        onClick=navigator.pop,
                        style=Style(width=18, height=15, marginLeft=6),
                    ),
                ],
            ),
            Panel(
                style=Style(
                    width="100%",
                    flex=1,
                    flexDirection=FlexDirection.row,
                ),
                children=[
                    Image(
                        style=Style(width="18%", height="100%", padding=5),
                        color=DemoColors.sidebar,
                        children=[
                            Label(content="SCENARIOS", color=DemoColors.dim,
                                  fontSize=FontSize.small),
                            Panel(style=Style(height=5)),
                            NavButton(
                                label="SHOP", code="01",
                                selected=scene == DemoScene.shop,
                                onClick=lambda: set_scene(DemoScene.shop)),
                            NavButton(
                                label="LOADOUT", code="02",
                                selected=scene == DemoScene.loadout,
                                onClick=lambda: set_scene(DemoScene.loadout)),
                            NavButton(
                                label="ALERTS", code="03",
                                selected=scene == DemoScene.alerts,
                                onClick=lambda: set_scene(DemoScene.alerts)),
                            NavButton(
                                label="DIALOG", code="04",
                                selected=scene == DemoScene.dialog,
                                onClick=lambda: set_scene(DemoScene.dialog)),
                            NavButton(
                                label="STRESS", code="05",
                                selected=scene == DemoScene.stress,
                                onClick=lambda: set_scene(DemoScene.stress)),
                            Panel(style=Style(flex=1)),
                            Label(content="FPS CLOCKED", color=DemoColors.dim,
                                  fontSize=FontSize.small),
                            Label(content="FRAME EXACT", color=DemoColors.teal,
                                  fontSize=FontSize.small),
                        ],
                    ),
                    Panel(
                        style=Style(
                            flex=1,
                            height="100%",
                            padding=6,
                        ),
                        children=content,
                    ),
                    Image(
                        style=Style(width="22%", height="100%"),
                        color=DemoColors.sidebar,
                        children=[
                            Inspector(
                                scene=scene,
                                easing_preset=easing_preset,
                                set_easing_preset=set_easing_preset,
                                speed=speed,
                                set_speed=set_speed,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _render_scene(scene, easing, duration):
    if scene == DemoScene.loadout:
        return LoadoutScene(easing=easing, duration=duration)
    if scene == DemoScene.alerts:
        return AlertsScene(easing=easing, duration=duration)
    if scene == DemoScene.dialog:
        return DialogScene(easing=easing, duration=duration)
    if scene == DemoScene.stress:
        return StressScene(easing=easing, duration=duration)
    return ShopScene(easing=easing, duration=duration)


def _loadout_target(slot, selected):
    active = slot == selected
    return Style(
        width="42%" if active else "25%",
        height="88%" if active else "66%",
        top=-4 if active else 8,
        padding=5 if active else 2,
        opacity=1.0 if active else 0.48,
    )


def _loadout_name(slot):
    return ("SCOUT", "ASSAULT", "SUPPORT")[slot]


def _resolve_easing(preset):
    if preset == EasingPreset.linear:
        return Easing.linear
    if preset == EasingPreset.back:
        return Easing.back_out
    if preset == EasingPreset.bounce:
        return Easing.bounce_out
    return Easing.ease_in_out


def _resolve_duration(speed):
    return (0.18, 0.42, 0.82)[speed]


def _scene_name(scene):
    return ("SHOP", "LOADOUT", "ALERTS", "DIALOG", "STRESS")[scene]
