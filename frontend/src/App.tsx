import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { auth } from "./api";
import { Dashboard, Discovery, CompanyList, CompanyDetail, Drafts, DraftDetail, ProfileSettings } from "./pages";

function Shell() {
  const navigate = useNavigate();
  const [token, setToken] = useState(auth.get());
  const saveToken = () => { auth.set(token.trim()); navigate("/"); window.location.reload(); };
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">↗</span><span>Startup<span>Reach</span><small>AI research workspace</small></span></div>
      <nav><NavLink to="/">Overview</NavLink><NavLink to="/discover">Discover startups</NavLink><NavLink to="/companies">Companies</NavLink><NavLink to="/drafts">Email drafts</NavLink><NavLink to="/settings">Profile & settings</NavLink></nav>
      <div className="sidebar-footer"><div className="eyebrow">WORKSPACE ACCESS</div><div className="token-row"><input aria-label="API bearer token" value={token} onChange={e => setToken(e.target.value)} placeholder="Bearer token" type="password" /><button className="icon-btn" onClick={saveToken} title="Save token" aria-label="Save API token">↵</button></div><p>Shared single-user access. Token stays in this browser session.</p></div>
    </aside>
    <main className="main"><Routes><Route path="/" element={<Dashboard />} /><Route path="/discover" element={<Discovery />} /><Route path="/companies" element={<CompanyList />} /><Route path="/companies/:id" element={<CompanyDetail />} /><Route path="/drafts" element={<Drafts />} /><Route path="/drafts/:id" element={<DraftDetail />} /><Route path="/settings" element={<ProfileSettings />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></main>
  </div>;
}
export default function App() { return <Shell />; }
