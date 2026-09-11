import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getHealth } from "../api/client";

export function Navbar() {
  const [backendStatus, setBackendStatus] = useState("Checking backend...");

  useEffect(() => {
    getHealth()
      .then((data) => setBackendStatus(`Backend: ${data.status}`))
      .catch(() => setBackendStatus("Backend: unavailable"));
  }, []);

  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand" end>
        AI Earth Intelligence
      </NavLink>

      <div className="navbar-links">
        <NavLink to="/" end>
          Ask &amp; Forecast
        </NavLink>
        <NavLink to="/results">Results</NavLink>
        <NavLink to="/about">About</NavLink>
      </div>

      <p className="backend-status">{backendStatus}</p>
    </nav>
  );
}
