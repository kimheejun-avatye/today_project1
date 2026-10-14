# 하루

오늘 할 일, 매일 할 일, 감정과 이슈를 기록하고 선택한 일기를 공유하는 개인 일기 서비스다.

## 실행

프로젝트 루트 `project1`에서 터미널 두 개로 실행한다. 기존 `.env`의 비밀값은 문서·저장소에 복사하지 않는다.

API 서버:

```sh
cd backend
python3 -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt
# 최초 설정 때만 .env.example을 참고해 .env를 작성한다.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

프런트엔드:

```sh
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`에 접속한다. 환경에 맞는 프런트엔드 Origin을 API 설정과 일치시킨다. `DATABASE_URL` 미설정 시 코드의 기본값은 SQLite다. 운영 환경은 PostgreSQL과 실제 SMTP 설정을 요구한다. Supabase 전환 이력은 현재 연결 확인과 구분한다.

## 문서

| 문서 | 읽을 때 |
|---|---|
| [전체 구조](docs/architecture.md) | API 책임, 코드 위치, 요청 처리 흐름 |
| [인증 정책](docs/authentication.md) | 이메일 인증, 가입, 로그인, Google, 토큰 |
| [DB 설계](docs/database.md) | 10개 테이블의 모든 컬럼·관계·제약 |
| [설계 결정](docs/decisions.md) | 왜 선택했는지, 다른 대안과 한계 |
| [고민과 설계 과정 원본](docs/history/README.md) | 질문·대안 비교·결정 변경을 담은 원본 5개 |
| [운영 안내](docs/operations.md) | Gmail·Google·Supabase 설정 및 전환 |
| [검증 기록](docs/verification.md) | 과거 확인 범위와 남은 검증 |

구현과 문서가 다르면 현재 코드를 확인하고 해당 주제 문서 한 곳을 수정한다. 새 ‘최종 계획서’를 추가해 중복 관리하지 않는다. 문서 정리 전 원본은 [보관 ZIP](../.archive/docs-before-20261014.zip)에 있다.

## 처음 코드를 읽는 순서

1. `backend/app/main.py`: 앱 시작과 API 등록을 확인한다.
2. `backend/app/api/routes/auth.py`: 가입 요청의 흐름을 읽고, `schemas/auth.py`와 `models/auth.py`에서 입력과 저장 구조를 확인한다.
3. `backend/app/services/refresh.py`: 토큰 회전과 재사용 차단을 확인한다.
4. `frontend/src/main.ts` → `app/application.ts` → `pages/`: 초기 실행, 화면 전환, 기능별 동작 순서로 읽는다.

가입·회원정보 화면의 HTML은 각 폴더의 `templates.ts`, 이벤트와 API 호출은 `index.ts`에 있다. 자세한 책임 구분은 [전체 구조](docs/architecture.md)를 참고한다.

## 문서 정리 원칙

- 정리 대상은 의미 없는 중복 설명이며, 고민과 의사결정 과정은 보존한다.
- 질문한 이유, 비교한 대안, 선택의 장단점, 바로잡은 오해, 결정 변경 과정은 요약본으로 대체하거나 삭제하지 않는다.
- 현재 구현은 주제별 문서에서 설명하고, 당시의 고민과 계획은 [설계 과정 원본](docs/history/README.md)에서 구분해 관리한다.
- 오래된 결정은 당시 기록임을 표시하고 최신 설명으로 연결한다. 단순히 현재 구현과 다르다는 이유로 삭제하지 않는다.
