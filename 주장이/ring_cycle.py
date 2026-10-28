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
SELL_AT = (5, 10)                   # 반지가 이 사이 개수(매번 랜덤)만큼 쌓이면 팔러 감
                                    # (딱 정하려면 SELL_AT = 10 처럼 숫자 하나)
RECOVER_MAX = 3                     # 실패하면 게임 창을 정리하고 처음부터 다시 — 연속으로 이만큼 실패하면 멈춤
REUSE_SURE = 0.80                   # '이미 있는 리어카맨'으로 믿을 기준 (애매하면 새로 소환)
PICK_TRIES = 6                      # 재료 한 무더기를 줍기 위해 눌러볼 최대 횟수

# ----- 쉬는 시간 (쉬지 않고 계속 만들면 매크로로 보일 수 있어서) -----
# 세 종류를 섞음. 범위 안에서 매번 랜덤이고, 대부분 짧은 쪽으로 나오다가 가끔 길게 나옴.
# 판이 끝나고 다음 판 시작 전에만 쉼 (카드판/리어카맨 중간에는 안 쉼). 쉬는 중에도 F8 = 바로 멈춤
REST = True                         # False 로 하면 안 쉼
PAUSE_CHANCE = 0.15                 # ① 멈칫: 판 사이에 이 확률로
PAUSE_SECS = (3, 20)                #          이만큼(초) 잠깐 멈춤
SHORT_EVERY = (4, 10)               # ② 짧은 쉼: 이 판수마다
SHORT_SECS = (20, 150)              #          이만큼(초) 쉼
LONG_EVERY = (30, 70)               # ③ 긴 휴식: 이만큼(분) 돌 때마다
LONG_MINS = (4, 15)                 #          이만큼(분) 쉼

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
        # (cv2.imread 는 한글 폴더 경로를 못 읽어서 PIL 로 읽음)
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
    # 제목 줄 높이만 봄 (더 내려가면 칸 안의 빨간 반지 그림까지 섞임)
    bw, bh = min(160, w.width), min(max(28, int(w.height * 0.09)), w.height)
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


def close_game_windows(sct):
    """조이톡 메인 창만 남기고 게임 안에서 뜬 창(되팔기/능력/아이템/카드판/제작/직업)을 닫음.

    다른 프로그램 창(cmd, 브라우저 등)은 건드리지 않음.
    """
    kinds = [(_layout["titles"].get(k), k) for k in ("sell", "ability", "item")]
    if am._layout is not None:
        kinds += [(am._layout["titles"].get(k), k) for k in ("card", "craft", "job")]
    closed = []
    for _ in range(2):                      # 닫고 나면 밑에 있던 창이 보일 수 있어서 두 번 훑음
        for title, kind in kinds:
            if not title or _norm(title) == _norm(_layout["titles"]["main"]):
                continue
            w = find_title(title)
            if w is None:
                continue
            pt = win_pt("sell_close", w) if kind == "sell" else find_red_close(sct, w)
            if pt is None:
                continue
            click_at(pt, jx=1 if kind != "sell" else 6, jy=1 if kind != "sell" else 3)
            closed.append(title)
            time.sleep(random.uniform(0.4, 0.7))
    print(f"  [정리] 닫은 창: {', '.join(closed) if closed else '없음'}")
    am._scan_cache = None


def _skewed(lo, hi):
    """lo~hi 사이 랜덤 — 대부분 짧은 쪽, 가끔 긴 쪽 (사람이 쉬는 시간처럼)."""
    return random.triangular(lo, hi, lo + (hi - lo) * 0.25)


def _fmt(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}분 {s}초" if m else f"{s}초"


_rest = {}                      # 쉬는 시간 계산용 (다음 짧은 쉼까지 판수, 다음 긴 휴식 시각 등)


def _plan_rest(now=None):
    now = now or time.time()
    _rest["games"] = 0
    _rest["short_at"] = random.randint(*SHORT_EVERY)
    _rest.setdefault("since", now)
    _rest.setdefault("long_at", now + _skewed(*LONG_EVERY) * 60)


def rest_for(sec, why):
    """sec 초 동안 쉼. 가끔 마우스만 살짝 움직임 (클릭은 안 함). F8/F9 누르면 바로 끝."""
    print(f"[휴식] {why} — {_fmt(sec)} 쉼  (F8 = 바로 멈춤)")
    end = time.time() + sec
    nudge = time.time() + random.uniform(15, 60)
    while running and alive and time.time() < end:
        time.sleep(min(0.5, max(0.05, end - time.time())))
        if time.time() >= nudge and time.time() < end - 2:
            nudge = time.time() + random.uniform(20, 90)
            if random.random() < 0.5:        # 사람처럼 가끔 마우스만 조금 옮김
                mx, my = pyautogui.position()
                w = main_win()
                nx, ny = mx + random.randint(-150, 150), my + random.randint(-100, 100)
                if w is not None:
                    nx = min(max(nx, w.left + 20), w.left + w.width - 20)
                    ny = min(max(ny, w.top + 40), w.top + w.height - 20)
                am.smooth_move_to(nx, ny, random.uniform(0.3, 0.8), bow=10)
    if running and alive:
        print("  휴식 끝 → 계속")


def maybe_rest():
    """판 하나가 끝날 때마다 불림 — 멈칫 / 짧은 쉼 / 긴 휴식 중 해당하는 걸 함."""
    if not REST:
        return
    now = time.time()
    if "short_at" not in _rest:
        _plan_rest(now)
    _rest["games"] += 1
    if now >= _rest["long_at"]:
        played = (now - _rest["since"]) / 60
        rest_for(_skewed(*LONG_MINS) * 60, f"긴 휴식 (약 {played:.0f}분 돌았음)")
        _rest.pop("long_at", None)
        _rest["since"] = time.time()
        _plan_rest()
        return
    if _rest["games"] >= _rest["short_at"]:
        rest_for(_skewed(*SHORT_SECS), f"짧은 쉼 ({_rest['games']}판 만들었음)")
        _plan_rest()
        return
    if random.random() < PAUSE_CHANCE:
        rest_for(_skewed(*PAUSE_SECS), "잠깐 멈칫")


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
            am._scan_cache = None
            if not close_craft(sct):
                return -1
            have = material_cells(sct)
            out = [n for n, _ in RECIPE if have.get(n, 0) == 0]
            fails += 1
            if not out and fails < 2:
                # 재료는 보이는데 넣기만 실패 → 바로 끝내지 말고 한 번 더 (팔러 가면 체력만 씀)
                print(f"  재료를 다 못 넣음 (재료는 있음: {have}) → 제작 창 다시 열어서 한 번 더")
                continue
            short = out[0] if out else (plan[0] if plan else None)
            if short:
                _short.add(short)
            print(f"[만들기] 재료를 다 못 넣음 → {done}번 만들고 이번 바퀴 끝"
                  + (f" (모자란 것: {short} → 다음 바퀴에 한 무더기 더 주움)" if short else ""))
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
            maybe_rest()
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
    stuck = set()                           # 눌러도 안 줄던 칸 (다시 안 누름)
    for _ in range(3):                      # 먹고 나면 칸이 당겨질 수 있어서 다시 확인
        cells = grid("item")
        foods = [pos for pos, n in item_contents(sct) if n == FOOD and pos not in stuck]
        if not foods or cells is None:
            break
        pitch = max(cells[1][0] - cells[0][0], 20)
        for pos in foods:
            same = 0
            prev = am.grab_cell(sct, pos[0], pos[1])
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
                cur = am.grab_cell(sct, pos[0], pos[1])
                if np.abs(cur - prev).mean() < 1.5:
                    same += 1               # 더블클릭했는데 칸이 그대로 (개수 숫자도 안 바뀜)
                    if same >= 2:
                        eaten -= same
                        print("  [먹기] 눌러도 안 줄어듦 — 체력이 가득 찼거나 클릭이 안 먹음 → 이 칸은 그만")
                        stuck.add(pos)
                        break
                else:
                    same = 0
                prev = cur
                now = ident(sct, pos, names)
                if now == "" or (now is not None and now != FOOD):
                    break                   # 칸이 비었음 (또는 다른 물건으로 바뀜)
                # now 가 None(못 알아봄)이면: 먹은 직후 칸이 반짝이거나 선택 표시가 생겨서
                # 그림이 달라 보이는 것일 수 있음 → 비지 않았으면 계속 먹음
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


_bad_carts = []                 # 가만히 서서 눌러도 안 열리던 '가짜' 이름 자리 (다음 바퀴에도 기억)


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
            for tries in range(3):              # 클릭이 씹힐 수 있어서 최대 3번 누름
                am.direct_click(main_pt("ability_icon"), "능력")
                if wait_title("ability", True, 3):
                    break
                print(f"  능력 창이 안 열림 → 다시 누름 ({tries + 2}번째)")
            else:
                print("[문제] 능력 창이 3번 눌러도 안 열림 — 아래 메뉴 능력(별) 아이콘 위치 확인")
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
    cands = []
    for _ in range(6):
        _, mx, _, (x, y) = cv2.minMaxLoc(res)
        if mx < LABEL_SURE:
            break
        cx, cy = l + x + tw / 2, t + y + th / 2
        cands.append((int(cx), int(cy), float(mx)))
        res[max(0, y - th):y + th + 1, max(0, x - tw):x + tw + 1] = -1
    if not cands:
        return None
    # 여러 명이면 방금 보던 리어카맨(가장 가까운 것)을 계속 따라감
    return min(cands, key=lambda q: (q[0] - c[0]) ** 2 + (q[1] - c[1]) ** 2)


def chase_click(sct, cart, body, extra=(0, 0), limit=2.5, tol=6):
    """걸어 다니는 리어카맨을 따라가서 누름 → (누른 x, y, 리어카맨 위치) 또는 None(놓침).

    '방금 찍은 화면'에서 찾은 위치로만 누름 — 예전 위치로는 절대 안 누름.
    (예전 위치를 누르면 리어카맨은 이미 지나가고 바닥 재료가 눌려서 주워짐)
      1) 리어카맨 쪽으로 부드럽게 다가감
      2) 짧은 간격으로 계속 다시 찾으면서 커서를 몸통 위로 맞춤 (따라감)
      3) 방금 찾은 몸통(+ 누르는 순간까지 걸어갈 만큼) 위에 커서가 있으면 그때 누름
    """
    k = scale()
    p = locate_near(sct, cart, 250)
    if p is None:
        return None

    def target(q, vx, vy, ahead):
        bx, by = body(q)
        return int(bx + extra[0] + vx * ahead), int(by + extra[1] + vy * ahead)

    tx, ty = target(p, 0, 0, 0)
    am.smooth_move_to(tx, ty, random.uniform(0.18, 0.28), bow=6)
    last, lt = p, time.time()
    vx = vy = 0.0
    look = 0.03                               # 화면을 찍어서 찾는 데 걸리는 시간 (계속 잼)
    misses = 0
    t0 = time.time()
    while running and alive and time.time() - t0 < limit:
        ts = time.time()
        q = locate_near(sct, last, int((90 * k + 30) * (1 + misses)))   # 놓치면 더 넓게
        now = time.time()
        look = 0.7 * look + 0.3 * (now - ts)
        if q is None:                         # 잠깐 가려졌을 수 있음 → 조금 기다렸다 다시
            misses += 1
            if misses >= 6:
                return None
            time.sleep(0.03)
            continue
        misses = 0
        tq = (ts + now) / 2                   # 이 위치가 찍힌 시각
        dt = tq - lt
        # 지난번 속도로 예상한 자리와 실제 자리 차이 — 크면 방금 방향을 틀었거나 멈춘 것
        jerk = abs(last[0] + vx * dt - q[0]) + abs(last[1] + vy * dt - q[1])
        if dt > 0.005:
            nvx, nvy = (q[0] - last[0]) / dt, (q[1] - last[1]) / dt
            if (nvx * nvx + nvy * nvy) ** 0.5 > 900 * k:   # 다른 글자로 튀었으면 속도는 무시
                nvx = nvy = 0.0
            vx, vy = 0.5 * vx + 0.5 * nvx, 0.5 * vy + 0.5 * nvy
        last, lt = q, tq
        # 지금 누르면 누르는 순간 몸통이 있을 자리
        cx, cy = target(q, vx, vy, (now - tq) + 0.03)
        mx, my = pyautogui.position()
        if abs(mx - cx) <= tol and abs(my - cy) <= tol and jerk <= tol:
            pyautogui.mouseDown()
            time.sleep(random.uniform(0.04, 0.07))
            pyautogui.mouseUp()
            return mx, my, q
        # 다음에 다시 볼 때쯤 몸통이 있을 자리로 커서를 옮김
        d = random.uniform(0.03, 0.05)
        nx, ny = target(q, vx, vy, (now - tq) + d + look)
        am.smooth_move_to(nx, ny, d, bow=0)
    return None


_sell_target = None             # 이번에 몇 개 쌓이면 팔지 (팔 때마다 새로 뽑음)


def pick_sell_target():
    if isinstance(SELL_AT, (tuple, list)):
        return random.randint(int(SELL_AT[0]), int(SELL_AT[1]))
    return int(SELL_AT)


def sell_all(sct):
    """아까비깡을 먹고, 리어카맨에게 결혼반지를 전부 팜. 팔 게 없으면 바로 True."""
    got = [n for _, n in item_contents(sct)]
    n_sell = sum(1 for n in got if n in SELL)
    if n_sell == 0:
        return True
    free = got.count("")
    global _sell_target
    if _sell_target is None:
        _sell_target = pick_sell_target()
    # 반지가 이번 기준 개수 미만이고, 다음 한 바퀴 + 재료 줍기(무더기 4칸 정도) 자리가 남아 있으면
    # 아직 안 팜 → 소환 횟수(체력) 아낌
    if n_sell < _sell_target and free >= MAX_ROUNDS + 5:
        print(f"[팔기] 반지 {n_sell}개 (이번 팔기 기준 {_sell_target}개) · 빈 칸 {free}개 → 아직 안 팜")
        return True
    eat_all(sct)
    n_sell = sum(1 for _, n in item_contents(sct) if n in SELL)
    if n_sell == 0:
        return True
    print(f"[팔기] 팔 것 {n_sell}개")
    names = all_names()
    cart = summon_cart(sct)
    if cart is None:
        return False
    fails = 0
    summoned_new = False
    off = _layout["points"]["cart_body"]
    k = scale()

    def body(c):
        return int(c[0] + off["off_x"] * k), int(c[1] + off["off_y"] * k)

    # 몸통 주변을 조금씩 다르게 눌러봄 (가운데 → 조금 위 → 조금 아래). 몸통 크기에 맞춰 비율로
    dy = abs(off["off_y"]) * k
    spots = [(0, 0), (0, -int(0.18 * dy)), (int(0.1 * dy), int(0.18 * dy))]
    tol = max(5, int(0.12 * dy))              # 커서가 몸통에서 이만큼 안이면 누름
    clicks = []                               # 이번 리어카맨을 누른 자리 (안 움직이는지 보려고)
    opened = False
    for attempt in range(5):
        for sx, sy in spots:
            res = chase_click(sct, cart, body, (sx, sy), tol=tol)
            if res is None:
                # 놓침 → 화면 전체에서 다시 찾음 (방금 보던 곳에서 가까운 것)
                found = _far(find_sprite(sct, "cart_label", LABEL_SURE, binary=True), _bad_carts)
                if not found:
                    print("  리어카맨을 놓침 (화면에 안 보임)")
                    break
                cart = min(found, key=lambda c: (c[0] - cart[0]) ** 2 + (c[1] - cart[1]) ** 2)
                continue
            tx, ty, cart = res
            clicks.append(cart[:2])
            print(f"  리어카맨 클릭 → ({tx}, {ty})  (이름 일치 {cart[2]:.2f})")
            if wait_title("sell", True, 1.2):
                opened = True
                break
        if opened:
            break
        fails += 1
        print("  되팔기 창이 안 뜸 → 다시")
        if fails == 1 and clicks:
            save_cart_debug(sct, (tx, ty), cart)
        # 여러 번 눌렀는데 이름이 한 번도 안 움직였으면 걸어 다니는 리어카맨이 아님 (가짜 글자)
        still = len(clicks) >= 3 and max(abs(c[0] - clicks[0][0]) + abs(c[1] - clicks[0][1])
                                         for c in clicks) <= 4
        found = _far(find_sprite(sct, "cart_label", LABEL_SURE, binary=True), _bad_carts)
        lost = not found
        if (still or lost) and not summoned_new:
            if still:
                _bad_carts.append(clicks[0])
                print("  그 이름은 안 움직임 → 진짜 리어카맨이 아닌 것 같음 → 새로 소환")
            else:
                print("  리어카맨이 안 보임 → 새로 소환")
            summoned_new = True
            new = summon_cart(sct, bad=_bad_carts, reuse=False)
            if new is None:
                return False
            cart, clicks = new, []
            continue
        if not lost:
            cart = min(found, key=lambda c: (c[0] - cart[0]) ** 2 + (c[1] - cart[1]) ** 2)
    if not opened:
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
    _sell_target = pick_sell_target()       # 다음엔 몇 개에서 팔지 새로 뽑음
    print(f"  다음 팔기 기준: 반지 {_sell_target}개")
    return True


# ==================== 반복 ====================

def worker():
    global running, alive
    try:
        if not load():
            alive = False
            return
        print(f"준비 완료 — 그림: {', '.join(_sprites)}  /  F8 로 시작")
        cycle = zero = recover = 0
        with mss.mss() as sct:
            while alive:
                if not running:
                    time.sleep(0.15)
                    continue
                am.running = am.alive = True
                cycle += 1
                print(f"\n========== {cycle}바퀴째 ==========")
                problem = None
                n = 0
                if not sell_all(sct):
                    problem = "팔기"
                elif not pick_up(sct):
                    problem = "줍기"
                else:
                    n = craft_all(sct)
                    if n < 0:
                        problem = "만들기"
                if problem:
                    if not running:                 # F8 로 멈춘 것 — 실패 아님
                        continue
                    recover += 1
                    if recover > RECOVER_MAX:
                        running = False
                        recover = 0
                        print(f"⏸ {problem} 실패가 {RECOVER_MAX + 1}번 연속 — 멈춤. 화면 확인 후 F8")
                        continue
                    # 멈추지 않고: 조이톡 말고 게임 안에 뜬 창을 다 닫고 처음부터 다시
                    print(f"[복구] {problem} 실패 → 게임 창 정리하고 처음부터 다시 ({recover}/{RECOVER_MAX})")
                    close_game_windows(sct)
                    time.sleep(random.uniform(1.5, 2.5))
                    continue
                recover = 0
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
    if running:
        _rest.clear()                       # 직접 멈췄다 다시 켜면 쉬는 시간 계산도 새로 시작
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
