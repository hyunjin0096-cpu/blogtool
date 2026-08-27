#!/usr/bin/env python3
"""
네이버 블로그 자동화 파이프라인 - 초안 생성기

매일 GitHub Actions에서 실행되어:
1. 법학 / IT / 알바꿀팁 세 가지 주제에 대해 오늘의 세부 소재를 정하고
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
    "법학": [
        "전세사기 피해자가 알아야 할 법적 대응 절차",
        "직장 내 괴롭힘 신고, 어떤 증거가 필요한가",
        "층간소음 분쟁, 실제로 소송까지 가면 벌어지는 일",
        "온라인 명예훼손 고소 절차와 실제 처벌 수위",
        "임금 체불 당했을 때 노동청 신고 A to Z",
        "중고거래 사기, 형사고소와 민사소송의 차이",
        "이혼 시 재산분할 기준이 되는 법적 원칙",
        "계약서에 도장 찍기 전 반드시 확인해야 할 조항",
        "부당해고를 당했을 때 구제신청 절차",
        "SNS 저작권 침해, 어디까지가 불법인가",
    ],
    "IT": [
        "생성형 AI 실무 활용 사례와 한계",
        "개인정보 유출 사고 발생 시 대응 매뉴얼",
        "저사양 PC에서도 쓸 수 있는 무료 개발 도구 모음",
        "노코드 툴로 만드는 간단한 자동화 워크플로우",
        "클라우드 스토리지 서비스 비교 (보안 관점)",
        "피싱 메일 구별법과 실제 피해 사례",
        "재택근무자를 위한 협업 툴 세팅 가이드",
        "스마트폰 배터리 수명을 늘리는 실질적인 방법",
        "무료로 배우는 데이터 분석 입문 로드맵",
        "1인 개발자가 알아야 할 서버 비용 절감 팁",
    ],
    "알바꿀팁": [
        "최저임금 위반 사업장 신고하는 법",
        "주휴수당 계산법과 자주 하는 실수",
        "알바 면접에서 나오는 예상 질문과 답변 예시",
        "단기 알바 vs 장기 알바, 세금 처리 차이",
        "야간 알바 수당 정확히 계산하는 법",
        "알바 중 다쳤을 때 산재 처리 절차",
        "부당 해고당한 알바생을 위한 대응 매뉴얼",
        "알바 구할 때 조심해야 할 채용 사기 유형",
        "시급 높은 알바 vs 워라밸 좋은 알바 비교",
        "4대 보험 가입 대상 알바 기준 총정리",
    ],
}


def pick_subtopic(topic: str) -> str:
    """날짜를 시드로 써서 매일 다른(그러나 재현 가능한) 소재를 고른다."""
    pool = TOPIC_POOL[topic]
    seed = f"{TODAY}-{topic}"
    rng = random.Random(seed)
    return rng.choice(pool)


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
        "법률/금전 관련 내용은 '일반적인 정보 제공 목적'이며 "
        "구체적 사안은 전문가 상담이 필요하다는 점을 본문 말미에 자연스럽게 언급한다. "
        "반드시 아래 JSON 형식으로만 응답한다 (다른 텍스트, 마크다운 코드블록 금지):\n"
        '{"title": "...", "body": "...", "hashtags": ["...", "..."], "image_keywords": "..."}\n'
        "- title: 클릭을 유도하되 낚시성은 아닌 네이버 블로그 제목 (30자 내외)\n"
        "- body: 소제목을 포함한 800~1200자 분량의 본문 (줄바꿈은 \\n으로 표현)\n"
        "- hashtags: 5~8개의 해시태그 (# 기호 없이 단어만)\n"
        "- image_keywords: 이 글에 어울리는 이미지를 찾기 위한 영어 검색어 2~3단어"
    )

    user_prompt = f"주제 카테고리: {topic}\n오늘의 세부 소재: {subtopic}\n위 소재로 네이버 블로그 글 초안을 작성해줘."

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": 2000,
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
    # 혹시 모델이 코드블록으로 감싸서 응답한 경우 대비
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

    # 오늘 날짜 파일 저장
    day_path = os.path.join(DATA_DIR, f"{TODAY}.json")
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump({"date": TODAY, "posts": posts}, f, ensure_ascii=False, indent=2)

    # 인덱스(날짜 목록) 갱신
    dates = []
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            dates = json.load(f).get("dates", [])
    if TODAY not in dates:
        dates.append(TODAY)
    dates = sorted(dates, reverse=True)[:60]  # 최근 60일만 보관

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(posts)}개 글 생성 -> {day_path}")


if __name__ == "__main__":
    main()
