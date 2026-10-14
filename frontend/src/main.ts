import "./app/styles.css";
import { state } from "./app/state";
import { preserve } from "./pages/calendar/index";
import { api, setUnauthorizedHandler } from "./shared/api/client";
import { render } from "./app/application";

import { showRelogin } from "./pages/auth/index";

setUnauthorizedHandler(() => {
  if (state.user) showRelogin();
});

window.addEventListener("beforeunload", preserve);
(async () => {
  try {
    state.config = await api("/config");
    try {
      state.user = await api("/me");
    } catch {}
    await render();
  } catch (e) {
    state.root.innerHTML =
      '<div class="card empty">서버에 연결할 수 없습니다. API 서버를 실행한 뒤 새로고침해주세요.</div>';
  }
})();
