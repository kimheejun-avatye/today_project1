"""A versioned development draft, not a finalized operating/privacy policy."""

from fastapi import HTTPException

NOTICE = {
    "version": "2026-10-13-dev-2",
    "title": "개인정보 수집·이용 안내 (개발용 초안)",
    "items": [
        "수집 항목: 이름, 닉네임, 이메일. 일반 가입은 비밀번호 해시, Google 가입은 Google 계정 고유번호도 저장합니다.",
        "목적: 가입·로그인과 프로필 관리. 이름은 내부 회원정보로만 보관하고 공개 일기·댓글에는 닉네임을 표시합니다. 입력 이름은 실명 인증을 의미하지 않습니다.",
        "보유: 개발 테스트 종료 후 수동 삭제 예정입니다. 실제 운영의 보유기간·탈퇴·삭제 정책은 아직 확정되지 않았습니다.",
        "동의를 거부할 수 있으나 이 개발 버전에서는 위 항목에 동의해야 가입할 수 있습니다. 실제 개인정보 대신 테스트 정보를 사용해주세요.",
    ],
    "draft": True,
}


def validate_consent(accepted, version):
    if not accepted:
        raise HTTPException(400, "개인정보 수집·이용 안내에 동의해주세요.")
    if version != NOTICE["version"]:
        raise HTTPException(
            409, "개인정보 안내가 변경되었습니다. 새로고침 후 다시 확인해주세요."
        )
