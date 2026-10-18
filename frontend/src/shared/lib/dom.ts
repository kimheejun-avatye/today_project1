export const escape = (s: unknown) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );

export function localDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 서비스의 '오늘'은 기기 시간대와 무관하게 KST(Asia/Seoul) 기준이다.
export function seoulToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(
    new Date(),
  );
}

export function toast(text: string) {
  let n = document.querySelector("#notice");
  if (!n) {
    n = document.createElement("div");
    n.id = "notice";
    document.body.append(n);
  }
  n.textContent = text;
  setTimeout(() => n?.remove(), 7000);
}

export function on(
  selector: string,
  event: string,
  callback: (e: Event) => void,
) {
  document.querySelector(selector)?.addEventListener(event, callback);
}

export function value(id: string) {
  return (document.getElementById(id) as HTMLInputElement)?.value || "";
}

export function button(label: string, id: string, secondary = false) {
  return `<button id="${id}" class="${secondary ? "secondary" : ""}">${label}</button>`;
}

export function field(id: string, label: string, type = "text", val = "") {
  return `<label>${label}<input id="${id}" type="${type}" value="${escape(val)}" required ${type === "password" ? 'minlength="12" maxlength="128" autocomplete="new-password"' : ""}></label>`;
}

export function catchError(fn: () => Promise<unknown>) {
  return async (e: Event) => {
    e.preventDefault();
    const el = e.currentTarget as HTMLButtonElement;
    el.setAttribute("disabled", "");
    try {
      await fn();
    } catch (err) {
      toast((err as Error).message);
    } finally {
      el.removeAttribute("disabled");
    }
  };
}
