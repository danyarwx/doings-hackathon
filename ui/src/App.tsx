import DeliveryPanel from "./components/DeliveryPanel";
import Header from "./components/Header";
import InsightsPanel from "./components/InsightsPanel";
import TranscriptPanel from "./components/TranscriptPanel";
import { useSessionWs } from "./lib/useSessionWs";

export default function App() {
  const session = useSessionWs();

  return (
    <div className="min-h-screen p-6 flex flex-col gap-6">
      <Header
        state={session.state}
        sessionStart={session.sessionStart}
        segments={session.segments}
        deliveries={session.deliveries}
      />
      <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">
        <div className="col-span-12 lg:col-span-6 min-h-0">
          <TranscriptPanel segments={session.segments} />
        </div>
        <div className="col-span-12 lg:col-span-3 min-h-0">
          <DeliveryPanel deliveries={session.deliveries} />
        </div>
        <div className="col-span-12 lg:col-span-3 min-h-0">
          <InsightsPanel />
        </div>
      </div>
    </div>
  );
}
