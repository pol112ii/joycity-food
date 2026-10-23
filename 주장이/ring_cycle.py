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
    return [(int(round(a[0] + col * px)), int(round(a[1] + row * py)))
            for row in range(5) for col in range(6)]


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


def find_sprite(sct, key, sure, binary=False):
    """메인 창에서 그림(key)을 찾아 [(중심x, 중심y, 점수), ...] (점수 높은 순)."""
    w = main_win()
    if w is None:
        return []
    img = shot_bgr(sct, w.left, w.top, w.width, w.height)
    tpl = _sprites[key]
    k = scale()
    if abs(k - 1) > 0.03:
        tpl = cv2.resize(tpl, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    if binary:
        # 이름 글자: 밝은 글자 픽셀만 비교 (뒤 배경이 달라도 글자 모양으로 찾음)
        img = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
        tpl = (cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) > 200).astype(np.float32)
    th, tw = tpl.shape[:2]
    if th >= img.shape[0] or tw >= img.shape[1]:
        return []
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    rects = other_windows()
    out = []
    while len(out) < 40:
        _, mx, _, (x, y) = cv2.minMaxLoc(res)
        if mx < sure:
            break
        cx, cy = w.left + x + tw / 2, w.top + y + th / 2
        if not any(a <= cx < c and b <= cy < d for a, b, c, d in rects):
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


def pick_up(sct):
    """바닥에서 모자란 무더기를 주움. 다 주웠으면 True."""
    have = material_cells(sct)
    print(f"[줍기] 지금 인벤토리: {have} / 필요: {PILES}")
    for name, piles in PILES.items():
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
        if not am.fill_slots(sct, tpl):
            have = material_cells(sct)
            if any(have.get(n, 0) == 0 for n, _ in RECIPE):
                print(f"[만들기] 재료가 떨어짐 → {done}번 만들고 끝 (남은 칸: {have})")
                return done
            fails += 1
            if fails >= 3:
                print("[중단] 재료는 있는데 넣기가 계속 실패함")
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


def summon_cart(sct):
    """능력 → 고물소환 → 능력 창 닫기 → 리어카맨이 나타나면 위치 반환.

    고물소환은 누를 때마다 한 명씩 생기므로 한 번만 누르고, 리어카맨이 한참
    안 보일 때만(클릭이 씹혔을 때) 한 번 더 시도함.
    """
    old = find_sprite(sct, "cart_label", LABEL_SURE, binary=True)
    if old:
        return old[0]                       # 이미 소환된 리어카맨이 있음
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
            found = find_sprite(sct, "cart_label", LABEL_SURE, binary=True)
            if found:
                return found[0]
            time.sleep(0.5)
        if attempt == 0:
            print(f"  고물소환 후 {CART_WAIT}초 동안 리어카맨이 안 보임 → 한 번 더 소환")
    print("[문제] 리어카맨이 안 나타남 (체력 부족이거나 이름 글자 그림이 안 맞음)")
    return None


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
    off = _layout["points"]["cart_body"]
    k = scale()

    def body(c):
        return int(c[0] + off["off_x"] * k), int(c[1] + off["off_y"] * k)

    for attempt in range(5):
        # 리어카맨은 계속 걸어 다님 → 다가간 뒤 한 번 더 찾아서 그 자리를 누름
        tx, ty = body(cart)
        am.smooth_move_to(tx, ty, random.uniform(0.25, 0.4) * am.MOUSE_SPEED, bow=8)
        again = find_sprite(sct, "cart_label", LABEL_SURE, binary=True)
        if again:
            cart = min(again, key=lambda c: (c[0] - cart[0]) ** 2 + (c[1] - cart[1]) ** 2)
            tx, ty = body(cart)
            am.smooth_move_to(tx, ty, random.uniform(0.05, 0.1), bow=0)
        time.sleep(random.uniform(0.05, 0.1))
        pyautogui.mouseDown()
        time.sleep(random.uniform(0.05, 0.1))
        pyautogui.mouseUp()
        print(f"  리어카맨 클릭 → ({tx}, {ty})")
        if wait_title("sell", True, 3):
            break
        print("  되팔기 창이 안 뜸 → 다시")
        again = find_sprite(sct, "cart_label", LABEL_SURE, binary=True)
        if again:
            cart = again[0]
    else:
        print("[문제] 리어카맨을 눌러도 되팔기 창이 안 뜸")
        return False
    time.sleep(random.uniform(0.5, 0.8))
    cells = grid("sell")
    clicked = 0
    for pos in cells:
        if not (running and alive):
            return False
        if ident(sct, pos, names) in SELL:
            click_at(pos, jx=4, jy=4)
            clicked += 1
            time.sleep(random.uniform(0.25, 0.45))
    if clicked == 0:
        # 아이템 창엔 반지가 있는데 되팔기 창에서 못 알아봄 → 계속 소환하면 체력만 닳으니 멈춤
        print("[문제] 되팔기 창에서 결혼반지를 못 알아봄 — 칸 위치(measure_ring.py)를 확인하세요")
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
        cycle = 0
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
