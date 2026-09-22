#!/usr/bin/env python3
"""
네이버 블로그 자동화 파이프라인 - 초안 생성기

매일 GitHub Actions에서 실행되어:
1. AI / 피부홈케어방법 / 요리레시피 세 가지 주제에 대해 오늘의 세부 소재를 정하고
2. Claude API로 네이버 블로그용 초안(제목+본문+해시태그)을 생성하고
3. Unsplash에서 주제에 맞는 무료 이미지를 찾아 매칭한 뒤
4. docs/data/ 아래 JSON 파일로 저장한다 (대시보드가 이 파일을 읽어서 보여줌)

필요한 환경변수(= GitHub Secrets):
  - ANTHROPIC_API_KEY   (필수)
  - UNSPLASH_ACCESS_KEY (선택, 없으면 이미지 없이 진행)

모델은 비용 절감을 위해 기본값을 Haiku로 설정. 품질을 더 높이고 싶으면
CLAUDE_MODEL 환경변수로 다른 모델(sonnet 계열)을 지정하면 된다.
"""

import json
import os
import random
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# 한국 시간 기준 오늘 날짜 사용 (서버는 보통 UTC라서 KST로 보정)
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

DATA_DIR = os.path.join(os.path.dirname(__file__), "docs", "data")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")

# 주제별 세부 소재 후보 풀. 매일 이 안에서 무작위로 하나씩 골라서
# 같은 얘기만 반복되지 않게 한다. 필요하면 자유롭게 항목을 추가/수정해서 쓰면 된다.
TOPIC_POOL = {
    "AI": [
        "생성형 AI 최신 트렌드와 실무 활용법",
        "트랜스포머 구조 쉽게 이해하기: 어텐션 메커니즘이란",
        "딥러닝 모델 경량화 기법: 양자화와 프루닝 쉽게 이해하기",
        "AI 할루시네이션은 왜 생길까, 완화 기법 총정리",
        "오픈소스 LLM vs 폐쇄형 모델, 무엇이 다른가",
        "파인튜닝 vs RAG, 언제 무엇을 써야 하나",
        "AI 저작권 소송 이슈 총정리 (알아둬야 할 것)",
        "딥페이크와 AI 윤리, 최근 규제 동향",
        "강화학습으로 이해하는 알파고·게임 AI 원리",
        "AI 모델 학습에 드는 GPU 비용, 왜 이렇게 비쌀까",
        "CNN vs Transformer, 이미지 인식 기술은 왜 달라졌나",
        "최근 화제가 된 AI 서비스 이슈 총정리",
    ],
    "피부홈케어방법": [
        "피부 타입별(건성·지성·복합성) 스킨케어 루틴 총정리",
        "환절기 피부 트러블 원인과 홈케어 방법",
        "저자극 성분 vs 고기능성 성분, 내 피부에 맞는 선택법",
        "홈 필링(각질 관리) 제대로 하는 법과 주의사항",
        "피부 진정에 좋은 홈케어 팩 만드는 법",
        "스킨케어 바르는 순서, 제대로 알고 쓰기",
        "다크서클·눈가 주름 홈케어 관리 방법",
        "여드름 피부를 위한 홈케어 스킨케어 루틴",
        "자외선 차단제 제대로 고르고 바르는 법",
        "피부 보습력을 높이는 생활 습관 및 홈케어 팁",
        "화장품 성분표 읽는 법, 똑똑하게 확인하기",
    ],
    "요리레시피": [
        "집에서 만드는 초간단 파스타 레시피",
        "다이어트에 좋은 저칼로리 집밥 레시피",
        "자취생을 위한 5분 완성 초간단 요리",
        "에어프라이어로 만드는 인기 요리 레시피",
        "손님 초대 요리 추천 레시피 (집들이 메뉴)",
        "제철 재료로 만드는 계절 요리 레시피",
        "일주일 밑반찬 준비 꿀팁 및 레시피",
        "초보자를 위한 기본 국물 요리 레시피 (국·찌개)",
        "간단 디저트·베이킹 레시피 모음",
        "혼밥러를 위한 원팬 요리 레시피",
        "야식으로 좋은 간단 안주 레시피",
    ],
}


def pick_subtopic(topic: str) -> str:
    """매 실행마다 완전 무작위로 소재를 고른다 (같은 날 여러 번 돌려도 매번 다르게 나옴)."""
    pool = TOPIC_POOL[topic]
    return random.choice(pool)


# ---------------------------------------------------------------------------
# Claude API 호출
# ---------------------------------------------------------------------------

def call_claude(topic: str, subtopic: str) -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    system_prompt = (
        "너는 네이버 블로그에 최적화된 글을 쓰는 한국어 블로그 작가다. "
        "네이버 검색 상위 노출을 고려해서 소제목(##)을 활용하고, "
        "문단은 짧게, 실용적인 정보 위주로 쓴다. "
        "과장된 광고성 표현이나 근거 없는 단정은 피하고, "
        "건강/피부/의학 관련 내용은 '일반적인 정보 제공 목적'이며, 정확한 정보인지 두 번 확인한다. "
        "구체적 사안은 전문가 상담이 필요하다는 점을 본문 말미에 자연스럽게 언급한다. "
        "반드시 아래 JSON 형식으로만 응답한다 (다른 텍스트, 마크다운 코드블록 금지):\n"
        '{"title": "...", "body": "...", "hashtags": ["...", "..."], "image_keywords": "..."}\n'
        "- title: 클릭을 유도하되 낚시성은 아닌 네이버 블로그 제목 (30자 내외)\n"
        "- body: 소제목을 포함해 최소 1000자 이상, 1500자 내외 분량의 본문 (줄바꿈은 \\n으로 표현). 1000자보다 짧으면 안 된다.\n"
        "- hashtags: 5~8개의 해시태그 (# 기호 없이 단어만)\n"
        "- image_keywords: 이 글에 어울리는 이미지를 찾기 위한 영어 검색어 2~3단어"
    )

    user_prompt = f"주제 카테고리: {topic}\n오늘의 세부 소재: {subtopic}\n위 소재로 네이버 블로그 글 초안을 작성해줘."

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 3000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    text = "".join(block.get("text", "") for block in result.get("content", []))
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# Unsplash 이미지 검색
# ---------------------------------------------------------------------------

def find_image(keywords: str) -> dict:
    if not UNSPLASH_ACCESS_KEY:
        return {"url": "", "credit": ""}

    import urllib.parse as up
    query = up.quote(keywords)

    url = f"https://api.unsplash.com/search/photos?query={query}&per_page=1&orientation=landscape"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        if not results:
            return {"url": "", "credit": ""}
        photo = results[0]
        return {
            "url": photo["urls"]["regular"],
            "credit": f'Photo by {photo["user"]["name"]} on Unsplash',
        }
    except urllib.error.URLError:
        return {"url": "", "credit": ""}


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    posts = []
    for topic in TOPIC_POOL.keys():
        subtopic = pick_subtopic(topic)
        print(f"[{topic}] 소재: {subtopic} - 생성 중...")
        try:
            draft = call_claude(topic, subtopic)
        except Exception as e:
            print(f"  경고: {topic} 생성 실패 - {e}", file=sys.stderr)
            continue

        image = find_image(draft.get("image_keywords", subtopic))

        posts.append({
            "topic": topic,
            "subtopic": subtopic,
            "title": draft.get("title", ""),
            "body": draft.get("body", ""),
            "hashtags": draft.get("hashtags", []),
            "image_url": image["url"],
            "image_credit": image["credit"],
        })

    if not posts:
        print("생성된 글이 없습니다. API 키를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    day_path = os.path.join(DATA_DIR, f"{TODAY}.json")
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump({"date": TODAY, "posts": posts}, f, ensure_ascii=False, indent=2)

    dates = []
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            dates = json.load(f).get("dates", [])
    if TODAY not in dates:
        dates.append(TODAY)
    dates = sorted(dates, reverse=True)[:60]

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(posts)}개 글 생성 -> {day_path}")


if __name__ == "__main__":
    main()
