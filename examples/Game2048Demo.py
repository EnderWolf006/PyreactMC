# -*- coding: utf-8 -*-
# pylint: disable=unexpected-keyword-arg,E1123
"""2048 示例：函数式系统事件、稳定 key 与 Animated 位移动画。"""
from ..pyreact import *


class Direction(object):
    left = "left"
    right = "right"
    up = "up"
    down = "down"


class EngineEvent(object):
    key_press = "OnKeyPressInGame"
    gamepad_stick = "OnGamepadStickClientEvent"


class KeyBoardType(object):
    left = 37
    up = 38
    right = 39
    down = 40
    a = 65
    d = 68
    s = 83
    w = 87


class KeyEventField(object):
    key = "key"
    is_down = "isDown"


class StickEventField(object):
    x = "x"
    y = "y"


class GameText(object):
    title = "2048"
    restart = "RESTART"
    hint = "Arrow keys / WASD / Gamepad stick"
    game_over = "No moves left"


GRID_SIZE = 4
BOARD_SIZE = 180
BOARD_PADDING = 5
TILE_SIZE = 38
TILE_GAP = 5
STICK_THRESHOLD = 0.65

_BOARD_COLOR = Color(0x3B4252FF)
_CELL_COLOR = Color(0x4C566AFF)
_TITLE_COLOR = Color(0xECEFF4FF)
_SCORE_COLOR = Color(0xD8DEE9FF)
_TILE_COLORS = {
    2: Color(0xEEECE6FF),
    4: Color(0xE9D9BFFF),
    8: Color(0xE7A769FF),
    16: Color(0xD97B5FFF),
    32: Color(0xC85E5EFF),
    64: Color(0xB84D62FF),
    128: Color(0xD8B45BFF),
    256: Color(0xC89C45FF),
    512: Color(0xB98738FF),
    1024: Color(0xA46F34FF),
    2048: Color(0x8D5932FF),
}


def _tile_color(value):
    return _TILE_COLORS.get(value, Color(0x6C7086FF))


def _tile_text_color(value):
    if value <= 4:
        return Color(0x3B4252FF)
    return Colors.white


def _tile_position(row, col):
    return (
        BOARD_PADDING + col * (TILE_SIZE + TILE_GAP),
        BOARD_PADDING + row * (TILE_SIZE + TILE_GAP),
    )


def _new_tile(tile_id, value, row, col, merge_id=None, ghost=False,
              spawned=False, spawn_key=None):
    tile = {
        "id": tile_id,
        "value": value,
        "row": row,
        "col": col,
    }
    if merge_id is not None:
        tile["merge_id"] = merge_id
    if ghost:
        tile["ghost"] = True
    if spawned:
        tile["spawned"] = True
        tile["spawn_key"] = str(tile_id) if spawn_key is None else spawn_key
    return tile


def _new_game(round_id=0):
    return {
        "tiles": [
            _new_tile(1, 2, 0, 0, spawned=True,
                      spawn_key="round_%d_1" % round_id),
            _new_tile(2, 2, 2, 3, spawned=True,
                      spawn_key="round_%d_2" % round_id),
        ],
        "next_id": 3,
        "next_merge_id": 1,
        "score": 0,
        "over": False,
        "ghosts": [],
        "merging": False,
    }


def _empty_cells(tiles):
    occupied = set((tile["row"], tile["col"]) for tile in tiles)
    result = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            if (row, col) not in occupied:
                result.append((row, col))
    return result


def _spawn_tile(tiles, next_id, score):
    empty = _empty_cells(tiles)
    if not empty:
        return tiles, next_id
    index = (next_id * 7 + score) % len(empty)
    value = 4 if next_id % 5 == 0 else 2
    row, col = empty[index]
    result = list(tiles)
    result.append(_new_tile(next_id, value, row, col, spawned=True))
    return result, next_id + 1


def _line_tiles(tiles, direction, line):
    if direction == Direction.left or direction == Direction.right:
        result = [tile for tile in tiles if tile["row"] == line]
        result.sort(key=lambda tile: tile["col"],
                    reverse=direction == Direction.right)
    else:
        result = [tile for tile in tiles if tile["col"] == line]
        result.sort(key=lambda tile: tile["row"],
                    reverse=direction == Direction.down)
    return result


def _target_position(direction, line, index):
    if direction == Direction.left:
        return line, index
    if direction == Direction.right:
        return line, GRID_SIZE - 1 - index
    if direction == Direction.up:
        return index, line
    return GRID_SIZE - 1 - index, line


def _move_board(game, direction):
    """执行一步 2048 移动。无可移动方块时返回原对象。"""
    source_tiles = game["tiles"]
    tiles = []
    ghosts = []
    gained = 0
    moved = False
    next_merge_id = game.get("next_merge_id", 1)
    for line in range(GRID_SIZE):
        line_tiles = _line_tiles(source_tiles, direction, line)
        index = 0
        target_index = 0
        while index < len(line_tiles):
            first = line_tiles[index]
            second = None
            if index + 1 < len(line_tiles):
                candidate = line_tiles[index + 1]
                if candidate["value"] == first["value"]:
                    second = candidate
            row, col = _target_position(direction, line, target_index)
            value = first["value"]
            if second is not None:
                value *= 2
                gained += value
                index += 1
                moved = True
                tiles.append(_new_tile(
                    first["id"], value, row, col, next_merge_id))
                ghosts.append(_new_tile(
                    second["id"], second["value"], row, col,
                    ghost=True))
                next_merge_id += 1
                index += 1
                target_index += 1
                continue
            if first["row"] != row or first["col"] != col:
                moved = True
            tiles.append(_new_tile(first["id"], value, row, col))
            index += 1
            target_index += 1

    if not moved:
        return game
    score = game["score"] + gained
    tiles, next_id = _spawn_tile(tiles, game["next_id"], score)
    return {
        "tiles": tiles,
        "next_id": next_id,
        "next_merge_id": next_merge_id,
        "score": score,
        "over": not _has_moves(tiles),
        "ghosts": ghosts,
        "merging": bool(ghosts),
    }


def _clear_merge_ghosts(game):
    if not game.get("ghosts") and not game.get("merging"):
        return game
    next_game = dict(game)
    next_game["ghosts"] = []
    next_game["merging"] = False
    return next_game


def _has_moves(tiles):
    if len(tiles) < GRID_SIZE * GRID_SIZE:
        return True
    by_position = {}
    for tile in tiles:
        by_position[(tile["row"], tile["col"])] = tile["value"]
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            value = by_position.get((row, col))
            if value == by_position.get((row + 1, col)):
                return True
            if value == by_position.get((row, col + 1)):
                return True
    return False


def _keyboard_direction(args):
    if not isinstance(args, dict) or args.get(KeyEventField.is_down) != "1":
        return None
    key = args.get(KeyEventField.key)
    try:
        key = int(key)
    except (TypeError, ValueError):
        return None
    if key == KeyBoardType.left or key == KeyBoardType.a:
        return Direction.left
    if key == KeyBoardType.right or key == KeyBoardType.d:
        return Direction.right
    if key == KeyBoardType.up or key == KeyBoardType.w:
        return Direction.up
    if key == KeyBoardType.down or key == KeyBoardType.s:
        return Direction.down
    return None


def _stick_direction(args):
    if not isinstance(args, dict):
        return None
    try:
        x = float(args.get(StickEventField.x, 0.0))
        y = float(args.get(StickEventField.y, 0.0))
    except (TypeError, ValueError):
        return None
    if abs(x) < STICK_THRESHOLD and abs(y) < STICK_THRESHOLD:
        return None
    if abs(x) >= abs(y):
        return Direction.right if x > 0.0 else Direction.left
    return Direction.up if y > 0.0 else Direction.down


def _cell(row, col):
    left, top = _tile_position(row, col)
    return Image(
        key="cell_%d_%d" % (row, col),
        style=Style(
            position=Position.absolute,
            left=left,
            top=top,
            width=TILE_SIZE,
            height=TILE_SIZE,
        ),
        color=_CELL_COLOR,
    )


def _tile(tile, on_motion_complete):
    left, top = _tile_position(tile["row"], tile["col"])
    value = tile["value"]
    merge_id = tile.get("merge_id")
    feedback_enter = None
    feedback_key = "feedback_%s" % str(merge_id or 0)
    if merge_id is not None:
        feedback_enter = Animation(
            duration=0.15,
            delay=0.08,
            easing=Easing.back_out,
            from_=Style(transform=[Scale(0.78)]),
            to=Style(transform=[Scale(1.0)]),
        )
    elif tile.get("spawned"):
        # 位移动画由外层 Animated 负责；新方块独立从透明的 0x0 弹入。
        feedback_key = "spawn_%s" % tile["spawn_key"]
        feedback_enter = Animation(
            duration=0.28,
            easing=Easing.back_out,
            from_=Style(opacity=0.0, transform=[Scale(0.0)]),
            to=Style(opacity=1.0, transform=[Scale(1.0)]),
        )
    return Animated(
        key="tile_%d" % tile["id"],
        style=Style(
            position=Position.absolute,
            left=0,
            top=0,
            width=TILE_SIZE,
            height=TILE_SIZE,
            zIndex=2 if tile.get("ghost") else 3,
        ),
        transition=Style(transform=[Translate(left, top)]),
        duration=0.13,
        transitionEasing=Easing.ease_out,
        onTransitionComplete=(on_motion_complete
                              if tile.get("ghost") else None),
        children=Animated(
            key=feedback_key,
            style=Style(width="100%", height="100%"),
            enter=feedback_enter,
            children=Image(
                style=Style(width="100%", height="100%"),
                color=_tile_color(value),
                children=Panel(
                    style=Style(
                        width="100%",
                        height="100%",
                        alignItems=AlignItems.center,
                        justifyContent=JustifyContent.center,
                    ),
                    children=Label(
                        color=_tile_text_color(value),
                        fontSize=10 if value < 1024 else 8,
                        shadow=value > 4,
                        content=str(value),
                    ),
                ),
            ),
        ),
    )


@Component
def Game2048Demo():
    game, set_game = use_state(_new_game)
    stick_direction = use_ref(None)
    round_id = use_ref(0)

    def move(direction):
        def next_game(current):
            if current["over"] or current.get("merging"):
                return current
            return _move_board(current, direction)
        set_game(next_game)

    def on_key(args):
        direction = _keyboard_direction(args)
        if direction is not None:
            move(direction)

    def on_stick(args):
        direction = _stick_direction(args)
        if direction is None:
            stick_direction.current = None
            return
        if stick_direction.current == direction:
            return
        stick_direction.current = direction
        move(direction)

    def restart():
        stick_direction.current = None
        round_id.current += 1
        set_game(_new_game(round_id.current))

    def clear_merge_ghosts():
        set_game(_clear_merge_ghosts)

    use_event(EngineEvent.key_press, on_key)
    use_event(EngineEvent.gamepad_stick, on_stick)

    cells = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            cells.append(_cell(row, col))
    tiles = [_tile(tile, clear_merge_ghosts)
             for tile in game["tiles"] + game.get("ghosts", [])]
    status = GameText.game_over if game["over"] else GameText.hint

    return Panel(
        style=Style(
            width="100%",
            height="100%",
            alignItems=AlignItems.center,
            justifyContent=JustifyContent.center,
        ),
        children=Panel(
            style=Style(width=208, alignItems=AlignItems.center),
            children=[
                Panel(
                    style=Style(
                        width=BOARD_SIZE,
                        flexDirection=FlexDirection.row,
                        alignItems=AlignItems.center,
                        justifyContent=JustifyContent.space_between,
                        marginBottom=6,
                    ),
                    children=[
                        Panel(
                            children=[
                                Label(
                                    color=_TITLE_COLOR,
                                    fontSize=20,
                                    shadow=True,
                                    content=GameText.title,
                                ),
                                Label(
                                    color=_SCORE_COLOR,
                                    fontSize=7,
                                    content="SCORE " + str(game["score"]),
                                ),
                            ],
                        ),
                        FilledButton(
                            style=Style(width=54, height=18),
                            default=Color(0x5E81ACFF),
                            onClick=restart,
                            children=Label(
                                color=Colors.white,
                                fontSize=6,
                                shadow=True,
                                content=GameText.restart,
                            ),
                        ),
                    ],
                ),
                Image(
                    style=Style(width=BOARD_SIZE, height=BOARD_SIZE),
                    color=_BOARD_COLOR,
                    children=cells + tiles,
                ),
                Label(
                    style=Style(marginTop=7),
                    color=_SCORE_COLOR,
                    fontSize=7,
                    content=status,
                ),
            ],
        ),
    )
