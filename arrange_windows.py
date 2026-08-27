# -*- coding: utf-8 -*-
"""
게임 창 자동 정렬 도구.

매번 마우스로 창들을 제자리에 맞추는 대신, 이 스크립트가 창들을
저장해둔 위치로 한 번에 옮겨줌.

■ 처음 한 번 (위치 기억시키기):
  1. 정렬하고 싶은 창을 켜고 마우스로 원하는 자리에 정확히 배치
  2. 실행:  py arrange_windows.py 저장
     → 지금 열려있는 창들의 위치가 window_layout.json 에 저장됨

  ※ 저장은 '덮어쓰기'가 아니라 '추가'라서, 나중에 다른 창을 켜고 다시
     저장해도 이전에 저장해둔 창 위치는 그대로 남아있음.
     예) 오늘 음식만들기만 켜고 저장 → 내일 가구만들기만 켜고 저장
         → 두 창의 위치가 모두 기억됨

■ 그 다음부터 (매일 쓸 때):
  창들을 켜놓고 실행:  py arrange_windows.py
  → 열려있는 창만 저장된 자리로 자동 이동

■ 저장된 위치 확인:
  py arrange_windows.py 목록

■ 특정 창 위치를 지우고 싶으면:
  py arrange_windows.py 삭제 가구만들기

※ 닫혀있는 창은 건너뜀 (예: 가구만들기 창을 안 켰으면 그냥 넘어감)
※ 컴퓨터마다 배치가 다르면 각 컴퓨터에서 '저장'을 한 번씩 하면 됨
   (window_layout.json은 컴퓨터마다 따로 생김)
"""

import os
import sys
import json

# 정렬 대상 창 제목. 게임에 창이 더 생기면 여기에 추가하면 됨.
TITLES = ["조이톡2", "아이템", "음식만들기", "가구만들기", "직업"]

LAYOUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "window_layout.json")


def norm(s):
    """제목 비교용 정규화 — 띄어쓰기 차이를 무시함.

    게임 창 제목이 '가구 만들기'(띄어쓰기 있음)일 수도 '가구만들기'일 수도
    있어서, 공백을 없애고 비교하면 어느 쪽이든 찾아짐.
    """
    return "".join(str(s).split())


def find_window(gw, title):
    """제목이 title과 같은 창을 찾음 (띄어쓰기 무시, 보이는 창 우선)."""
    t = norm(title)
    cands = [w for w in gw.getAllWindows() if norm(w.title) == t and w.width > 0]
    if not cands:
        return None
    visible = [w for w in cands if getattr(w, "visible", True)]
    return (visible or cands)[0]


def load_layout():
    if not os.path.exists(LAYOUT_FILE):
        return {}
    try:
        with open(LAYOUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[주의] 저장 파일을 읽지 못했습니다({e}). 새로 만듭니다.")
        return {}


def write_layout(layout):
    with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)


def save_layout(gw):
    layout = load_layout()          # 기존 저장분을 먼저 읽어서 '추가'로 저장
    before = dict(layout)
    for title in TITLES:
        w = find_window(gw, title)
        if w is None:
            if title in layout:
                x, y = layout[title]
                print(f"  [건너뜀] '{title}' 창이 안 열려있음 "
                      f"— 이전 저장값 ({x}, {y}) 유지")
            else:
                print(f"  [건너뜀] '{title}' 창을 못 찾음 (안 쓰는 창이면 정상)")
            continue
        layout[title] = [w.left, w.top]
        mark = "" if before.get(title) == [w.left, w.top] else "  ← 새로 저장"
        print(f"  '{title}' 위치: ({w.left}, {w.top}){mark}")

    if not layout:
        print("\n[실패] 저장할 창이 하나도 없습니다. 창들을 켜고 다시 실행하세요.")
        return
    write_layout(layout)
    print(f"\n저장 완료! → {LAYOUT_FILE}")
    print(f"기억 중인 창: {', '.join(layout)}")
    print("이제부터는 그냥 실행만 하면 창들이 이 자리로 이동합니다.")


def apply_layout(gw):
    layout = load_layout()
    if not layout:
        print("[안내] 저장된 위치가 없습니다. 먼저 창들을 원하는 자리에 배치한 뒤")
        print("       py arrange_windows.py 저장")
        print("       을 실행해서 위치를 기억시켜 주세요.")
        return
    moved = skipped = 0
    for title, (x, y) in layout.items():
        w = find_window(gw, title)
        if w is None:
            print(f"  [건너뜀] '{title}' 창이 안 열려있음")
            skipped += 1
            continue
        if (w.left, w.top) == (x, y):
            print(f"  '{title}' 이미 제자리 ({x}, {y})")
            continue
        old = (w.left, w.top)
        w.moveTo(x, y)
        print(f"  '{title}' 이동: {old} → ({x}, {y})")
        moved += 1
    print(f"\n완료! {moved}개 창을 옮겼습니다."
          + (f" (안 열린 창 {skipped}개는 건너뜀)" if skipped else ""))


def show_layout():
    layout = load_layout()
    if not layout:
        print("저장된 위치가 없습니다.")
        return
    print(f"저장 파일: {LAYOUT_FILE}\n")
    for title, (x, y) in layout.items():
        print(f"  {title:12s} → ({x}, {y})")


def delete_entry(name):
    layout = load_layout()
    hit = [k for k in layout if norm(k) == norm(name)]
    if not hit:
        print(f"'{name}' 은(는) 저장되어 있지 않습니다.")
        print(f"저장된 창: {', '.join(layout) if layout else '(없음)'}")
        return
    for k in hit:
        del layout[k]
        print(f"'{k}' 저장 위치를 지웠습니다.")
    write_layout(layout)


def main():
    try:
        import pygetwindow as gw
    except ImportError:
        print("[에러] pygetwindow가 설치되어 있지 않습니다.")
        print("       cmd에서:  py -m pip install pygetwindow")
        return

    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("저장", "save"):
        print("현재 창 위치를 저장합니다...\n")
        save_layout(gw)
    elif arg in ("목록", "list"):
        show_layout()
    elif arg in ("삭제", "delete"):
        if len(sys.argv) < 3:
            print("사용법:  py arrange_windows.py 삭제 <창이름>")
            print("예)      py arrange_windows.py 삭제 가구만들기")
            return
        delete_entry(sys.argv[2])
    else:
        print("저장된 위치로 창들을 이동합니다...\n")
        apply_layout(gw)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
