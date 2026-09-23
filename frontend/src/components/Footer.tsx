import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-grid">
        <div>
          <p className="footer-brand">AI Earth Intelligence &amp; Forecasting Engine</p>
          <p className="footer-tagline">Question &rarr; plan &rarr; validate &rarr; answer.</p>
        </div>

        <div>
          <h5>Explore</h5>
          <ul>
            <li>
              <Link to="/">Ask &amp; Forecast</Link>
            </li>
            <li>
              <Link to="/results">Measured Results</Link>
            </li>
            <li>
              <Link to="/about">About</Link>
            </li>
          </ul>
        </div>

        <div>
          <h5>Data</h5>
          <ul>
            <li>NASA FIRMS</li>
            <li>ERA5-Land (Copernicus CDS)</li>
            <li>Copernicus DEM GLO-30</li>
            <li>ESA WorldCover 10m</li>
          </ul>
        </div>

        <div>
          <h5>Contact</h5>
          <ul>
            <li>Email: khoahonguyen0210@gmail.com</li>
            <li>Github: khoahonguyen0210</li>
          </ul>
        </div>
      </div>

      <p className="footer-legal">
        MIT licensed.
      </p>
    </footer>
  );
}
