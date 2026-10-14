export type User = {
  id: number;
  email: string;
  name: string;
  nickname: string | null;
  google_only: boolean;
  google_linked: boolean;
};

export type Diary = {
  id: number | null;
  date: string;
  content: string;
  emotion: string;
  status: string;
  shared: boolean;
  version: number;
  author?: string;
};

export type Task = {
  id: number | null;
  recurring_id: number | null;
  title: string;
  completed: boolean;
};

export type Config = {
  development: boolean;
  mail_preview: boolean;
  mail_ready: boolean;
  google_client_id: string;
  privacy_notice: {
    version: string;
    title: string;
    items: string[];
    draft: boolean;
  };
};

declare global {
  interface Window {
    google: any;
  }
}
