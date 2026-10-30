# -*- coding: utf-8 -*-
"""
의장이 사이클(sew_cycle.py) 준비 도구 — 마결자동의 measure_ring.py 를 그대로 쓰고,
바닥 무더기 그림만 sew_cycle.py 의 PILES 에 적은 재료로 바꿔서 잼.

결과: ring_layout.json + ring_sprites 폴더 (이 폴더 안)

■ 제일 쉬운 방법 (마결자동을 쓰던 컴퓨터)
  1. 마결자동 폴더의 ring_layout.json 과 ring_sprites 폴더를 이 폴더로 복사
     (아래 메뉴 아이콘 / 아이템 창 / 능력 창 / 리어카맨 / 되팔기 창은 같은 게임 화면이라 그대로 씀)
  2. sew_cycle.py 맨 위 PILES 에 바닥에서 주울 재료 이름 적기
  3. 바닥에 그 재료 무더기를 떨어뜨려 두고, 제작 창을 띄운 채로:  py measure_cycle.py
  4. "다시 잴 번호" 에서 4 (바닥 무더기 그림) 만 → 재료마다 왼쪽 위/오른쪽 아래 F1 두 번
■ ring_layout.json 이 없으면 처음부터 전부 잼 (마결자동 measure_ring.py 와 같은 순서)
  F1 = 기록 / F2 = 방금 것 다시 / ESC = 그만두기
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import measure_ring as mr       # 마결자동 측정 도구 (그대로)


def read_piles():
    """sew_cycle.py 의 PILES 에 적은 재료 이름 (sew_cycle 을 통째로 불러오지 않고 그 줄만 읽음)."""
    import ast
    with open(os.path.join(HERE, "sew_cycle.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PILES" for t in node.targets):
            return list(ast.literal_eval(node.value))
    return []


def setup_steps(names):
    """measure_ring 의 바닥 그림 단계(석분/철괴/상급키트)를 이 재료들로 바꿈."""
    old = mr.STEPS
    spr = [i for i, s in enumerate(old) if s[0].startswith("spr_")]
    first, last = spr[0], spr[-1]
    new_spr = [("spr_" + n, "box", f"바닥의 {n} 무더기 하나 (안 가려진 것)") for n in names]
    shift = len(new_spr) - len(spr)
    steps = old[:first] + new_spr + old[last + 1:]
    groups = []
    for label, idx, wins in mr.GROUPS:
        if any(old[i][0].startswith("spr_") for i in idx):
            idx = [i for i in idx if not old[i][0].startswith("spr_")] + list(range(first, first + len(new_spr)))
            label = f"바닥 무더기 그림 ({'/'.join(names)})"
        else:
            idx = [i if i < first else i + shift for i in idx]
        groups.append((label, idx, wins))
    mr.STEPS, mr.GROUPS = steps, groups


def main():
    names = read_piles()
    if not names or any(n.startswith("재료") for n in names):
        print("[중단] sew_cycle.py 맨 위 PILES 에 바닥에서 주울 재료 이름을 먼저 적어주세요")
        print("       예)  PILES = {\"실\": 1, \"천조각\": 1}   (이름은 items 폴더 그림 이름과 똑같이)")
        return
    print("의장이 사이클 준비 — 바닥 무더기 그림을 잴 재료:", ", ".join(names))
    setup_steps(names)
    mr.main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n\n[에러 발생] 아래 내용을 복사해서 알려주세요:\n")
        traceback.print_exc()
    input("\n엔터를 누르면 창이 닫힙니다...")
