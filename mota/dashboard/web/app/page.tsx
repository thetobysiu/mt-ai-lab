"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

// `/` → /live; `/?floor=x` (old deep link, used by the figure script) → /play?floor=x
function Redirector() {
  const router = useRouter();
  const params = useSearchParams();
  useEffect(() => {
    const floor = params.get("floor");
    router.replace(floor ? `/play/?floor=${encodeURIComponent(floor)}` : "/live/");
  }, [params, router]);
  return <p className="muted">Redirecting…</p>;
}

export default function Home() {
  return (
    <Suspense fallback={<p className="muted">Redirecting…</p>}>
      <Redirector />
    </Suspense>
  );
}
