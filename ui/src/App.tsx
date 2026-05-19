import ControlBar from "./components/ControlBar";
import InsightsPanel from "./components/InsightsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import { useSessionWs } from "./lib/useSessionWs";

export default function App() {
  const session = useSessionWs();

  return (
    <div className="min-h-screen p-6 flex flex-col gap-6">
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
  );
}
