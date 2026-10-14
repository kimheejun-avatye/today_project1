import { state } from "../../app/state";
import type { Diary } from "../../shared/types/index";
import { api } from "../../shared/api/client";
import { escape, catchError, on, value } from "../../shared/lib/dom";

export async function community() {
  const posts: Diary[] = await api("/community");
  document.querySelector("#main")!.innerHTML =
    `<section class="page-heading"><h1>커뮤니티</h1><p>공유된 일기와 댓글을 확인하세요.</p></section><div class="feed">${posts.map((p) => `<article class="card post"><div class="post-meta">${escape(p.author)} · ${p.date}<span>${escape(p.emotion)}</span></div><p class="post-content">${p.content.trim() ? escape(p.content) : '<span class="hint">' + (p.emotion.trim() ? "감정만 기록한 일기입니다." : "본문과 감정이 없는 기존 공유 기록입니다. 내 캘린더에서 내용을 작성하거나 공유를 취소해주세요.") + "</span>"}</p><button data-comments="${p.id}" class="quiet">댓글 보기</button><div id="comments-${p.id}"></div></article>`).join("") || '<div class="card empty">아직 공유된 하루가 없어요.</div>'}</div>`;
  document.querySelectorAll("[data-comments]").forEach((b) =>
    b.addEventListener(
      "click",
      catchError(() =>
        loadComments(Number((b as HTMLElement).dataset.comments)),
      ),
    ),
  );
}

export async function loadComments(id: number) {
  const rows = await api(`/community/${id}/comments`);
  const box = document.getElementById("comments-" + id)!;
  box.innerHTML =
    rows
      .map(
        (c: any) =>
          `<div class="comment"><b>${escape(c.author)}</b><p>${escape(c.content)}</p>${c.member_id === state.user!.id ? `<button class="quiet" data-remove-comment="${c.id}">삭제</button>` : ""}</div>`,
      )
      .join("") +
    `<div class="task-add"><input id="comment-input-${id}" maxlength="2000" placeholder="따뜻한 댓글을 남겨주세요"><button id="comment-send-${id}">등록</button></div>`;
  on(
    "#comment-send-" + id,
    "click",
    catchError(async () => {
      await api(`/community/${id}/comments`, "POST", {
        content: value("comment-input-" + id),
      });
      await loadComments(id);
    }),
  );
  box.querySelectorAll("[data-remove-comment]").forEach((b) =>
    b.addEventListener(
      "click",
      catchError(async () => {
        await api(
          "/comments/" + (b as HTMLElement).dataset.removeComment,
          "DELETE",
        );
        await loadComments(id);
      }),
    ),
  );
}
