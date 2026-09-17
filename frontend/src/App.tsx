import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./App.css";
import { Footer } from "./components/Footer";
import { Navbar } from "./components/Navbar";
import { AboutPage } from "./pages/AboutPage";
import { HomePage } from "./pages/HomePage";
import { ResultsPage } from "./pages/ResultsPage";

function App() {
  return (
    <BrowserRouter>
      <div className="ambient-bg" aria-hidden="true">
        <span className="ambient-aurora" />
        <span className="ambient-glow ambient-glow-ember" />
        <span className="ambient-glow ambient-glow-teal" />
        <span className="ambient-glow ambient-glow-pink" />
        <span className="ambient-glow ambient-glow-blue" />
        <span className="ambient-stars" />
      </div>
      <Navbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Routes>
      <Footer />
    </BrowserRouter>
  );
}

export default App;
