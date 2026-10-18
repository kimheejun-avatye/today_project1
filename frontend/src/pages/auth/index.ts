import {
  authFormHtml,
  authLayoutHtml,
  verificationFormHtml,
  googleProfileHtml,
  reloginHtml,
} from "./templates";
import { state } from "../../app/state";
import { on, catchError, value, toast, cooldown } from "../../shared/lib/dom";
import { api, ApiError } from "../../shared/api/client";
import { render } from "../../app/application";
import { loadCaptcha, resetCaptcha } from "./captcha";
import { script } from "../../shared/lib/external";
import { preserve } from "../calendar/index";

export function privacyInput() {
  const accepted =
    document.querySelector<HTMLInputElement>("#privacy-consent")?.checked ||
    false;
  if (!accepted) throw Error("개인정보 수집·이용 안내에 동의해주세요.");
  return {
    privacy_consent: accepted,
    privacy_consent_version: state.config.privacy_notice.version,
  };
}

export function renderAuth() {
  state.authGeneration++;
  state.captchaGeneration++;
  state.captchaToken = "";
  clearTimeout(state.captchaTimer);
  state.root.innerHTML = authLayoutHtml();
  if (state.authMode === "login") {
    document.querySelector("#auth-fields")!.innerHTML = authFormHtml();
    on(
      "#login-submit",
      "click",
      catchError(async () => {
        state.user = await api("/auth/login", "POST", {
          email: value("email"),
          password: value("password"),
        });
        await render();
      }),
    );
    on("#signup-link", "click", () => {
      state.authMode = "signup";
      state.verification = null;
      state.verified = false;
      renderAuth();
    });
    on("#reset-link", "click", () => {
      state.authMode = "reset";
      state.verification = null;
      state.verified = false;
      renderAuth();
    });
  } else {
    document.querySelector("#auth-fields")!.innerHTML = verificationFormHtml();
    loadCaptcha();
    const checkPasswords = () => {
      const password = value("new-password"),
        confirmation = value("confirm-password");
      const matches = password === confirmation;
      document.querySelector("#password-status")!.textContent = confirmation
        ? matches
          ? "비밀번호가 일치합니다."
          : "비밀번호가 일치하지 않습니다."
        : "";
      return matches;
    };
    on("#new-password", "input", checkPasswords);
    on("#confirm-password", "input", checkPasswords);
    on(
      "#send-code",
      "click",
      catchError(async () => {
        if (!state.captchaToken)
          throw Error(
            "먼저 이미지의 숫자를 입력해 자동 가입 방지를 확인해주세요.",
          );
        state.verification = null;
        state.verified = false;
        document.querySelector("#code-status")!.textContent = "";
        (document.querySelector("#verified-fields") as HTMLElement).hidden =
          state.authMode !== "signup";
        try {
          const result = await api("/auth/email/request", "POST", {
            email: value("email"),
            purpose: state.authMode === "signup" ? "SIGNUP" : "PASSWORD_RESET",
            captcha_token: state.captchaToken,
          });
          state.verification = result;
          document.querySelector("#code-status")!.textContent = result.dev_code
            ? `개발용 인증번호: ${result.dev_code}`
            : result.message;
        } catch (err) {
          // 서버가 대기 시간을 알려주면 그동안 버튼을 잠급니다.
          if (err instanceof ApiError && err.retryAfter)
            cooldown(
              document.querySelector<HTMLButtonElement>("#send-code")!,
              err.retryAfter,
            );
          throw err;
        } finally {
          resetCaptcha();
        }
      }),
    );
    on(
      "#verify-code",
      "click",
      catchError(async () => {
        if (!state.verification) throw Error("먼저 인증번호를 요청해주세요.");
        await api("/auth/email/verify", "POST", {
          ...state.verification,
          code: value("code"),
        });
        state.verified = true;
        (document.querySelector("#verified-fields") as HTMLElement).hidden =
          false;
        document.querySelector("#code-status")!.textContent =
          "이메일 인증되었습니다";
        toast("이메일 인증되었습니다");
      }),
    );
    on("#email", "input", () => {
      state.verification = null;
      state.verified = false;
      document.querySelector("#code-status")!.textContent = "";
      (document.querySelector("#verified-fields") as HTMLElement).hidden =
        state.authMode !== "signup";
    });
    on(
      "#finish",
      "click",
      catchError(async () => {
        if (!checkPasswords()) {
          document
            .querySelector<HTMLInputElement>("#confirm-password")!
            .focus();
          throw Error("비밀번호가 일치하지 않습니다. 다시 확인해주세요.");
        }
        if (!state.verified || !state.verification)
          throw Error("이메일 인증이 필요합니다.");
        const consent = state.authMode === "signup" ? privacyInput() : {};
        const result = await api(
          state.authMode === "signup" ? "/auth/signup" : "/auth/password/reset",
          "POST",
          {
            ...state.verification,
            ...consent,
            password: value("new-password"),
            name: value("name"),
            nickname: value("nickname"),
          },
        );
        toast(result.message);
        state.authMode = "login";
        renderAuth();
      }),
    );
    on("#back-login", "click", () => {
      state.authMode = "login";
      renderAuth();
    });
  }
  googleButton();
}

export function googleProfile(
  credential: string,
  info: {
    email: string;
    name: string;
  },
) {
  state.authGeneration++;
  state.captchaGeneration++;
  clearTimeout(state.captchaTimer);
  state.root.innerHTML = googleProfileHtml(info);
  loadCaptcha();
  on(
    "#google-finish",
    "click",
    catchError(async () => {
      const consent = privacyInput();
      if (!state.captchaToken) throw Error("자동 가입 방지를 확인해주세요.");
      try {
        state.user = await api("/auth/google", "POST", {
          credential,
          intent: "signup",
          name: value("name"),
          nickname: value("nickname"),
          captcha_token: state.captchaToken,
          ...consent,
        });
        await render();
      } catch (e) {
        resetCaptcha();
        throw e;
      }
    }),
  );
  on("#google-cancel", "click", () => {
    state.authMode = "signup";
    renderAuth();
  });
}

export async function googleButton() {
  if (
    !state.config.google_client_id ||
    (state.authMode !== "login" && state.authMode !== "signup")
  )
    return;
  const mode = state.authMode,
    generation = state.authGeneration,
    box = document.querySelector("#google-button");
  if (!box) return;
  const current = () =>
    generation === state.authGeneration &&
    box.isConnected &&
    state.authMode === mode;
  const route = (message: string) => {
    document.querySelector("#google-message")!.textContent = message;
    (document.querySelector("#google-status") as HTMLElement).hidden = false;
    (document.querySelector("#google-route") as HTMLButtonElement).onclick =
      () => {
        state.authMode = mode === "login" ? "signup" : "login";
        state.verification = null;
        state.verified = false;
        renderAuth();
      };
  };
  try {
    await script("https://accounts.google.com/gsi/client");
    if (!current()) return;
    window.google.accounts.id.initialize({
      client_id: state.config.google_client_id,
      callback: async (result: any) => {
        if (!current()) return;
        try {
          const info = await api("/auth/google/prepare", "POST", {
            credential: result.credential,
          });
          if (!current()) return;
          if (mode === "signup") {
            if (!info.needs_profile) {
              route(
                "이미 가입된 Google 계정입니다. 로그인 화면에서 로그인해주세요.",
              );
              return;
            }
            googleProfile(result.credential, info);
            return;
          }
          if (info.needs_profile) {
            route(
              "아직 가입되지 않은 Google 계정입니다. 회원가입을 먼저 진행해주세요.",
            );
            return;
          }
          state.user = await api("/auth/google", "POST", {
            credential: result.credential,
            intent: "login",
          });
          await render();
        } catch (e) {
          if (current()) toast((e as Error).message);
        }
      },
    });
    window.google.accounts.id.renderButton(box, {
      theme: "outline",
      size: "large",
      text: mode === "signup" ? "signup_with" : "signin_with",
      locale: "ko",
      width: Math.min(400, Math.floor(box.clientWidth)),
    });
  } catch (e) {
    if (current()) toast((e as Error).message);
  }
}

export function showRelogin() {
  if (document.querySelector("#relogin")) return;
  preserve();
  const previous = state.user?.id;
  const modal = document.createElement("dialog");
  modal.id = "relogin";
  modal.innerHTML = reloginHtml();
  document.body.append(modal);
  modal.showModal();
  modal.querySelector("#login-submit")!.addEventListener(
    "click",
    catchError(async () => {
      const email = (modal.querySelector("#email") as HTMLInputElement).value,
        password = (modal.querySelector("#password") as HTMLInputElement).value;
      const next = await api("/auth/login", "POST", { email, password });
      modal.close();
      modal.remove();
      state.user = next;
      if (next.id !== previous) {
        toast("다른 계정으로 로그인했습니다. 이전 글은 저장하지 않습니다.");
        await render();
      } else toast("로그인했습니다. 저장 버튼을 다시 눌러주세요.");
    }),
  );
  modal.querySelector(".auth-links")?.remove();
  modal.querySelector("#close-relogin")!.addEventListener("click", () => {
    modal.close();
    modal.remove();
  });
}
