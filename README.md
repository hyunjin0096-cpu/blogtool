# 네이버 블로그 초안 자동화 (법학 / IT / 알바꿀팁)

매일 자동으로 3개 주제의 블로그 초안(제목+본문+해시태그+이미지)을 생성하고,
웹 대시보드에서 확인 → 복사 → 네이버 블로그에 붙여넣기만 하면 되는 시스템입니다.

> ⚠️ 네이버 블로그는 글 발행을 위한 공식 API가 없어서, 발행 자체는 자동화하지 않습니다.
> (자동 로그인/자동 발행은 네이버 약관 위반 소지 + 계정 정지 위험이 있어 포함하지 않았습니다.)
> 대신 "발행 직전까지"는 완전 자동화하고, 마지막 붙여넣기+발행만 사람이 합니다 (약 1분).

---

## 1. 필요한 것

- GitHub 계정 (무료)
- Anthropic API 키 ( https://console.anthropic.com 에서 발급 )
- (선택) Unsplash API 키 ( https://unsplash.com/developers 에서 무료 발급 — 없으면 이미지 없이 텍스트만 생성됩니다)

## 2. 설치 순서

### ① 이 폴더를 GitHub 저장소로 만들기
1. GitHub에서 새 저장소(Public 권장 — Actions가 완전 무료)를 만듭니다.
2. 이 폴더 전체를 그 저장소에 업로드(푸시)합니다.

```bash
cd naver-blog-automation
git init
git add .
git commit -m "초기 세팅"
git branch -M main
git remote add origin https://github.com/<내계정>/<저장소이름>.git
git push -u origin main
```

### ② API 키 등록 (Secrets)
저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | 발급받은 Anthropic API 키 (필수) |
| `UNSPLASH_ACCESS_KEY` | 발급받은 Unsplash Access Key (선택) |

### ③ GitHub Pages 활성화 (대시보드 보기용)
저장소 → **Settings → Pages**
- Source: `Deploy from a branch`
- Branch: `main` / 폴더: `/docs` 선택 → Save

몇 분 후 `https://<내계정>.github.io/<저장소이름>/` 주소로 대시보드가 열립니다.

### ④ 자동 실행 확인
- 기본 설정은 **매일 한국시간 오전 7시**에 자동 실행됩니다. (`.github/workflows/daily.yml`에서 시간 수정 가능)
- 지금 바로 테스트하고 싶다면: 저장소 → **Actions** 탭 → `매일 블로그 초안 자동 생성` → **Run workflow** 클릭

## 3. 매일 사용하는 법

1. 대시보드 주소 접속 (즐겨찾기 해두면 편함)
2. 법학 / IT / 알바꿀팁 탭 클릭해서 원하는 글 확인
3. "제목+본문 복사하기" 클릭
4. 네이버 블로그 글쓰기 화면에 붙여넣기
5. 이미지가 있으면 대시보드에 뜬 이미지를 저장해서 함께 첨부 (Unsplash 이미지는 출처 표기 문구도 같이 복사해서 본문 하단에 넣어주면 좋습니다)
6. 최종 검토 후 발행

## 4. 커스터마이징

- **소재 풀 수정**: `generate_posts.py` 안의 `TOPIC_POOL` 딕셔너리에 원하는 세부 주제를 자유롭게 추가/수정
- **글 톤/분량 조정**: `call_claude()` 함수 안의 `system_prompt` 수정
- **모델 변경**: 품질을 더 높이고 싶다면 Secrets에 `CLAUDE_MODEL` 값을 `claude-sonnet-5` 등으로 추가 (기본값은 비용이 가장 저렴한 Haiku)
- **실행 시간 변경**: `.github/workflows/daily.yml`의 `cron` 값 수정 (UTC 기준, KST는 UTC+9)

## 5. 예상 비용

- GitHub Actions, GitHub Pages, Unsplash API: **무료**
- Anthropic API: 하루 3개(법학/IT/알바꿀팁 각 1개, 800~1200자) 기준 Haiku 모델 사용 시 한 달 합계로도 매우 저렴한 수준 (커피 한두 잔 값 이내)

## 6. 주의사항

- 법률/금전 관련 정보는 반드시 발행 전에 사실관계를 한 번 더 확인하세요. AI가 생성한 초안은 참고용입니다.
- 이미지에 Unsplash 출처 표기를 포함하는 것을 권장합니다 (라이선스상 필수는 아니지만 매너입니다).
