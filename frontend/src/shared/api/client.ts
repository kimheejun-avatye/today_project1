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
  // 진행 중인 재발급이 끝난 뒤 로그아웃해 늦은 Set-Cookie 응답과 충돌하지 않게 한다.
  if (path === "/auth/logout") {
    ending = true;
    generation++;
    try {
      await refreshing?.catch(() => false);
      return await authLock(async () => {
        const response = await fetch("/api/auth/logout", {
          method: "POST", credentials: "same-origin",
          headers: { "X-CSRF-Token": decodeURIComponent(csrf()) },
        });
        if (!response.ok) throw new ApiError("로그아웃에 실패했습니다. 다시 시도해주세요.", response.status, null);
        broadcast?.postMessage("ended");
        return response.json();
      });
    } finally { ending = false; }
  }
  const requestGeneration = generation;
  const sentProof = csrf();
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
    if (ending || requestGeneration !== generation) throw new ApiError("로그인이 종료되었습니다.", 401, null);
    if (!refreshing) refreshing = authLock(async () => {
      if (ending || requestGeneration !== generation) return false;
      // 탭 간 잠금을 기다리는 동안 다른 탭이 쿠키를 바꿨다면 그 결과를 재사용한다.
      if (csrf() && csrf() !== sentProof) return true;
      const r = await fetch("/api/auth/refresh", {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRF-Token": decodeURIComponent(csrf()) },
      });
      if (r.status === 401) return false;
      if (!r.ok) throw new ApiError("재발급에 실패했습니다. 잠시 후 다시 시도해주세요.", r.status, null);
      return true;
    }).finally(() => (refreshing = null));
    if (await refreshing && requestGeneration === generation && !ending)
      return api(path, method, body, false);
  }

  // 로그아웃 이전에 시작한 요청이 늦게 끝나도 로그인 후 화면 상태를 되살리지 않는다.
  if (ending || requestGeneration !== generation)
    throw new ApiError("로그인이 종료되었습니다.", 401, null);
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
    // 헤더가 없거나 숫자가 아니면 null로 둡니다.
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

let ending = false;
let generation = 0;
const broadcast = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("haru-auth") : null;
broadcast?.addEventListener("message", (event) => {
  if (event.data === "ended") { generation++; onUnauthorized(); }
});
// Web Locks 지원 환경에서 같은 출처의 여러 탭을 조율한다. 미지원 환경도 서버가 중복 교체를 거절한다.
function authLock<T>(action: () => Promise<T>): Promise<T> {
  return navigator.locks ? navigator.locks.request("haru-auth", action) : action();
}

// 화면의 재로그인 안내용 판정이다. 브라우저 시계나 읽은 JWT를 서버 인증 근거로 사용하지 않는다.
export function checkLoginDeadline() {
  const proof = csrf();
  try {
    const payload = JSON.parse(atob(decodeURIComponent(proof).split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.exp * 1000 > Date.now()) return;
  } catch { /* 쿠키가 사라졌거나 읽을 수 없어도 재로그인을 안내한다. */ }
  onUnauthorized();
}
