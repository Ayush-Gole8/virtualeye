import React from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LayoutDashboard, Eye, FileText, Settings, Mic, LogOut, Star, Brain, Zap } from 'lucide-react';
import { useVoice } from '../../context/VoiceNavigationContext';
import { useMode } from '../../context/ModeContext';

const SidebarItem = ({ icon: Icon, label, path, active }) => {
  const navigate = useNavigate();
  return (
    <button 
      onClick={() => navigate(path)}
      className={`sidebar-item ${active ? 'active' : ''}`}
    >
      <Icon size={20} />
      <span>{label}</span>
      {active && <motion.div layoutId="active-pill" className="active-dot" />}
    </button>
  );
};

const DashboardLayout = () => {
  const location = useLocation();
  const { isListening, toggleListening } = useVoice();
  const { mode, toggleMode } = useMode();
  const navigate = useNavigate();

  const navItems = [
    { icon: LayoutDashboard, label: 'Overview (Commands)', path: '/dashboard' },
    { icon: Eye, label: 'Live Vision', path: '/dashboard/vision' },
    { icon: FileText, label: 'Read Text (OCR)', path: '/dashboard/ocr' },
    { icon: Settings, label: 'Settings', path: '/dashboard/settings' },
    { icon: Star, label: 'Demo Purpose Only', path: '/dashboard/demopurpose' },
  ];

  return (
    <div className="dashboard-layout">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-icon-small"><Eye size={20} /></div>
          <span className="logo-text-small">Virtual Eye</span>
        </div>

        <nav className="sidebar-nav">
          {navItems.map((item) => (
            <SidebarItem key={item.path} {...item} active={location.pathname === item.path} />
          ))}
        </nav>

        <button onClick={() => navigate('/')} className="exit-btn">
          <LogOut size={20} /> <span>Exit App</span>
        </button>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main-content">
        <header className="top-bar">
          <h2 className="page-title">
            {navItems.find(i => i.path === location.pathname)?.label || 'Dashboard'}
          </h2>

          {/* Priority / Naive mode toggle */}
          <button
            onClick={toggleMode}
            title={mode === 'priority'
              ? 'Priority Mode: Smart TTC-ranked filtering active. Click for Naive.'
              : 'Naive Mode: All objects announced. Click for Priority.'}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '6px 14px', borderRadius: '999px', border: 'none',
              cursor: 'pointer', fontWeight: 600, fontSize: '13px',
              background: mode === 'priority'
                ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                : 'linear-gradient(135deg, #f59e0b, #ef4444)',
              color: '#fff',
              boxShadow: mode === 'priority'
                ? '0 0 12px rgba(99,102,241,0.5)'
                : '0 0 12px rgba(245,158,11,0.5)',
              transition: 'all 0.25s ease',
            }}
          >
            {mode === 'priority' ? <Brain size={15} /> : <Zap size={15} />}
            {mode === 'priority' ? 'Priority' : 'Naive'}
          </button>

          {/* Voice Status Indicator */}
          <div 
            onClick={toggleListening}
            className={`voice-badge ${isListening ? 'listening' : ''}`}
          >
            <Mic size={18} />
            <span>{isListening ? 'Listening...' : 'Mic Off'}</span>
          </div>
        </header>

        <div className="content-area">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default DashboardLayout;