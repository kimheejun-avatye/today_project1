import { state } from "../../app/state";
import { api } from "../../shared/api/client";
import {
  escape,
  button,
  on,
  catchError,
  value,
  toast,
} from "../../shared/lib/dom";

export async function loadCaptcha() {
  const box = document.querySelector("#captcha");
  if (!box) return;
  const generation = ++state.captchaGeneration;
  state.captchaToken = "";
  clearTimeout(state.captchaTimer);
  box.innerHTML = '<p role="status">숫자 이미지를 불러오는 중…</p>';
  try {
    const challenge = await api("/auth/captcha", "POST", {
      previous_id: state.captchaId,
    });
    if (generation !== state.captchaGeneration || !box.isConnected) return;
    state.captchaId = challenge.id;
    box.innerHTML = `<img class="captcha-image" src="${escape(challenge.image)}" alt="자동 가입 방지용 숫자 이미지. 읽기 어려우면 새 이미지 또는 숫자 음성을 이용해주세요."><audio controls src="${escape(challenge.audio)}" aria-label="숫자 음성 듣기 (영어)"></audio><p class="hint">5자리 숫자 · 2분 유효 · 음성은 영어로 읽어줍니다.</p><label>이미지의 숫자<input id="captcha-answer" inputmode="numeric" autocomplete="off" maxlength="5"></label>${button("숫자 확인", "captcha-check", true)}${button("새 이미지 받기", "captcha-refresh", true)}<p id="captcha-status" role="status" aria-live="polite"></p>`;
    state.captchaTimer = window.setTimeout(
      () => {
        if (generation !== state.captchaGeneration || !box.isConnected) return;
        state.captchaToken = "";
        box.querySelector("#captcha-status")!.textContent =
          "이미지가 만료되었습니다. 새 이미지를 받아주세요.";
      },
      Math.max(0, challenge.expires_at * 1000 - Date.now()),
    );
    on("#captcha-refresh", "click", () => {
      loadCaptcha();
    });
    on(
      "#captcha-check",
      "click",
      catchError(async () => {
        const result = await api("/auth/captcha/verify", "POST", {
          id: challenge.id,
          answer: value("captcha-answer"),
        });
        if (generation !== state.captchaGeneration || !box.isConnected) return;
        state.captchaToken = result.captcha_token;
        box.querySelector("#captcha-status")!.textContent = result.message;
      }),
    );
    on("#captcha-answer", "input", () => {
      state.captchaToken = "";
      box.querySelector("#captcha-status")!.textContent = "";
    });
  } catch (e) {
    if (generation !== state.captchaGeneration || !box.isConnected) return;
    box.innerHTML = `<p>이미지를 불러오지 못했습니다.</p>${button("다시 불러오기", "captcha-refresh", true)}`;
    on("#captcha-refresh", "click", () => {
      loadCaptcha();
    });
    toast((e as Error).message);
  }
}

export function resetCaptcha() {
  state.captchaToken = "";
  loadCaptcha();
}
