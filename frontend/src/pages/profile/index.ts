import { profileHtml } from "./templates";
import { state } from "../../app/state";
import { on, catchError, value, toast, cooldown } from "../../shared/lib/dom";
import { api, ApiError } from "../../shared/api/client";
import { loadCaptcha, resetCaptcha } from "../auth/captcha";
import { renderAuth } from "../auth/index";
import { script } from "../../shared/lib/external";
import { render } from "../../app/application";

export function profile() {
  document.querySelector("#main")!.innerHTML = profileHtml();
  on(
    "#profile-save",
    "click",
    catchError(async () => {
      state.user = await api("/me", "PATCH", {
        name: value("profile-name"),
        nickname: value("profile-nickname"),
      });
      toast("변경했습니다.");
    }),
  );
  let proof: any = null;
  if (!state.user!.google_only) {
    loadCaptcha();
    on(
      "#email-send",
      "click",
      catchError(async () => {
        if (!state.captchaToken)
          throw Error("먼저 자동 가입 방지를 확인해주세요.");
        try {
          proof = await api("/auth/email/request", "POST", {
            email: value("new-email"),
            purpose: "EMAIL_CHANGE",
            captcha_token: state.captchaToken,
          });
          document.querySelector("#email-status")!.textContent = proof.dev_code
            ? `개발용 인증번호: ${proof.dev_code}`
            : proof.message;
        } catch (err) {
          // 서버가 대기 시간을 알려주면 그동안 버튼을 잠급니다.
          if (err instanceof ApiError && err.retryAfter)
            cooldown(
              document.querySelector<HTMLButtonElement>("#email-send")!,
              err.retryAfter,
            );
          throw err;
        } finally {
          resetCaptcha();
        }
      }),
    );
    on("#new-email", "input", () => (proof = null));
    on(
      "#email-change",
      "click",
      catchError(async () => {
        if (!proof) throw Error("인증번호를 먼저 요청하세요.");
        await api("/auth/email/verify", "POST", {
          ...proof,
          code: value("email-code"),
        });
        state.user = await api("/me/email", "POST", proof);
        toast("이메일을 변경했습니다.");
        profile();
      }),
    );
  }
  on("#password-reset", "click", () => {
    if (state.user!.google_only)
      return toast("Google에서 비밀번호를 관리해주세요.");
    state.authMode = "reset";
    renderAuth();
  });
  if (document.querySelector("#link-google"))
    script("https://accounts.google.com/gsi/client").then(() => {
      window.google.accounts.id.initialize({
        client_id: state.config.google_client_id,
        callback: async (r: any) => {
          const password = prompt("기존 계정 비밀번호를 입력해주세요.");
          if (!password || !confirm("선택한 Google 계정을 연결할까요?")) return;
          try {
            state.user = await api("/auth/google", "POST", {
              credential: r.credential,
              intent: "link",
              link_password: password,
              consent: true,
            });
            toast("Google 계정을 연결했습니다.");
            await render();
          } catch (e) {
            toast((e as Error).message);
          }
        },
      });
      window.google.accounts.id.renderButton(
        document.querySelector("#link-google"),
        { theme: "outline", size: "large" },
      );
    });
}
