// HTML 구성만 담당합니다. 이벤트 등록과 API 요청은 index.ts에서 처리합니다.
import { state } from "../../app/state";
import { field, button, escape } from "../../shared/lib/dom";

export function authFormHtml() {
  return /* HTML */ `${field("email", "이메일", "email")}${field("password", "비밀번호", "password")}
    <p class="hint">비밀번호는 12자 이상으로 설정합니다.</p>
    ${button("로그인", "login-submit")}
    <div class="auth-links">
      <button id="signup-link" class="quiet">회원가입</button
      ><button id="reset-link" class="quiet">비밀번호 재설정</button>
    </div>`;
}

export function privacyHtml() {
  return /* HTML */ `<section class="privacy-section">
    <details>
      <summary>${escape(state.config.privacy_notice.title)}</summary>
      ${state.config.privacy_notice.items.map((item) => `<p>${escape(item)}</p>`).join("")}
      <p class="hint">
        안내 버전: ${escape(state.config.privacy_notice.version)}
      </p>
    </details>
    <label class="consent"
      ><input id="privacy-consent" type="checkbox" />[필수] 위 개인정보
      수집·이용 안내를 읽고 동의합니다.</label
    >
  </section>`;
}

export function profileFields(name = "") {
  return field("name", "이름", "text", name) + field("nickname", "닉네임");
}

export function googleEntryHtml() {
  if (
    !state.config.google_client_id ||
    (state.authMode !== "login" && state.authMode !== "signup")
  )
    return "";
  const signup = state.authMode === "signup";
  return /* HTML */ `<section
      id="google-auth"
      class="google-auth"
      aria-label="${signup ? "Google로 회원가입하기" : "Google로 로그인하기"}"
    >
      <h3>${signup ? "Google로 회원가입하기" : "간편 로그인"}</h3>
      <div id="google-button"></div>
      <div id="google-status" hidden role="status" aria-live="polite">
        <p id="google-message"></p>
        <button id="google-route" class="secondary">
          ${signup ? "로그인으로 이동" : "회원가입으로 이동"}
        </button>
      </div>
    </section>
    <p class="auth-divider">
      <span>${signup ? "또는 이메일로 회원가입" : "또는 이메일로 로그인"}</span>
    </p>`;
}

export function authLayoutHtml() {
  return /* HTML */ `<div class="auth-layout">
    <section class="auth-card">
      <div class="brand">하루</div>
      <h2>
        ${state.authMode === "login" ? "로그인" : state.authMode === "signup" ? "회원가입" : "비밀번호 재설정"}
      </h2>
      ${googleEntryHtml()}
      <div id="auth-fields"></div>
      ${state.config?.mail_preview ? '<p class="dev-note">로컬 개발 모드 · 이메일은 실제 발송되지 않으며 인증번호가 화면에 표시됩니다. 실제 이메일 소유 확인이 아닙니다.</p>' : state.config?.development && !state.config.mail_ready ? '<p class="dev-note">Gmail 연결 대기 · 실제 메일 발송 설정이 아직 완료되지 않았습니다. 인증번호는 화면에 표시하지 않습니다.</p>' : ""}
    </section>
  </div>`;
}

export function verificationFormHtml() {
  return /* HTML */ `${state.authMode === "signup" ? profileFields() : ""}
    <section class="verification-section" aria-labelledby="captcha-heading">
      <h3 id="captcha-heading">자동 가입 방지</h3>
      <p class="hint">
        아래 이미지의 숫자를 입력하고 확인해주세요. 이메일 인증번호와는
        다릅니다.
      </p>
      <div id="captcha"></div>
    </section>
    <section class="verification-section" aria-labelledby="email-heading">
      <h3 id="email-heading">이메일 인증</h3>
      <p class="hint">
        입력한 이메일을 사용할 수 있는지 확인합니다. 메일로 받은 인증번호를
        입력해주세요.
      </p>
      ${field("email", "이메일 (로그인 ID)", "email")}${button("이메일 인증번호 보내기", "send-code", true)}
      <p id="code-status" class="hint" role="status" aria-live="polite"></p>
      ${field("code", "이메일 인증번호")}
      ${button("이메일 인증번호 확인", "verify-code", true)}
    </section>
    <div id="verified-fields" ${state.authMode === "signup" ? "" : "hidden"}>
      ${field("new-password", "새 비밀번호 (12자 이상)", "password")}${field("confirm-password", "비밀번호 확인", "password")}
      <p id="password-status" class="hint" role="status" aria-live="polite"></p>
      ${state.authMode === "signup" ? privacyHtml() : ""}${button(state.authMode === "signup" ? "가입 완료" : "비밀번호 변경", "finish")}
    </div>
    <button class="quiet" id="back-login">로그인으로 돌아가기</button>`;
}

export function googleProfileHtml(info: { email: string; name: string }) {
  return /* HTML */ `<div class="auth-layout">
    <section class="auth-card">
      <div class="brand">하루</div>
      <h2>Google 회원가입</h2>
      <p>Google에서 확인한 이메일: ${escape(info.email)}</p>
      ${profileFields(info.name)}
      <section class="verification-section">
        <h3>자동 가입 방지</h3>
        <div id="captcha"></div>
      </section>
      ${privacyHtml()}${button("Google 가입 완료", "google-finish")}<button
        id="google-cancel"
        class="quiet"
      >
        회원가입으로 돌아가기
      </button>
    </section>
  </div>`;
}

export function reloginHtml() {
  return /* HTML */ `<h2>다시 로그인이 필요해요</h2>
    <p>작성한 글은 그대로 남아 있습니다.</p>
    ${authFormHtml()}<button id="close-relogin" class="quiet">
      글로 돌아가기
    </button>`;
}
