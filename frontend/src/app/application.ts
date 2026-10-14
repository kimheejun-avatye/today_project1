import { state } from "./state";
import { escape, on, catchError, toast } from "../shared/lib/dom";
import { preserve, calendar } from "../pages/calendar/index";
import { api } from "../shared/api/client";
import { renderAuth } from "../pages/auth/index";
import { community } from "../pages/community/index";
import { profile } from "../pages/profile/index";

export function shell() {
  state.root.innerHTML = `<header><a class="brand" href="#">하루</a><nav><button id="nav-calendar" class="${state.view === "calendar" ? "active" : ""}">나의 캘린더</button><button id="nav-community" class="${state.view === "community" ? "active" : ""}">커뮤니티</button><button id="nav-profile">${escape(state.user!.nickname || "익명")} 님</button><button id="logout" class="quiet">로그아웃</button></nav></header><main id="main"></main><footer>하루 · 일기와 할 일</footer>`;
  on("#nav-calendar", "click", () => {
    preserve();
    state.view = "calendar";
    render();
  });
  on("#nav-community", "click", () => {
    preserve();
    state.view = "community";
    render();
  });
  on("#nav-profile", "click", () => {
    preserve();
    state.view = "profile";
    render();
  });
  on(
    "#logout",
    "click",
    catchError(async () => {
      preserve();
      await api("/auth/logout", "POST");
      state.user = null;
      state.authMode = "login";
      renderAuth();
    }),
  );
}

export async function render() {
  if (!state.user) return renderAuth();
  shell();
  try {
    if (state.view === "calendar") await calendar();
    else if (state.view === "community") await community();
    else profile();
  } catch (e) {
    toast((e as Error).message);
  }
}
