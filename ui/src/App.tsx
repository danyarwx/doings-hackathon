import { useState } from "react";
import ControlBar from "./components/ControlBar";
import InsightsPanel from "./components/InsightsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import LightRays from "./components/ui/light-rays";
import { getHistorySession } from "./lib/api";
import type { Segment } from "./lib/types";
import { useSessionWs } from "./lib/useSessionWs";

export default function App() {
  const session = useSessionWs();
  const [pastView, setPastView] = useState<{
    sessionId: string;
    segments: Segment[];
  } | null>(null);

  const handleViewPast = async (id: string) => {
    try {
      const data = await getHistorySession(id);
      setPastView({ sessionId: data.session_id, segments: data.segments });
    } catch (err) {
      console.error(err);
      alert(`Failed to load session: ${String(err)}`);
    }
  };

  const segmentsToShow = pastView ? pastView.segments : session.segments;

  return (
    <>
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <LightRays
          raysOrigin="top-center"
          raysColor="#441fea"
          raysSpeed={1.0}
          lightSpread={0.9}
          rayLength={1.4}
          fadeDistance={1.2}
          saturation={0.9}
          followMouse={true}
          mouseInfluence={0.08}
          noiseAmount={0.05}
        />
      </div>
      <div className="h-screen p-6 flex flex-col gap-6 overflow-hidden relative">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1 min-h-0">
          <div className="min-h-0">
            <TranscriptPanel
              segments={segmentsToShow}
              viewingPastId={pastView?.sessionId ?? null}
              onViewPast={handleViewPast}
              onBackToLive={() => setPastView(null)}
            />
          </div>
          <div className="min-h-0">
            <InsightsPanel insights={session.insights} />
          </div>
        </div>
        <ControlBar state={session.state} />
      </div>
    </>
  );
}
