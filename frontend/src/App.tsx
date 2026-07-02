import { useEffect, useState } from "react";
import { getHealth } from "./api/client";

function App() {
  const [status, setStatus] = useState("Checking backend...");

  useEffect(() => {
    getHealth()
      .then((data) => {
        setStatus(`Backend: ${data.status}`);
      })
      .catch((error) => {
        console.error(error);
        setStatus("Backend: unavailable");
      });
  }, []);

  return (
    <main>
      <h1>AI Earth Intelligence & Forecasting Engine</h1>
      <p>Earth Intelligence & Forecasting Platform</p>
      <p>{status}</p>
    </main>
  );
}

export default App;