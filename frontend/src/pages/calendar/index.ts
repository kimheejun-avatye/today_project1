import { state } from "../../app/state";
import {
  value,
  toast,
  localDate,
  on,
  escape,
  button,
  catchError,
} from "../../shared/lib/dom";
import type { Diary, Task } from "../../shared/types/index";
import { api } from "../../shared/api/client";
import { render } from "../../app/application";

export function draftKey() {
  return `haru:draft:${state.user!.id}:${state.day}`;
}

export function preserve() {
  if (!state.user || !state.currentDiary || !document.querySelector("#content"))
    return;
  try {
    sessionStorage.setItem(
      draftKey(),
      JSON.stringify({
        ...state.currentDiary,
        content: value("content"),
        emotion: value("emotion"),
      }),
    );
  } catch {
    toast("브라우저 복구 공간이 부족합니다. 서버에 임시 저장해주세요.");
  }
}

export async function calendar() {
  const entries: Diary[] = await api("/diaries?month=" + state.month);
  const [y, m] = state.month.split("-").map(Number);
  const days = new Date(y, m, 0).getDate(),
    start = new Date(y, m - 1, 1).getDay();
  document.querySelector("#main")!.innerHTML =
    `<section class="page-heading"><h1>나의 캘린더</h1><p>날짜를 골라 할 일과 마음을 남겨보세요.</p></section><div class="workspace"><aside class="calendar card"><div class="month-nav"><button id="prev">‹</button><h2>${y}년 ${m}월</h2><button id="next">›</button></div><div class="week">${["일", "월", "화", "수", "목", "금", "토"].map((x) => `<span>${x}</span>`).join("")}</div><div class="days">${"<span></span>".repeat(start)}${Array.from(
      { length: days },
      (_, i) => {
        const key = `${state.month}-${String(i + 1).padStart(2, "0")}`;
        const d = entries.find((e) => e.date === key);
        return `<button data-day="${key}" class="${state.day === key ? "selected" : ""} ${key === localDate(new Date()) ? "today" : ""}">${i + 1}<small>${d ? (d.shared ? "●" : "•") : " "}</small></button>`;
      },
    ).join(
      "",
    )}</div><p class="hint">• 기록한 날 &nbsp; ● 공유한 날</p></aside><section id="editor" class="card"></section></div>`;
  const move = (n: number) => {
    preserve();
    state.month = localDate(new Date(y, m - 1 + n, 1)).slice(0, 7);
    calendar().catch((e) => toast(e.message));
  };
  on("#prev", "click", () => move(-1));
  on("#next", "click", () => move(1));
  document.querySelectorAll("[data-day]").forEach((b) =>
    b.addEventListener("click", () => {
      preserve();
      state.day = (b as HTMLElement).dataset.day!;
      calendar().catch((e) => toast(e.message));
    }),
  );
  await editor();
}

export async function editor() {
  const [d, tasks]: [Diary, Task[]] = await Promise.all([
    api("/diaries/" + state.day),
    api("/tasks/" + state.day),
  ]);
  state.currentDiary = d;
  let saved: Diary | null = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(draftKey()) || "null");
  } catch {}
  const recovery =
    saved && (saved.content !== d.content || saved.emotion !== d.emotion);
  if (recovery && saved) {
    d.content = saved.content;
    d.emotion = saved.emotion;
    state.currentDiary = { ...d, version: saved.version };
  }
  document.querySelector("#editor")!.innerHTML =
    `<div class="editor-top"><div><h2>${Number(state.day.slice(5, 7))}월 ${Number(state.day.slice(8))}일의 기록</h2></div><span class="badge">${d.status === "FINAL" ? "등록 완료" : "작성 중"}</span></div>${recovery ? '<div class="recovery">이 탭의 작성 내용을 복구했습니다. 서버 내용과 충돌하면 저장을 막고 안내합니다.</div>' : ""}<h3>오늘의 할 일 <span class="hint">${tasks.filter((t) => t.completed).length} / ${tasks.length}</span></h3><div class="tasks">${tasks.map((t, i) => `<div class="task"><label><input type="checkbox" data-task="${i}" ${t.completed ? "checked" : ""}><span class="${t.completed ? "done" : ""}">${escape(t.title)}</span>${t.recurring_id ? "<small>매일</small>" : ""}</label>${t.recurring_id ? `<button class="quiet" data-stop="${t.recurring_id}">반복 중단</button>` : `<button class="quiet" data-delete-task="${t.id}">삭제</button>`}</div>`).join("") || '<p class="hint">작은 할 일부터 하나 추가해보세요.</p>'}</div><div class="task-add"><input id="task-title" placeholder="할 일을 적어주세요" maxlength="200"><label class="inline"><input id="recurring" type="checkbox">매일</label>${button("추가", "add-task", true)}</div><hr><label>오늘의 감정<input id="emotion" maxlength="40" placeholder="오늘의 마음을 한마디로" value="${escape(d.emotion)}"></label><label>오늘의 이야기<textarea id="content" placeholder="어떤 하루였나요? 자유롭게 적어보세요.">${escape(d.content)}</textarea></label><p class="hint">작성 내용은 이 탭에 복구용으로 보관됩니다. 다른 기기에서 이어 쓰려면 임시 저장해주세요.</p><div class="actions">${button("임시 저장", "save-draft", true)}${button("등록하기", "publish")}<button id="share" class="quiet">${d.shared ? "공유 취소" : "커뮤니티에 공유"}</button>${d.id ? '<button id="delete-diary" class="quiet danger">삭제</button>' : ""}</div><p class="hint">공유하면 일기 본문과 감정이 공개됩니다. 이후 수정 내용도 반영됩니다. 할 일·연락처는 공개되지 않습니다.</p>`;
  on("#content", "input", preserve);
  on("#emotion", "input", preserve);
  document.querySelectorAll("[data-task]").forEach((b) =>
    b.addEventListener(
      "change",
      catchError(async () => {
        const t = tasks[Number((b as HTMLElement).dataset.task)];
        await api("/tasks", "PATCH", {
          id: t.id || 0,
          recurring_id: t.recurring_id || 0,
          day: state.day,
          completed: (b as HTMLInputElement).checked,
        });
      }),
    ),
  );
  on(
    "#add-task",
    "click",
    catchError(async () => {
      preserve();
      await api("/tasks", "POST", {
        title: value("task-title"),
        day: state.day,
        recurring: (document.querySelector("#recurring") as HTMLInputElement)
          .checked,
      });
      await editor();
    }),
  );
  document.querySelectorAll("[data-stop]").forEach((b) =>
    b.addEventListener(
      "click",
      catchError(async () => {
        preserve();
        await api(
          `/recurring/${(b as HTMLElement).dataset.stop}/stop?day=${state.day}`,
          "POST",
        );
        toast("선택한 날짜까지만 반복합니다.");
        await editor();
      }),
    ),
  );
  document.querySelectorAll("[data-delete-task]").forEach((b) =>
    b.addEventListener(
      "click",
      catchError(async () => {
        preserve();
        await api("/tasks/" + (b as HTMLElement).dataset.deleteTask, "DELETE");
        await editor();
      }),
    ),
  );
  const save = async (
    status: string,
    shared: boolean,
    openCommunity = false,
  ) => {
    if (shared && !value("content").trim() && !value("emotion").trim())
      throw Error(
        "공유할 일기 본문이나 감정을 입력해주세요. 할 일은 공유되지 않습니다.",
      );
    preserve();
    state.currentDiary = await api("/diaries/" + state.day, "PUT", {
      content: value("content"),
      emotion: value("emotion"),
      status,
      shared,
      version: state.currentDiary!.version,
    });
    sessionStorage.removeItem(draftKey());
    toast(
      openCommunity
        ? "일기 본문과 감정을 공유했습니다."
        : "서버에 저장했습니다.",
    );
    if (openCommunity) {
      state.view = "community";
      await render();
    } else await calendar();
  };
  on(
    "#save-draft",
    "click",
    catchError(() => save("DRAFT", false)),
  );
  on(
    "#publish",
    "click",
    catchError(() => save("FINAL", state.currentDiary!.shared)),
  );
  on(
    "#share",
    "click",
    catchError(async () => {
      if (!d.shared && !confirm("일기 본문과 감정을 커뮤니티에 공개할까요?"))
        return;
      await save("FINAL", !d.shared, !d.shared);
    }),
  );
  on(
    "#delete-diary",
    "click",
    catchError(async () => {
      if (!confirm("일기와 연결된 댓글을 삭제할까요? 할 일은 남습니다."))
        return;
      await api("/diaries/" + state.day, "DELETE");
      sessionStorage.removeItem(draftKey());
      await calendar();
    }),
  );
}
