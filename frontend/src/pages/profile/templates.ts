// HTML 구성만 담당합니다. 이벤트 등록과 API 요청은 index.ts에서 처리합니다.
import { state } from "../../app/state";
import { field, button, escape } from "../../shared/lib/dom";

export function profileHtml() {
  return /* HTML */ `<section class="page-heading"><h1>나의 정보</h1></section>
    <div class="card profile">
      ${field("profile-name", "이름", "text", state.user!.name)}${field("profile-nickname", "닉네임", "text", state.user!.nickname || "")}${button("정보 저장", "profile-save")}
      <hr />
      <p>현재 이메일: ${escape(state.user!.email)}</p>
      ${!state.user!.google_only ? `${field("new-email", "변경할 이메일", "email")}<div id="captcha"></div>${button("인증번호 보내기", "email-send", true)}<p id="email-status" class="hint"></p>${field("email-code", "인증번호")}${button("인증 후 이메일 변경", "email-change")}` : '<p class="hint">Google 전용 계정의 이메일은 변경할 수 없습니다.</p>'}
      <hr />
      <button id="password-reset" class="secondary">비밀번호 재설정</button>
      <p class="hint">재설정 완료 시 기존 로그인이 종료됩니다.</p>
      ${state.config.google_client_id && !state.user!.google_only && !state.user!.google_linked ? '<hr><h3>Google 연결</h3><p class="hint">현재 비밀번호를 확인하고 Google 계정을 연결합니다.</p><div id="link-google"></div>' : ""}
    </div>`;
}
