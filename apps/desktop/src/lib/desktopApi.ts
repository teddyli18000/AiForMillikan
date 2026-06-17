import type { DesktopApi } from "../types";

declare global {
  interface Window {
    millikan?: DesktopApi;
  }
}

export const desktopApi: DesktopApi | null = window.millikan ?? null;
