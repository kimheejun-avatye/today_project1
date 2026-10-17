import type { User, Diary, Config } from "../shared/types/index";
import { seoulToday } from "../shared/lib/dom";

interface AppState {
  root: HTMLDivElement;
  user: User | null;
  config: Config;
  day: string;
  month: string;
  view: string;
  authMode: string;
  currentDiary: Diary | null;
  authGeneration: number;
  verification: { id: string; flow: string } | null;
  verified: boolean;
  captchaToken: string;
  captchaId: string;
  captchaGeneration: number;
  captchaTimer: number | undefined;
}

const today = seoulToday();

export const state: AppState = {
  root: document.querySelector<HTMLDivElement>("#app")!,
  user: null,
  config: undefined!,
  day: today,
  month: today.slice(0, 7),
  view: "calendar",
  authMode: "login",
  currentDiary: null,
  authGeneration: 0,
  verification: null,
  verified: false,
  captchaToken: "",
  captchaId: "",
  captchaGeneration: 0,
  captchaTimer: undefined!,
};
