import ControlBar from "./components/ControlBar";
import InsightsPanel from "./components/InsightsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import LightRays from "./components/ui/light-rays";
import { useSessionWs } from "./lib/useSessionWs";

export default function App() {
  const session = useSessionWs();

  return (
    <>
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <LightRays
          raysOrigin="top-center"
          raysColor="#7AB8FF"
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
            <TranscriptPanel segments={session.segments} />
          </div>
          <div className="min-h-0">
            <InsightsPanel />
          </div>
        </div>
        <ControlBar state={session.state} />
      </div>
    </>
  );
}
