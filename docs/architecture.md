# 전체 구조와 API 서버

정리 기준: 2026-10-14. FastAPI API 서버, TypeScript/Vite 화면, SQLAlchemy 관계형 모델로 구성한다. 운영 DB는 PostgreSQL을 기준으로 한다.

```text
브라우저 화면
  → API 요청 + 쿠키
  → FastAPI: 입력·로그인·CSRF·소유권 검사
  → 서비스: 인증·로그인 상태 전환
  → SQLAlchemy 트랜잭션
  → PostgreSQL: 데이터·고유 제약·관계·잠금

API 서버 → Gmail SMTP: 이메일 발송
브라우저 → Google 로그인 → API 서버: ID 토큰 검증
```

화면에서 버튼을 숨기는 것만으로 권한을 보장하지 않는다. API가 요청자의 로그인 상태와 데이터 소유자를 확인한다. DB는 중복과 잘못된 관계를 마지막으로 차단한다.

## 파일 구조

```text
project1/
├─ README.md
├─ docs/                       주제별 현행 문서
├─ backend/
│  ├─ app/
│  │  ├─ main.py               앱 생성·미들웨어·라우터 등록
│  │  ├─ api/routes/           auth, google, members, diaries,
│  │  │                        tasks, community, config
│  │  ├─ api/serializers.py    응답 변환
│  │  ├─ core/                 설정·보안·개인정보 정책
│  │  ├─ services/             verification, tokens, google,
│  │  │                        mail, captcha, refresh
│  │  ├─ schemas/              영역별 요청 입력 모델
│  │  ├─ models/               영역별 DB 테이블·제약
│  │  ├─ db/                   연결·트랜잭션·제한·컬럼 보완
│  │  └─ maintenance.py        만료 데이터 정리
│  ├─ tests/                   API·인증 상태·PostgreSQL 검사
│  ├─ scripts/                 연결 확인·설정 보조
│  ├─ sql/                     초기 SQL·후속 변경·정리 예약
│  ├─ setup_supabase.py
│  └─ migrate_to_supabase.py
└─ frontend/src/
   ├─ main.ts                   초기 실행
   ├─ app/                      화면 전환·상태·스타일
   ├─ pages/                    auth, profile, calendar, community
   └─ shared/                   API 호출·공통 유틸리티·타입
```

## 요청 처리와 책임

| 영역 | 서버가 담당하는 핵심 규칙 |
|---|---|
| 인증 | 캡차, 이메일 발송·검증, 가입, 로그인, 재발급, 로그아웃 |
| Google | ID 토큰 검증, 신규 가입과 기존 계정 연결 구분 |
| 회원 | 본인 정보 조회·변경과 필요한 재인증 |
| 일기 | 회원·날짜별 저장, 초안/등록/공유, 버전 충돌 검사 |
| 할 일 | 반복 설정과 날짜별 완료 상태의 분리·소유권 검사 |
| 커뮤니티 | 공개 일기만 노출, 댓글 작성자와 삭제 권한 확인 |

구체적인 경로·입력 스키마는 실행 중인 API의 `/docs`와 [라우터 코드](../backend/app/api/routes/)를 기준으로 한다.

## 실패와 동시 요청

[db_session](../backend/app/db/session.py)은 정상 처리 후 커밋하고 예외 발생 시 롤백한다. 가입에서는 회원 저장과 인증 소비가 같이 성공해야 한다. 동일 인증을 동시에 사용하면 행 잠금으로 순서를 정하고 잠금 이후 상태를 다시 검사한다. 이메일 고유 제약은 서로 다른 인증으로 같은 이메일에 가입하는 경쟁도 차단한다.

일기에는 `version`을 두어 오래된 화면이 최신 저장 내용을 덮어쓰지 않도록 한다. 관계를 가진 데이터는 외래키로 연결하되 접근 권한은 API에서 별도로 검사한다.

SMTP 발송과 DB 저장은 하나의 트랜잭션으로 묶이지 않는다. 메일을 보냈지만 저장이 실패하는 경우까지 해결하려면 발송 작업 저장·재시도 구조가 필요하다. 현재 구현과 후속 개선을 구분한다.

관련 문서: [인증](authentication.md), [DB](database.md), [설계 결정](decisions.md).

## 수정할 기능별 출발점

| 수정 대상 | 파일 |
|---|---|
| 가입·이메일 인증의 요청 흐름 | `backend/app/api/routes/auth.py` |
| 토큰 회전과 직전 토큰 재시도 | `backend/app/services/refresh.py` |
| 입력 조건과 DB 제약 | `backend/app/schemas/`, `backend/app/models/` |
| 가입 화면 HTML | `frontend/src/pages/auth/templates.ts` |
| 가입 버튼·Google 인증 동작 | `frontend/src/pages/auth/index.ts` |
| 회원정보 화면 HTML / 동작 | `frontend/src/pages/profile/templates.ts` / `index.ts` |
| 공통 통신과 재발급 요청 합치기 | `frontend/src/shared/api/client.ts` |

`templates.ts`는 HTML을 만들고, `index.ts`는 화면에 넣은 뒤 이벤트를 연결한다. 현재 템플릿은 앱 상태를 읽지만 상태 변경이나 API 요청은 수행하지 않는다. 모든 작은 화면에 파일을 추가하지 않고 길고 복잡한 가입·회원정보 화면부터 분리했다.

재발급 서비스는 로그인 기록과 발급할 토큰 값을 반환한다. API 라우터가 요청 쿠키를 읽고 CSRF 검증을 전달하며 응답 쿠키를 설정한다. 서비스에서 별도로 정상 커밋하지 않아 요청 트랜잭션의 경계를 유지한다.

### 오류여도 저장해야 하는 기록

`db/controls.py`의 `fail()`은 실패 횟수와 재사용 차단 기록을 커밋한 뒤 오류를 반환한다. 일반 예외로 바꾸면 차단 기록도 롤백될 수 있다. 반대로 회원 생성과 인증 소비는 실패 시 함께 롤백해야 한다. 두 경로의 차이를 유지한다.

이메일 발송과 토큰 교체·로그아웃 경쟁 처리에는 코드 주석으로 이유를 남겼다. 재발급 유예와 세션 테이블은 제거했으며 현재 정책은 인증 문서를 따른다.
