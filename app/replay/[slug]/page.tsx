import Link from "next/link";
import { ArrowLeft, Radio } from "lucide-react";
import ReplayClient from "@/components/ReplayClient";

export default async function ReplayPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <main className="app-shell replay-page"><header className="topbar"><Link className="brand-lockup replay-back" href="/"><ArrowLeft size={15} /> FLY / POKER</Link><span className="live-status"><Radio size={13} /> ARCHIVED HAND</span></header><section className="replay-hero"><p className="eyebrow">REPLAY ARCHIVE / {slug}</p><h1>A hand worth<br /><em>remembering.</em></h1><p className="lede">This replay is a deterministic event recording. It does not rerun the neural simulation.</p></section><ReplayClient slug={slug} /></main>;
}
