import { useState } from "react";
import AppNav from "./components/AppNav";
import ControlBar from "./components/ControlBar";
import ExportView from "./components/ExportView";
import InsightsPanel from "./components/InsightsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import LightRays from "./components/ui/light-rays";
import { generateExport, getHistorySession } from "./lib/api";
import type { Segment } from "./lib/types";
import { useSessionWs } from "./lib/useSessionWs";

export default function App() {
  const session = useSessionWs();
  const [pastView, setPastView] = useState<{
    sessionId: string;
    segments: Segment[];
  } | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportGenerating, setExportGenerating] = useState(false);
  const [activeModel, setActiveModel] = useState<string>("phi3");

  const handleViewPast = async (id: string) => {
    try {
      const data = await getHistorySession(id);
      setPastView({ sessionId: data.session_id, segments: data.segments });
      setExportOpen(false);
    } catch (err) {
      console.error(err);
      alert(`Failed to load session: ${String(err)}`);
    }
  };

  const handleOpenExport = () => {
    setPastView(null);
    setExportOpen(true);
  };

  const handleGenerate = async () => {
    if (exportGenerating) return;
    setExportGenerating(true);
    try {
      const draft = await generateExport();
      session.setExportDraft(draft);
    } catch (err) {
      console.error(err);
      alert(String(err));
    } finally {
      setExportGenerating(false);
    }
  };

  const exportReady =
    session.state === "idle" &&
    session.insights.some((i) => i.status === "approved");

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
      <div className="h-screen flex flex-col overflow-hidden relative">
        <AppNav
          onSelectPast={handleViewPast}
          onOpenExport={handleOpenExport}
          exportReady={exportReady}
          exportOpen={exportOpen}
          onModelChange={setActiveModel}
        />
        <div className="flex-1 min-h-0 max-w-7xl w-full mx-auto px-8 py-6 flex flex-col gap-6">
          {exportOpen ? (
            <ExportView
              draft={session.exportDraft}
              generating={exportGenerating}
              onGenerate={handleGenerate}
              onBack={() => setExportOpen(false)}
              model={activeModel}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 flex-1 min-h-0">
                <div className="min-h-0">
                  <TranscriptPanel
                    segments={segmentsToShow}
                    viewingPastId={pastView?.sessionId ?? null}
                    onBackToLive={() => setPastView(null)}
                  />
                </div>
                <div className="min-h-0">
                  <InsightsPanel
                    insights={session.insights}
                    aiStatus={session.aiStatus}
                  />
                </div>
              </div>
              <ControlBar state={session.state} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
