"use client";
// App shell: collapsible left rail + context topbar (page title, global API/job status).
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { getJson } from "@/lib/api";
import type { Job } from "@/lib/types";
import { ApiKeyPanel, useSettings } from "./ApiKeyPanel";
import { IconActivity, IconBox, IconChart, IconDna, IconFile, IconFlask, IconMap, IconPanel, IconTarget } from "./Icons";

const PAGES: [string, string, ComponentType<SVGProps<SVGSVGElement>>][] = [
  ["/live/", "Live", IconActivity],
  ["/play/", "Play", IconMap],
  ["/maps/", "Maps", IconBox],
  ["/experiments/", "Experiments", IconFlask],
  ["/gepa/", "GEPA", IconDna],
  ["/logs/", "Logs", IconFile],
  ["/reference/", "Reference", IconChart],
  ["/projects/", "Projects", IconTarget],
];

function useGlobalStatus() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [apiBusy, setApiBusy] = useState<string[]>([]);
  useEffect(() => {
    const tick = () => getJson<{ jobs: Job[]; api_busy: string[] }>("/api/jobs?active=1")
      .then((r) => { setJobs(r.jobs); setApiBusy(r.api_busy); }).catch(() => {});
    tick();
    const t = setInterval(tick, 5000);
    return () => clearInterval(t);
  }, []);
  return { jobs, apiBusy };
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname() ?? "";
  const [collapsed, setCollapsed] = useState(false);
  const { jobs, apiBusy } = useGlobalStatus();
  const { settings, reload } = useSettings();
  const [keyOpen, setKeyOpen] = useState(false);
  useEffect(() => { setCollapsed(localStorage.getItem("mota-rail") === "1"); }, []);
  const toggle = () => setCollapsed((v) => { localStorage.setItem("mota-rail", v ? "0" : "1"); return !v; });

  const current = PAGES.find(([href]) => path.startsWith(href.replace(/\/$/, "")));
  const running = jobs.filter((j) => j.status === "running").length;
  const paused = jobs.filter((j) => j.status === "paused").length;

  return (
    <div className={`app ${collapsed ? "collapsed" : ""}`}>
      <aside className="rail" data-testid="rail">
        <button className="nav-link mb-1" onClick={toggle} title={collapsed ? "Expand sidebar" : "Collapse sidebar"} data-testid="rail-toggle" aria-expanded={!collapsed}>
          <IconPanel />{!collapsed && <span className="heading" style={{ color: "var(--text)" }}>Magic Tower AI Lab</span>}
        </button>
        <nav className="flex flex-col gap-0.5" data-testid="nav" aria-label="Main">
          {PAGES.map(([href, label, Icon]) => {
            const active = path.startsWith(href.replace(/\/$/, ""));
            return (
              <Link key={href} href={href} data-testid={`nav-${label.toLowerCase()}`} aria-current={active ? "page" : undefined}
                    title={label} className={`nav-link ${active ? "active" : ""}`}>
                <Icon />{!collapsed && label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="min-w-0 flex flex-col">
        <header className="topbar">
          <h1 className="text-[13px]">{current ? current[1] : "Magic Tower AI Lab"}</h1>
          <span className="muted text-[11px] mono">hybrid deterministic–neural agent lab</span>
          <span className="ml-auto flex items-center gap-2 text-[11px]">
            {running > 0 && <span className="tag tag-ok" data-testid="top-running"><span className="dot dot-running" />{running} running</span>}
            {paused > 0 && <span className="tag tag-warn" data-testid="top-paused">{paused} paused</span>}
            {apiBusy.length > 0
              ? <span className="tag tag-warn" data-testid="top-api">LLM API busy</span>
              : <span className="tag" data-testid="top-api">LLM API free</span>}
            {jobs.length > 0 && <Link className="link" href="/live/">watch</Link>}
            <button className={`tag ${settings?.api_key.configured ? "" : "tag-warn"}`} onClick={() => setKeyOpen((v) => !v)}
                    data-testid="top-api-key" title="API key used for LLM runs started here">
              {settings?.api_key.configured ? "API key set" : "set API key"}
            </button>
          </span>
        </header>
        {keyOpen && (
          <div className="panel p-3 m-2" data-testid="api-key-popover">
            <div className="flex items-baseline gap-2 mb-2"><b>API key</b>
              <button className="btn btn-sm btn-ghost ml-auto" onClick={() => setKeyOpen(false)}>close</button></div>
            <ApiKeyPanel onChange={() => reload()} />
          </div>
        )}
        <main className="work flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
