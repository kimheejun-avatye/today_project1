export function script(src: string): Promise<void> {
  const pending = scriptLoads.get(src);
  if (pending) return pending;
  const s = document.createElement("script");
  s.src = src;
  const loading = new Promise<void>((resolve, reject) => {
    s.onload = () => resolve();
    s.onerror = () => {
      scriptLoads.delete(src);
      s.remove();
      reject(Error("외부 로그인 기능을 불러오지 못했습니다."));
    };
  });
  scriptLoads.set(src, loading);
  document.head.append(s);
  return loading;
}

export const scriptLoads = new Map<string, Promise<void>>();
