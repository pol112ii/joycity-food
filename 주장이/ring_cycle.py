# -*- coding: utf-8 -*-
"""
결혼반지 자동 반복 — 줍기 → 만들기 → 팔기 → 다시 줍기 ...

  ① 방 바닥에서 재료 줍기 (석분 2무더기, 철괴 1무더기, 상급키트 1무더기)
  ② 주장이 봇(auto_match.py)으로 결혼반지 만들기 — 재료가 떨어질 때까지
  ③ 아이템 창에서 아까비깡을 전부 더블클릭해서 먹기 (체력 보충 — 하나에 100)
  ④ 능력 → 고물소환 → 리어카맨 클릭 → 결혼반지 팔기 → 닫기
  ⑤ ①로

auto_match.py 는 고치지 않고 그대로 불러다 씀 (이 파일이 실행할 때만 설정을 바꿈).

■ 준비 (한 번만)
  1. 주장이 봇이 이 폴더에서 잘 돌아가는 상태 (match_layout.json, items 폴더)
  2. items 폴더에 아이콘 등록: 석분, 철괴, 상급키트, 결혼반지, 아까비깡
     (py auto_match.py 캡처 → 이름 바꾸기)
  3. py -m pip install opencv-python      (바닥 그림 찾기용)
  4. py measure_ring.py                    (ring_layout.json, ring_sprites 폴더가 생김)
■ 실행:  py ring_cycle.py     F8 = 시작/정지,  F9 = 종료
"""

import os
import sys
import json
import time
import random
import threading

try:
    import numpy as np
    import mss
    import cv2
    import keyboard
    import pyautogui
    from PIL import Image
except ImportError as e:
    print("[에러] 필요한 프로그램이 없습니다:", e)
    print("cmd 에서:  py -m pip install opencv-python mss numpy pyautogui keyboard pillow pygetwindow")
    input("\n엔터를 누르면 창이 닫힙니다...")
    sys.exit(1)

import auto_match as am

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_FILE = os.path.join(HERE, "ring_layout.json")
SPRITE_DIR = os.path.join(HERE, "ring_sprites")

# ==================== 설정 ====================
RECIPE = [("석분", 2), ("철괴", 1), ("상급키트", 1)]   # 반지 1번에 넣는 재료
NUM_SLOTS = 4                       # 제작 창에 열려 있는 재료 칸 수
PILES = {"석분": 2, "철괴": 1, "상급키트": 1}         # 한 바퀴에 주울 무더기 수 (한 무더기 20개)
SELL = ("결혼반지",)                 # 리어카맨에게 팔 것
FOOD = "아까비깡"                    # 팔기 전에 아이템 창에서 전부 더블클릭해서 먹을 것
MAX_ROUNDS = 25                     # 한 바퀴에 만들기 최대 횟수 (보통 20번에 재료가 떨어짐)
CART_WAIT = 20                      # 고물소환 후 리어카맨이 나타나길 기다리는 시간(초)
SPRITE_SURE = 0.62                  # 바닥 재료 그림 일치 기준 (0~1, 높을수록 엄격). 석분은 무더기끼리
                                    # 많이 겹쳐서 0.6대로 나옴 — 주운 뒤 아이템 창으로 확인하니 안전
LABEL_SURE = 0.60                   # 리어카맨 이름 글자 일치 기준
REUSE_SURE = 0.80                   # '이미 있는 리어카맨'으로 믿을 기준 (애매하면 새로 소환)
PICK_TRIES = 6                      # 재료 한 무더기를 줍기 위해 눌러볼 최대 횟수

running = False
alive = True
_layout = None
_tpl = {}            # 인벤토리 아이콘 {이름: [이미지]}
_sprites = {}        # 바닥/리어카 그림 {이름: 이미지(BGR)}


# ==================== 창 / 좌표 ====================

def _norm(t):
    return "".join(str(t).split())


def load():
    global _layout, _tpl, _sprites
    if not os.path.exists(LAYOUT_FILE):
        print("[중단] ring_layout.json 이 없어요 — py measure_ring.py 부터")
        return False
    try:
        with open(LAYOUT_FILE, encoding="utf-8") as f:
            _layout = json.load(f)
    except ValueError:
        print("[중단] ring_layout.json 이 깨져 있어요 (저장이 덜 됨) — py measure_ring.py 를 다시 하세요")
        return False
    if am.load_layout() is None:
        print("[중단] match_layout.json 이 없어요 — 주장이 봇 준비(사용법.txt 4번)부터")
        return False
    _tpl = am.load_templates()
    need = {n for n, _ in RECIPE} | set(SELL) | {FOOD}
    missing = need - _tpl.keys()
    if missing:
        print(f"[중단] items 폴더에 아이콘이 없는 것: {', '.join(sorted(missing))}")
        print("       py auto_match.py 캡처 → 이름 바꾸기 (아까비깡은 실패해서 하나 생겼을 때 캡처)")
        if missing - {"아까비깡"}:
            return False
    _sprites = {}
    for key, v in _layout["sprites"].items():
        img = cv2.imread(os.path.join(SPRITE_DIR, v["file"]))
        if img is None:
            img = cv2.cvtColor(np.array(Image.open(os.path.join(SPRITE_DIR, v["file"]))
                                        .convert("RGB")), cv2.COLOR_RGB2BGR)
        _sprites[key] = img
    return True


def find_title(title):
    """제목이 title 인 '떠 있는' 창 (띄어쓰기 무시)."""
    want = _norm(title)
    try:
        for w in am._gw.getAllWindows():
            if _norm(w.title) == want and am._really_shown(w):
                return w
    except Exception:
        pass
    return None


def _is_main(w):
    """게임 메인 창인지 — 측정 때 기록한 제목과 똑같아야 함 (브라우저 탭 제목 등과 구별)."""
    return _norm(w.title) == _norm(_layout["titles"]["main"])


def main_win():
    ws = [w for w in am._gw.getAllWindows() if _is_main(w) and am._really_shown(w)]
    return max(ws, key=lambda w: w.width * w.height) if ws else None


_last_scale = None


def system_dpi():
    """윈도우 화면 배율(DPI). 100% = 96, 125% = 120. 못 읽으면 None."""
    try:
        import ctypes
        return int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        return None


def scale():
    """측정한 컴퓨터 대비 지금 화면 배율 — 떠 있는 창(제작/아이템) 폭으로 계산.

    제작 창은 닫혀 있을 때가 많아서, 늘 떠 있는 아이템 창으로도 계산함.
    둘 다 없으면 윈도우 화면 배율(DPI) 비율, 그것도 안 되면 마지막 값(처음이면 1.0).
    """
    global _last_scale
    w = find_title(_layout_title("craft"))
    if w is not None:
        _last_scale = w.width / _layout["ref_craft_w"]
        return _last_scale
    ref_item = _layout.get("sizes", {}).get("item")
    w = find_title(_layout["titles"]["item"]) if ref_item else None
    if w is not None:
        _last_scale = w.width / ref_item[0]
        return _last_scale
    dpi, ref_dpi = system_dpi(), _layout.get("dpi")
    if dpi and ref_dpi:
        return dpi / ref_dpi
    return _last_scale or 1.0


def _layout_title(kind):
    if kind == "craft":
        return am._layout["titles"]["craft"]
    return _layout["titles"][kind]


def main_pt(name):
    """메인 창의 고정 위치 (아래 메뉴 아이콘) — 창 왼쪽 아래 기준."""
    w = main_win()
    p = _layout["points"][name]
    k = scale()
    y = w.top + w.height - p["dy_bottom"] * k
    x = w.left + p["dx_left"] * k
    return int(round(x)), int(round(y))


def win_pt(name, w=None):
    p = _layout["points"][name]
    w = w or find_title(_layout["titles"][p["win"]])
    if w is None:
        return None
    return (int(round(w.left + p["fx"] * w.width)), int(round(w.top + p["fy"] * w.height)))


def grid(prefix):
    """창 안 6x5 칸 중심 좌표 목록 (prefix = item / sell)."""
    a, b, c = win_pt(prefix + "_first"), win_pt(prefix + "_row1_last"), win_pt(prefix + "_row5_first")
    if None in (a, b, c):
        return None
    px, py = (b[0] - a[0]) / 5, (c[1] - a[1]) / 4
    pts = [(int(round(a[0] + col * px)), int(round(a[1] + row * py)))
           for row in range(5) for col in range(6)]
    return snap_grid(pts, px, py)


def snap_grid(pts, px, py):
    """찍은 자리가 몇 픽셀 어긋났어도 실제 칸 가운데로 맞춤.

    빈 칸은 속이 새까만 네모라서, 각 빈 칸에서 '까만 네모가 통째로 들어가는 자리'의
    가운데를 찾고, 그걸로 줄/열 위치를 다시 계산함. (빈 칸이 모자라면 그대로 씀)
    """
    try:
        pitch = min(abs(px), abs(py))
        h = int(pitch * 0.36)              # 까만 속 네모의 반 크기 (테두리 안쪽)
        r = int(pitch * 0.3)               # 이만큼까지 어긋난 건 맞춰줌
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        left, top = min(xs) - h - r, min(ys) - h - r
        w, hh = max(xs) - min(xs) + 2 * (h + r) + 1, max(ys) - min(ys) + 2 * (h + r) + 1
        with mss.mss() as sct:
            img = shot_bgr(sct, left, top, w, hh)
        bright = (img.astype(int).sum(axis=2) > 60).astype(np.int32)
        ii = np.pad(bright.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        fits = []                           # (열, 줄, 실제 x, 실제 y)
        for i, (x, y) in enumerate(pts):
            x, y = x - left, y - top
            ok = []
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    y0, y1, x0, x1 = y + dy - h, y + dy + h + 1, x + dx - h, x + dx + h + 1
                    if ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0] == 0:
                        ok.append((dx, dy))
            if ok:
                dxs, dys = [o[0] for o in ok], [o[1] for o in ok]
                fits.append((i % 6, i // 6, x + (min(dxs) + max(dxs)) / 2 + left,
                             y + (min(dys) + max(dys)) / 2 + top))
        if len({f[0] for f in fits}) < 2 or len({f[1] for f in fits}) < 2:
            return pts
        cx = np.polyfit([f[0] for f in fits], [f[2] for f in fits], 1)
        cy = np.polyfit([f[1] for f in fits], [f[3] for f in fits], 1)
        new = [(int(round(np.polyval(cx, i % 6))), int(round(np.polyval(cy, i // 6))))
               for i in range(len(pts))]
        if max(max(abs(n[0] - p[0]), abs(n[1] - p[1])) for n, p in zip(new, pts)) > r + 2:
            return pts
        return new
    except Exception:
        return pts


def wait_title(kind, shown=True, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout and running and alive:
        if (find_title(_layout["titles"][kind]) is not None) == shown:
            return True
        time.sleep(0.15)
    return False


# ==================== 화면 읽기 ====================

def shot_bgr(sct, left, top, w, h):
    s = sct.grab({"left": int(left), "top": int(top), "width": int(w), "height": int(h)})
    return np.asarray(s)[:, :, :3].copy()


def ident(sct, pos, names):
    """칸 하나에 든 아이템 이름 ('' = 빈 칸, None = 모르는 것). names 중에서만 고름."""
    region = am.grab_cell(sct, pos[0], pos[1])
    center = region[am.ALIGN + am.TOP_CUT:am.ALIGN + am.CELL_SIZE, am.ALIGN:am.ALIGN + am.CELL_SIZE]
    if int((center.sum(axis=2) > 90).sum()) < am.MIN_ITEM_PX:
        return ""
    best, bd = None, 1e9
    for n in names:
        for t in _tpl.get(n, []):
            d = am.match_region(region, t)
            if d < bd:
                best, bd = n, d
    return best if best is not None and bd <= am.threshold_for(best) else None


def other_windows():
    """메인 창 '위에' 떠 있는 창들의 사각형 (그 안에서 찾은 건 바닥 그림이 아님).

    창 목록은 화면 맨 위 창부터 나오므로, 게임 메인 창이 나오기 전까지만 셈.
    (게임 뒤에 깔린 브라우저 같은 창까지 세면 방 전체를 가린 걸로 오해함)
    """
    rects = []
    for w in am._gw.getAllWindows():
        t = str(w.title)
        if _is_main(w):
            break
        if t.strip() and am._really_shown(w):
            rects.append((w.left, w.top, w.left + w.width, w.top + w.height))
    return rects


_best_size = {}     # 그림별로 잘 맞았던 크기 배율 (다음엔 그것부터 씀)


def find_sprite(sct, key, sure, binary=False):
    """메인 창에서 그림(key)을 찾아 [(중심x, 중심y, 점수), ...] (점수 높은 순).

    화면 배율이 측정한 컴퓨터와 다르면 그림 크기도 다른데, 게임이 글자/그림을
    새로 그리기 때문에 단순히 늘린 그림과 딱 맞지는 않음. 그래서 몇 가지 크기
    (측정 때 그대로, 배율만큼, ±8%)로 대보고 가장 잘 맞는 크기를 씀.
    """
    w = main_win()
    if w is None:
        return []
    img = shot_bgr(sct, w.left, w.top, w.width, w.height)
    if binary:
        # 이름 글자: 밝은 글자 픽셀만 비교 (뒤 배경이 달라도 글자 모양으로 찾음)
        img = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
    k = scale()
    sizes = [_best_size[key]] if key in _best_size else []
    sizes += [s for s in (k, 1.0, k * 0.92, k * 1.08) if all(abs(s - t) > 0.02 for t in sizes)]
    best = None
    for f in sizes:
        tpl = _sprites[key]
        if abs(f - 1) > 0.02:
            tpl = cv2.resize(tpl, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        if binary:
            tpl = (cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
        th, tw = tpl.shape[:2]
        if th < 4 or tw < 4 or th >= img.shape[0] or tw >= img.shape[1]:
            continue
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        mx = float(res.max())
        if best is None or mx > best[0]:
            best = (mx, f, res, th, tw)
        if mx >= 0.9:                  # 충분히 잘 맞으면 다른 크기는 안 봐도 됨
            break
    if best is None:
        return []
    mx, f, res, th, tw = best
    if mx >= sure:
        _best_size[key] = f
    rects = other_windows()
    # 아래 메뉴 줄과 그 밑 채팅창은 방이 아님 ("[알림] 리어카맨을 소환했어요!" 같은 글자를 착각함)
    try:
        floor_bottom = main_pt("item_icon")[1] - 30 * k
    except Exception:
        floor_bottom = w.top + w.height
    out = []
    while len(out) < 40:
        _, mx, _, (x, y) = cv2.minMaxLoc(res)
        if mx < sure:
            break
        cx, cy = w.left + x + tw / 2, w.top + y + th / 2
        if cy < floor_bottom and not any(a <= cx < c and b <= cy < d for a, b, c, d in rects):
            out.append((int(cx), int(cy), float(mx)))
        res[max(0, y - th // 2):y + th // 2 + 1, max(0, x - tw // 2):x + tw // 2 + 1] = -1
    return out


# ==================== 마우스 ====================

def click_at(pt, jx=3, jy=3, label=None):
    am.human_click(pt, jx=jx, jy=jy)
    if label:
        print(f"  {label} → {pt}")


def double_click(pt):
    x, y = pt[0] + random.randint(-3, 3), pt[1] + random.randint(-3, 3)
    am.smooth_move_to(x, y, random.uniform(0.25, 0.45) * am.MOUSE_SPEED, bow=8)
    time.sleep(random.uniform(0.1, 0.2))
    for _ in range(2):
        pyautogui.mouseDown()
        time.sleep(random.uniform(0.04, 0.08))
        pyautogui.mouseUp()
        time.sleep(random.uniform(0.06, 0.11))


# ==================== ① 줍기 ====================

def all_names():
    """칸을 알아볼 때 비교할 이름 — items 폴더에 등록된 아이콘 전부.

    반지 재료만 비교하면, 인벤토리에 섞인 다른 아이템(예: 하급키트)이 생김새가
    비슷한 재료(상급키트)로 착각돼서 재료 칸에 들어갈 수 있음.
    """
    names = [n for n, _ in RECIPE] + list(SELL) + [FOOD]
    return names + sorted(n for n in _tpl if n not in names)


def ensure_item_window():
    """아이템 창이 안 떠 있으면 아래 메뉴 [아이템] 아이콘으로 엶."""
    if find_title(_layout["titles"]["item"]) is not None:
        return True
    am.direct_click(main_pt("item_icon"), "아이템")
    return wait_title("item", True, 4)


def item_contents(sct):
    """아이템 창 30칸의 내용 [(칸 중심, 이름), ...]  ('' = 빈 칸, None = 모르는 것)."""
    if not ensure_item_window():
        print("  [주의] 아이템 창이 안 열림")
        return []
    cells = grid("item")
    mx, my = pyautogui.position()
    w = find_title(_layout["titles"]["item"])
    if w is not None and w.left <= mx < w.left + w.width and w.top <= my < w.top + w.height:
        # 커서가 칸을 가리면 잘못 읽으니 아이템 창 밖으로 살짝 비켜둠
        am.smooth_move_to(w.left - random.randint(30, 80), my, random.uniform(0.2, 0.35), bow=6)
    names = all_names()
    return [(pos, ident(sct, pos, names)) for pos in cells]


def material_cells(sct):
    """아이템 창에서 재료별 칸 수."""
    got = [n for _, n in item_contents(sct)]
    return {n: got.count(n) for n in PILES}


_short = set()          # 지난 만들기 때 모자랐던 재료 (칸은 있어도 개수가 모자람) → 한 무더기 더 주움


def pick_up(sct):
    """바닥에서 모자란 무더기를 주움. 다 주웠으면 True."""
    have = material_cells(sct)
    print(f"[줍기] 지금 인벤토리: {have} / 필요: {PILES}")
    want = {n: (max(p, have.get(n, 0) + 1) if n in _short else p) for n, p in PILES.items()}
    if _short:
        print(f"  지난번에 모자랐던 것: {', '.join(sorted(_short))} → 한 무더기 더")
        _short.clear()
    for name, piles in want.items():
        while running and alive and have.get(name, 0) < piles:
            cands = find_sprite(sct, "spr_" + name, SPRITE_SURE)
            if not cands:
                print(f"[중단] 바닥에서 '{name}' 을 못 찾음 — 재료가 다 떨어졌거나 그림 기준이 안 맞음")
                return False
            before = have.get(name, 0)
            ok = False
            for cx, cy, sc in cands[:PICK_TRIES]:
                click_at((cx, cy), label=f"'{name}' 줍기 (일치 {sc:.2f})")
                time.sleep(random.uniform(0.9, 1.3))
                have = material_cells(sct)
                if have.get(name, 0) > before:
                    ok = True
                    break
                print("    안 주워짐 → 다른 무더기")
            if not ok:
                print(f"[중단] '{name}' 을 눌러도 안 주워짐 — 그림 위치가 안 맞는 듯")
                return False
    am._scan_cache = None          # 칸 배치가 바뀌었으니 주장이 봇이 새로 스캔하게
    return True


# ==================== ② 만들기 ====================

def slot_names(sct):
    """제작 창 재료 칸에 지금 들어 있는 것 ['석분', None(모름), '' (빈 칸), ...]."""
    am.apply_craft_layout()
    names = all_names()
    return [ident(sct, (int(am.SLOT1_CENTER[0] + i * am.SLOT_PITCH_X), int(am.SLOT1_CENTER[1])), names)
            for i in range(NUM_SLOTS)]


def recipe_ok(sct):
    """재료 칸에 레시피와 다른 재료가 들어갔는지 확인. 다르면 False.

    칸 그림을 못 알아본 것(None)은 틀렸다고 보지 않음 — 확실히 다른 재료로 읽힐 때만 False.
    """
    got = slot_names(sct)
    want = {}
    for n, c in RECIPE:
        want[n] = want.get(n, 0) + c
    have = {}
    for n in got:
        if n:
            have[n] = have.get(n, 0) + 1
    wrong = [n for n in have if have[n] > want.get(n, 0)]
    if wrong:
        print(f"  [재료 확인] 칸에 든 것: {got} → 레시피와 다름 ({', '.join(wrong)})")
        return False
    if None in got:
        print(f"  [재료 확인] 칸에 든 것: {got} (못 알아본 칸은 그냥 진행)")
    return True


def find_red_close(sct, w):
    """창 오른쪽 위 빨간 동그라미(닫기 버튼) 위치. 못 찾으면 None."""
    bw, bh = min(160, w.width), min(70, w.height)
    img = shot_bgr(sct, w.left + w.width - bw, w.top, bw, bh).astype(int)
    b, g, r = img[:, :, 0], img[:, :, 1], img[:, :, 2]
    ys, xs = np.nonzero((r > 190) & (g < 120) & (b < 120))
    if len(xs) < 20:
        return None
    return (int(w.left + w.width - bw + xs.mean()), int(w.top + ys.mean()))


def close_craft(sct):
    """제작 창을 빨간 버튼으로 닫음 (넣은 재료는 인벤토리로 돌아감)."""
    w = am.find_win("craft")
    if w is None:
        return True
    pt = find_red_close(sct, w)
    if pt is None:
        print("  [문제] 제작 창 빨간 닫기 버튼을 못 찾음")
        return False
    click_at(pt, jx=2, jy=2, label="제작 창 닫기")
    for _ in range(16):
        time.sleep(0.25)
        if not am.craft_open(sct):
            time.sleep(random.uniform(0.5, 0.9))
            return True
    print("  [문제] 제작 창이 안 닫힘")
    return False


def craft_all(sct):
    """재료가 떨어질 때까지 반지 만들기. 몇 번 했는지 반환 (-1 = 오류로 멈춤)."""
    am.RECIPE = list(RECIPE)
    am.NUM_SLOTS = NUM_SLOTS
    am.JOB_KEY = None                     # F2 가 안 먹어서 아래 메뉴 직업 아이콘을 누름
    am.JOB_BTN = main_pt("job_icon")
    am._scan_cache = None
    tpl = {n: _tpl[n] for n in all_names() if n in _tpl}   # 반지/아까비깡도 알아야 재료로 착각 안 함
    done = fails = 0
    while running and alive and done < MAX_ROUNDS:
        am.JOB_BTN = main_pt("job_icon")
        if not am.open_furniture_window(sct):
            return -1
        left = am.filled_slots(sct, NUM_SLOTS)
        if left:
            # 지난번에 넣다 만 재료가 칸에 남아 있음 → 그대로 넣으면 레시피가 틀어짐
            print(f"  [재료 확인] 넣기 전인데 칸 {[i + 1 for i in left]} 에 재료가 남아 있음 → 제작 창 닫고 다시")
            am._scan_cache = None
            fails += 1
            if not close_craft(sct) or fails >= 3:
                print("[중단] 남은 재료가 안 빠짐")
                return -1
            continue
        if not am.fill_slots(sct, tpl):
            # 넣다가 실패 → 이미 넣은 재료는 칸에 남음. 무엇이 모자랐는지 보고, 창을 닫아서 돌려받음
            got = [n for n in slot_names(sct) if n]
            plan = [n for n, c in RECIPE for _ in range(c)]
            for n in got:
                if n in plan:
                    plan.remove(n)
            if plan and None not in slot_names(sct):
                _short.add(plan[0])
            am._scan_cache = None
            if not close_craft(sct):
                return -1
            print(f"[만들기] 재료를 다 못 넣음 → {done}번 만들고 이번 바퀴 끝"
                  + (f" (모자란 것: {plan[0]} → 다음 바퀴에 한 무더기 더 주움)" if plan else ""))
            return done
        if not recipe_ok(sct):
            # 다른 재료가 들어감 → 제작 창을 닫았다가 다시 열어서 처음부터 넣음
            print("  → 제작 창을 닫고 다시 열어서 재료를 새로 넣음")
            am._scan_cache = None
            fails += 1
            if not close_craft(sct) or fails >= 3:
                print("[중단] 재료가 계속 잘못 들어감")
                return -1
            continue
        if not am.press_start(sct):
            fails += 1
            if fails >= 3:
                return -1
            continue
        ok, stats = am.play_board(sct)
        if ok:
            done += 1
            fails = 0
            print(f"★ 반지 만들기 {done}번째 완료 (클릭 {stats['clicks']}회, {stats['secs']}초)")
            time.sleep(random.uniform(1.0, 2.0))
        else:
            fails += 1
            if fails >= 3:
                return -1
    return done


# ==================== ③ 먹기 / ④ 팔기 ====================

def eat_all(sct):
    """아이템 창에서 아까비깡을 전부 더블클릭해서 먹음 (체력 보충).

    아까비깡은 한 칸에 여러 개 쌓이므로(예: 3), 한 칸을 그 칸이 빌 때까지 계속
    더블클릭함. 먹을 때마다 커서를 옆 칸으로 살짝 비켜서 그 칸을 다시 확인
    (커서가 칸을 덮고 있으면 아이콘을 잘못 읽음).
    """
    eaten = 0
    names = all_names()
    for _ in range(3):                      # 먹고 나면 칸이 당겨질 수 있어서 다시 확인
        cells = grid("item")
        foods = [pos for pos, n in item_contents(sct) if n == FOOD]
        if not foods or cells is None:
            break
        pitch = max(cells[1][0] - cells[0][0], 20)
        for pos in foods:
            for _ in range(40):             # 한 칸 최대 40개까지
                if not (running and alive):
                    return
                double_click(pos)
                eaten += 1
                time.sleep(random.uniform(0.5, 0.8))
                side = -pitch if pos[0] - pitch > cells[0][0] - pitch / 2 else pitch
                am.smooth_move_to(pos[0] + side, pos[1] + random.randint(-4, 4),
                                  random.uniform(0.12, 0.22), bow=3)
                time.sleep(random.uniform(0.1, 0.2))
                if ident(sct, pos, names) != FOOD:
                    break
    if eaten:
        print(f"[먹기] 아까비깡 {eaten}개 먹음")


def ability_ready(sct, timeout=4.0):
    """능력 창이 '다 그려질' 때까지 기다림.

    능력 창은 열릴 때 잠깐 빈 판만 보이는데, 그때 누른 고물소환은 무시됨
    (영상으로 확인). 고물소환 줄에 아이콘/글자가 그려져서 무늬가 생기면 준비 끝.
    """
    t0 = time.time()
    while time.time() - t0 < timeout and running and alive:
        pt = win_pt("summon")
        if pt is not None:
            k = scale()
            hw, hh = int(60 * k), int(12 * k)
            img = shot_bgr(sct, pt[0] - hw, pt[1] - hh, hw * 2, hh * 2)
            if cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).std() > 12:
                time.sleep(random.uniform(0.2, 0.4))
                return True
        time.sleep(0.1)
    return False


_seen = []                      # [마지막으로 찾은 리어카맨 위치, 그때 시각]
_bad_carts = []                 # 눌러도 되팔기 창이 안 열리던 리어카맨 자리 (다음 바퀴에도 기억)


def _far(found, bad, dist=70):
    """bad(안 눌리던 자리) 근처에서 찾은 건 뺌."""
    return [c for c in found if all((c[0] - b[0]) ** 2 + (c[1] - b[1]) ** 2 > dist ** 2 for b in bad)]


def summon_cart(sct, bad=(), reuse=True):
    """능력 → 고물소환 → 능력 창 닫기 → 리어카맨이 나타나면 위치 반환.

    고물소환은 누를 때마다 한 명씩 생기므로 한 번만 누르고, 리어카맨이 한참
    안 보일 때만(클릭이 씹혔을 때) 한 번 더 시도함.
    """
    if reuse:
        old = _far(find_sprite(sct, "cart_label", REUSE_SURE, binary=True), _bad_carts)
        if old:
            print(f"  이미 있는 리어카맨 이름을 찾음 ({old[0][0]}, {old[0][1]}, 일치 {old[0][2]:.2f})")
            return old[0]                   # 이미 소환된 리어카맨이 있음
    for attempt in range(2):
        if find_title(_layout["titles"]["ability"]) is None:
            am.direct_click(main_pt("ability_icon"), "능력")
            if not wait_title("ability", True, 5):
                print("[문제] 능력 창이 안 열림")
                return None
        if not ability_ready(sct):
            print("  (능력 창 내용이 늦게 뜸 — 그래도 눌러봄)")
        click_at(win_pt("summon"), jx=20, jy=3, label="고물소환")
        time.sleep(random.uniform(0.6, 1.0))
        click_at(win_pt("ability_close"), jx=1, jy=1, label="능력 창 닫기")
        wait_title("ability", False, 3)
        t0 = time.time()
        while running and alive and time.time() - t0 < CART_WAIT:
            found = _far(find_sprite(sct, "cart_label", LABEL_SURE, binary=True), bad)
            if found:
                _seen[:] = [found[0], time.time()]
                return found[0]
            time.sleep(0.1)
        if attempt == 0:
            print(f"  고물소환 후 {CART_WAIT}초 동안 리어카맨이 안 보임 → 한 번 더 소환")
    print("[문제] 리어카맨이 안 나타남 (체력 부족이거나 이름 글자 그림이 안 맞음)")
    return None


def save_cart_debug(sct, click, cart):
    """리어카맨이 안 눌렸을 때 게임 화면을 cart_debug.png 로 저장 (초록 = 찾은 이름, 빨강 = 누른 곳)."""
    try:
        w = main_win()
        if w is None:
            return
        from PIL import ImageDraw
        img = Image.fromarray(shot_bgr(sct, w.left, w.top, w.width, w.height)[:, :, ::-1])
        d = ImageDraw.Draw(img)
        lx, ly = cart[0] - w.left, cart[1] - w.top
        d.rectangle([lx - 40, ly - 12, lx + 40, ly + 12], outline=(0, 255, 0), width=2)
        x, y = click[0] - w.left, click[1] - w.top
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 0, 0), width=3)
        img.save(os.path.join(HERE, "cart_debug.png"))
        print(f"  → 화면을 cart_debug.png 로 저장 (이름 일치 {cart[2]:.2f})")
    except Exception as e:
        print("  (디버그 저장 실패:", e, ")")


def save_sell_debug(sct, w, cells, names):
    """못 알아봤을 때 되팔기 창을 칸 위치 표시와 함께 sell_debug.png 로 저장."""
    try:
        if w is None:
            return
        img = Image.fromarray(shot_bgr(sct, w.left, w.top, w.width, w.height)[:, :, ::-1])
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for pos in cells or []:
            x, y = pos[0] - w.left, pos[1] - w.top
            d.rectangle([x - 4, y - 4, x + 4, y + 4], outline=(255, 0, 255))
        img.save(os.path.join(HERE, "sell_debug.png"))
        print("  → 화면을 sell_debug.png 로 저장했어요 (분홍 네모 = 칸을 보는 자리)")
        for pos in (cells or [])[:6]:
            region = am.grab_cell(sct, pos[0], pos[1])
            ds = {n: min((am.match_region(region, t) for t in _tpl.get(n, [])), default=None)
                  for n in SELL}
            print(f"    칸 {pos}: 읽은 것={ident(sct, pos, names)!r}  반지 차이={ds}")
    except Exception as e:
        print("  (디버그 저장 실패:", e, ")")


def locate_near(sct, c, radius):
    """c 근처(±radius)에서만 리어카맨 이름을 빨리 찾음 → (x, y, 점수) 또는 None."""
    w = main_win()
    if w is None or "cart_label" not in _sprites:
        return None
    f = _best_size.get("cart_label", scale())
    tpl = _sprites["cart_label"]
    if abs(f - 1) > 0.02:
        tpl = cv2.resize(tpl, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    tpl = (cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
    th, tw = tpl.shape[:2]
    try:
        bottom = main_pt("item_icon")[1] - 30 * scale()
    except Exception:
        bottom = w.top + w.height
    l = max(w.left, int(c[0] - radius - tw / 2))
    t = max(w.top, int(c[1] - radius - th / 2))
    r = min(w.left + w.width, int(c[0] + radius + tw / 2))
    b = min(int(bottom), int(c[1] + radius + th / 2))
    if r - l <= tw or b - t <= th:
        return None
    img = (cv2.cvtColor(shot_bgr(sct, l, t, r - l, b - t), cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, (x, y) = cv2.minMaxLoc(res)
    if mx < LABEL_SURE:
        return None
    return (int(l + x + tw / 2), int(t + y + th / 2), float(mx))


def click_cart(sct, cart, body):
    """걸어 다니는 리어카맨을 누름.

    잠깐 사이에 두 번 위치를 재서 걷는 속도/방향을 구하고, 마우스가 도착할
    때쯤 있을 자리를 미리 계산해서 한 번에 부드럽게 가서 누름.
    (따라가며 여러 번 고치는 것보다 자연스럽고 잘 맞음)
    """
    if _seen and _seen[0] == cart and time.time() - _seen[1] < 1.0:
        p1, t1 = cart, _seen[1]             # 방금 찾은 위치를 첫 번째로 씀 → 기다릴 필요 없음
    else:
        p1 = locate_near(sct, cart, 250) or cart
        t1 = time.time()
        time.sleep(0.08)
    p2 = locate_near(sct, p1, 120) or p1
    t2 = time.time()
    vx, vy = (p2[0] - p1[0]) / (t2 - t1), (p2[1] - p1[1]) / (t2 - t1)
    if (vx * vx + vy * vy) ** 0.5 > 600:        # 엉뚱한 걸 잡았으면 속도는 무시
        vx = vy = 0.0
    d = random.uniform(0.22, 0.32)
    lead = (time.time() - t2) + d + 0.08
    bx, by = body(p2)
    tx, ty = int(bx + vx * lead), int(by + vy * lead)
    am.smooth_move_to(tx, ty, d, bow=6)
    # 도착해서 한 번 더 확인 — 예상보다 많이 어긋났으면(벽에서 방향을 틀었을 때 등) 살짝 고침
    p3 = locate_near(sct, p2, 120)
    if p3:
        nx, ny = body(p3)
        nx, ny = int(nx + vx * 0.06), int(ny + vy * 0.06)
        if abs(nx - tx) > 18 or abs(ny - ty) > 18:
            am.smooth_move_to(nx, ny, random.uniform(0.05, 0.08), bow=0)
            tx, ty = nx, ny
        p2 = p3
    time.sleep(random.uniform(0.02, 0.05))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.04, 0.08))
    pyautogui.mouseUp()
    return tx, ty, p2


def sell_all(sct):
    """아까비깡을 먹고, 리어카맨에게 결혼반지를 전부 팜. 팔 게 없으면 바로 True."""
    eat_all(sct)
    n_sell = sum(1 for _, n in item_contents(sct) if n in SELL)
    if n_sell == 0:
        return True
    print(f"[팔기] 팔 것 {n_sell}개")
    names = all_names()
    cart = summon_cart(sct)
    if cart is None:
        return False
    bad = _bad_carts
    fails = 0
    summoned_new = False
    off = _layout["points"]["cart_body"]
    k = scale()

    def body(c):
        return int(c[0] + off["off_x"] * k), int(c[1] + off["off_y"] * k)

    for attempt in range(5):
        tx, ty, cart = click_cart(sct, cart, body)
        print(f"  리어카맨 클릭 → ({tx}, {ty})  (이름 일치 {cart[2]:.2f})")
        if wait_title("sell", True, 3):
            break
        print("  되팔기 창이 안 뜸 → 다시")
        fails += 1
        if fails == 1:
            save_cart_debug(sct, (tx, ty), cart)
        if fails >= 2 and not summoned_new:
            # 같은 자리를 두 번 눌러도 안 열림 → 남아 있던(눌리지 않는) 리어카맨이거나 잘못 찾은 것
            # → 그 자리는 빼고 새로 소환
            bad.append(cart[:2])
            print("  그 자리는 진짜 리어카맨이 아닌 것 같음 → 새로 소환")
            summoned_new = True
            new = summon_cart(sct, bad=bad, reuse=False)
            if new is None:
                return False
            cart = new
            continue
        again = _far(find_sprite(sct, "cart_label", LABEL_SURE, binary=True), bad)
        if again:
            cart = again[0]
    else:
        print("[문제] 리어카맨을 눌러도 되팔기 창이 안 뜸 — cart_debug.png 를 보내주세요")
        return False
    time.sleep(random.uniform(0.5, 0.8))
    w = find_title(_layout["titles"]["sell"])
    mx, my = pyautogui.position()
    if w is not None and w.left <= mx < w.left + w.width and w.top <= my < w.top + w.height:
        # 리어카맨을 누른 자리가 되팔기 창 안이면 커서(설명 풍선)가 칸을 가림 → 창 밖으로 비켜둠
        am.smooth_move_to(w.left - random.randint(30, 80), my, random.uniform(0.2, 0.35), bow=6)
        time.sleep(random.uniform(0.3, 0.5))
    cells = grid("sell")
    rings = []
    for _ in range(3):                      # 창이 막 열려서 그림이 덜 그려졌을 수 있으니 몇 번 봄
        rings = [pos for pos in cells if ident(sct, pos, names) in SELL]
        if rings:
            break
        time.sleep(0.7)
    clicked = 0
    for pos in rings:
        if not (running and alive):
            return False
        click_at(pos, jx=4, jy=4)
        clicked += 1
        time.sleep(random.uniform(0.25, 0.45))
    if clicked == 0:
        # 아이템 창엔 반지가 있는데 되팔기 창에서 못 알아봄 → 계속 소환하면 체력만 닳으니 멈춤
        print("[문제] 되팔기 창에서 결혼반지를 못 알아봄 — 칸 위치(measure_ring.py)를 확인하세요")
        save_sell_debug(sct, w, cells, names)
        click_at(win_pt("sell_close"), jx=8, jy=3, label="닫기")
        return False
    print(f"  {clicked}개 올림 → 팔기")
    time.sleep(random.uniform(0.3, 0.6))
    click_at(win_pt("sell_btn"), jx=10, jy=3, label="팔기")
    time.sleep(random.uniform(1.0, 1.5))
    click_at(win_pt("sell_close"), jx=8, jy=3, label="닫기")
    wait_title("sell", False, 3)
    am._scan_cache = None
    return True


# ==================== 반복 ====================

def worker():
    global running, alive
    try:
        if not load():
            alive = False
            return
        print(f"준비 완료 — 그림: {', '.join(_sprites)}  /  F8 로 시작")
        cycle = zero = 0
        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.15)
                    continue
                am.running = am.alive = True
                cycle += 1
                print(f"\n========== {cycle}바퀴째 ==========")
                if not sell_all(sct):
                    running = False
                    print("⏸ 팔기 실패로 멈춤 — 확인 후 F8")
                    continue
                if not pick_up(sct):
                    running = False
                    print("⏸ 줍기 실패로 멈춤 — 확인 후 F8")
                    continue
                n = craft_all(sct)
                if n < 0:
                    running = False
                    print("⏸ 만들기 오류로 멈춤 — 확인 후 F8")
                    continue
                zero = zero + 1 if n == 0 else 0
                if zero >= 3:
                    running = False
                    zero = 0
                    print("⏸ 3바퀴 연속 하나도 못 만들어서 멈춤 — 재료/화면 확인 후 F8")
    except pyautogui.FailSafeException:
        print("\n[비상정지] 마우스가 화면 구석으로 갔습니다. 완전히 종료합니다.")
        alive = False
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
        alive = False


def toggle():
    global running
    running = not running
    am.running = running
    print("\n▶ 시작됨" if running else "\n⏸ 정지됨 (지금 하던 동작이 끝나면 멈춤)")


def quit_all():
    global running, alive
    running = alive = False
    am.running = am.alive = False
    print("\n종료합니다...")


def main():
    print("=" * 56)
    print(" 결혼반지 자동 반복 (줍기 → 만들기 → 팔기)")
    print(" F8 = 시작/정지    F9 = 종료")
    print(" 비상시: 마우스를 화면 왼쪽 위 구석으로!")
    print(" ※ 주장이 봇(auto_match.py)과 동시에 켜지 마세요")
    print("=" * 56)
    keyboard.add_hotkey("f8", toggle)
    keyboard.add_hotkey("f9", quit_all)
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while alive:
        time.sleep(0.2)
    print("끝.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
