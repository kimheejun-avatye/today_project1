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

// 화면이 상태 코드와 재시도 대기 시간으로 오류를 구분할 수 있게 합니다.
export class ApiError extends Error {
  status: number;
  retryAfter: number | null;

  constructor(message: string, status: number, retryAfter: number | null) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
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
    const header = response.headers.get("Retry-After");
    const seconds = Number(header);
    throw new ApiError(
      typeof result.detail === "string"
        ? result.detail
        : "입력값을 확인해주세요.",
      response.status,
      header && Number.isFinite(seconds) ? seconds : null,
    );
  }
  return result;
}

// 같은 탭의 동시 요청은 재발급 한 번을 공유합니다.
let refreshing: Promise<boolean> | null = null;
