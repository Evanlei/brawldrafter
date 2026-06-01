import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { fetchCatalog } from "./api/catalog";
import { useDraftStore } from "./store/draftStore";
import { DraftView } from "./views/DraftView";
import { LobbyView } from "./views/LobbyView";

function HomeRoute() {
  const phase = useDraftStore((s) => s.phase);
  if (phase === "draft") {
    return <Navigate to="/draft" replace />;
  }
  return <LobbyView />;
}

export default function App() {
  const loadCatalog = useDraftStore((s) => s.loadCatalog);

  useEffect(() => {
    fetchCatalog()
      .then((catalog) => loadCatalog(catalog))
      .catch((error) => {
        console.warn("Catalog API unavailable; using bundled catalog.", error);
      });
  }, [loadCatalog]);

  return (
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/draft" element={<DraftView />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
