// 통신 모듈은 화면을 직접 참조하지 않고 앱이 등록한 콜백을 호출합니다.
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export function csrf() {
  return (
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("csrf="))
      ?.slice(5) || ""
  );
}

export async function api(
  path: string,
  method = "GET",
  body?: unknown,
  retry = true,
): Promise<any> {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(csrf()),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (!refreshing)
      refreshing = fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "X-CSRF-Token": decodeURIComponent(csrf()) },
      })
        .then((r) => r.ok)
        .finally(() => (refreshing = null));
    if (await refreshing) return api(path, method, body, false);
  }
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
    throw Error(
      typeof result.detail === "string"
        ? result.detail
        : "입력값을 확인해주세요.",
    );
  }
  return result;
}

// 같은 탭의 동시 요청은 재발급 한 번을 공유합니다.
let refreshing: Promise<boolean> | null = null;
