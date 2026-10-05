// Minimal inline SVG icon set (Lucide-style strokes) — no emoji in the UI.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = (p: P) => ({ width: 14, height: 14, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, ...p });

export const IconActivity = (p: P) => <svg {...base(p)}><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>;
export const IconPlay = (p: P) => <svg {...base(p)}><polygon points="6 3 20 12 6 21 6 3" /></svg>;
export const IconPause = (p: P) => <svg {...base(p)}><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>;
export const IconStop = (p: P) => <svg {...base(p)}><rect x="5" y="5" width="14" height="14" rx="2" /></svg>;
export const IconFlask = (p: P) => <svg {...base(p)}><path d="M9 3h6" /><path d="M10 3v6.5L4.5 19a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9.5V3" /></svg>;
export const IconDna = (p: P) => <svg {...base(p)}><path d="M4 4c4 4 12 4 16 0" /><path d="M4 20c4-4 12-4 16 0" /><path d="M6 8c3 2 9 2 12 0" /><path d="M6 16c3-2 9-2 12 0" /><path d="M12 6v12" /></svg>;
export const IconFile = (p: P) => <svg {...base(p)}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="8" y1="13" x2="16" y2="13" /><line x1="8" y1="17" x2="14" y2="17" /></svg>;
export const IconChart = (p: P) => <svg {...base(p)}><line x1="4" y1="20" x2="20" y2="20" /><rect x="6" y="10" width="3" height="8" /><rect x="11" y="5" width="3" height="13" /><rect x="16" y="13" width="3" height="5" /></svg>;
export const IconBox = (p: P) => <svg {...base(p)}><path d="M21 8l-9-5-9 5v8l9 5 9-5z" /><path d="M3 8l9 5 9-5" /><path d="M12 13v8" /></svg>;
export const IconMap = (p: P) => <svg {...base(p)}><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" /><line x1="8" y1="2" x2="8" y2="18" /><line x1="16" y1="6" x2="16" y2="22" /></svg>;
export const IconDownload = (p: P) => <svg {...base(p)}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>;
export const IconX = (p: P) => <svg {...base(p)}><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>;
export const IconExternal = (p: P) => <svg {...base(p)}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>;
export const IconSkipEnd = (p: P) => <svg {...base(p)}><polygon points="5 4 15 12 5 20 5 4" /><line x1="19" y1="5" x2="19" y2="19" /></svg>;
export const IconRefresh = (p: P) => <svg {...base(p)}><polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" /></svg>;
export const IconPanel = (p: P) => <svg {...base(p)}><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="9" y1="3" x2="9" y2="21" /></svg>;
export const IconSkipStart = (p: P) => <svg {...base(p)}><polygon points="19 4 9 12 19 20 19 4" /><line x1="5" y1="5" x2="5" y2="19" /></svg>;
export const IconPrev = (p: P) => <svg {...base(p)}><polyline points="15 18 9 12 15 6" /></svg>;
export const IconNext = (p: P) => <svg {...base(p)}><polyline points="9 18 15 12 9 6" /></svg>;
export const IconExpand = (p: P) => <svg {...base(p)}><polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" /><line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" /></svg>;
export const IconCollapse = (p: P) => <svg {...base(p)}><polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" /><line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" /></svg>;
export const IconSettings = (p: P) => <svg {...base(p)}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.35.4.65.74.83H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>;
export const IconTarget = (p: P) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4" /><line x1="12" y1="1" x2="12" y2="5" /><line x1="12" y1="19" x2="12" y2="23" /><line x1="1" y1="12" x2="5" y2="12" /><line x1="19" y1="12" x2="23" y2="12" /></svg>;
